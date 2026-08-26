from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from accounts.models import FinancialAccount
from core.models import Currency, TimeStampedModel
from ledger.models import Transaction


class Security(TimeStampedModel):
    class Type(models.TextChoices):
        STOCK = "STOCK", "Stock"
        ETF = "ETF", "ETF"
        FUND = "FUND", "Fund"
        BOND = "BOND", "Bond"
        CRYPTO = "CRYPTO", "Crypto"
        CASH_EQUIVALENT = "CASH_EQUIVALENT", "Cash equivalent"
        OTHER = "OTHER", "Other"

    symbol = models.CharField(max_length=24)
    name = models.CharField(max_length=160)
    security_type = models.CharField(max_length=20, choices=Type.choices)
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT)
    isin = models.CharField(max_length=12, blank=True)
    exchange = models.CharField(max_length=64, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["symbol", "exchange"],
                condition=~models.Q(exchange=""),
                name="unique_security_symbol_exchange",
            ),
            models.UniqueConstraint(
                fields=["isin"], condition=~models.Q(isin=""), name="unique_security_isin"
            ),
        ]
        ordering = ["symbol"]

    def __str__(self):
        return self.symbol


class SecurityPrice(TimeStampedModel):
    class Source(models.TextChoices):
        MANUAL = "MANUAL", "Manual"

    security = models.ForeignKey(Security, on_delete=models.CASCADE, related_name="prices")
    date = models.DateField()
    price = models.DecimalField(max_digits=20, decimal_places=8, validators=[MinValueValidator(0)])
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT)
    source = models.CharField(max_length=64, choices=Source.choices, default=Source.MANUAL)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["security", "date", "source"], name="unique_security_price"
            )
        ]
        ordering = ["-date"]


class InvestmentTransaction(TimeStampedModel):
    """Investment metadata attached to one authoritative cash-ledger transaction.

    ``exchange_rate`` means one unit of ``currency`` equals this many units of
    the brokerage account currency. It is fixed at posting time and is never
    replaced with a current market rate.
    """

    transaction = models.OneToOneField(
        Transaction, on_delete=models.PROTECT, related_name="investment_detail"
    )
    account = models.ForeignKey(
        FinancialAccount, on_delete=models.PROTECT, related_name="investment_transactions"
    )
    security = models.ForeignKey(Security, on_delete=models.PROTECT)
    settlement_date = models.DateField(null=True, blank=True)
    quantity = models.DecimalField(max_digits=28, decimal_places=8, null=True, blank=True)
    price_per_unit = models.DecimalField(max_digits=28, decimal_places=8, null=True, blank=True)
    gross_amount = models.DecimalField(max_digits=20, decimal_places=4)
    fees = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    taxes = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT)
    exchange_rate = models.DecimalField(
        max_digits=24,
        decimal_places=12,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.000000000001"))],
    )

    class Meta:
        ordering = ["transaction__transaction_date", "transaction_id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__isnull=True) | models.Q(quantity__gt=0),
                name="investment_quantity_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(price_per_unit__isnull=True) | models.Q(price_per_unit__gte=0),
                name="investment_price_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(gross_amount__gte=0), name="investment_gross_nonnegative"
            ),
            models.CheckConstraint(
                condition=models.Q(fees__gte=0), name="investment_fees_nonnegative"
            ),
            models.CheckConstraint(
                condition=models.Q(taxes__gte=0), name="investment_taxes_nonnegative"
            ),
        ]

    @property
    def transaction_type(self):
        return self.transaction.transaction_type

    @property
    def trade_date(self):
        return self.transaction.transaction_date

    @property
    def net_cash_impact_native(self):
        transaction_type = self.transaction_type
        if transaction_type == Transaction.Type.BUY:
            return -(self.gross_amount + self.fees + self.taxes)
        if transaction_type == Transaction.Type.SELL:
            return self.gross_amount - self.fees - self.taxes
        if transaction_type == Transaction.Type.DIVIDEND:
            return self.gross_amount - self.fees - self.taxes
        return -self.gross_amount

    def clean(self):
        errors = {}
        transaction_type = self.transaction_type if self.transaction_id else None
        if self.account_id and self.account.account_type != FinancialAccount.Type.BROKERAGE:
            errors["account"] = "Investment transactions require a brokerage account."
        if (
            self.transaction_id
            and self.account_id
            and self.transaction.owner_id != self.account.owner_id
        ):
            errors["account"] = "Transaction and account owners must match."
        if self.security_id and not self.security.active:
            errors["security"] = "Security must be active."
        if self.security_id and self.currency_id and self.security.currency_id != self.currency_id:
            errors["currency"] = "Transaction currency must match the security currency."
        if (
            self.settlement_date
            and self.transaction_id
            and self.settlement_date < self.transaction.transaction_date
        ):
            errors["settlement_date"] = "Settlement date cannot be before the trade date."
        if transaction_type in (Transaction.Type.BUY, Transaction.Type.SELL):
            if self.quantity is None or self.quantity <= 0:
                errors["quantity"] = "Quantity must be positive."
            if self.price_per_unit is None or self.price_per_unit < 0:
                errors["price_per_unit"] = "Price per unit must be non-negative."
            if self.quantity is not None and self.price_per_unit is not None:
                expected = (self.quantity * self.price_per_unit).quantize(Decimal("0.0001"))
                if self.gross_amount != expected:
                    errors["gross_amount"] = (
                        f"Gross amount must equal quantity × price ({expected})."
                    )
        elif self.quantity is not None or self.price_per_unit is not None:
            errors["quantity"] = "Quantity and price are only used for buy and sell transactions."
        if self.currency_id and self.account_id:
            same_currency = self.currency_id == self.account.currency_id
            if not same_currency and self.exchange_rate is None:
                errors["exchange_rate"] = (
                    "An exchange rate is required when transaction and account currencies differ."
                )
            if same_currency and self.exchange_rate not in (None, Decimal(1)):
                errors["exchange_rate"] = (
                    "Same-currency transactions must use an exchange rate of 1."
                )
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.transaction_type} {self.security.symbol} on {self.trade_date}"
