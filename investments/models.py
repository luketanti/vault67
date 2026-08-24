from django.core.validators import MinValueValidator
from django.db import models

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
                fields=["symbol", "exchange"], name="unique_security_symbol_exchange"
            )
        ]
        ordering = ["symbol"]

    def __str__(self):
        return self.symbol


class SecurityPrice(TimeStampedModel):
    security = models.ForeignKey(Security, on_delete=models.CASCADE, related_name="prices")
    date = models.DateField()
    price = models.DecimalField(max_digits=20, decimal_places=8, validators=[MinValueValidator(0)])
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT)
    source = models.CharField(max_length=64, default="manual")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["security", "date", "source"], name="unique_security_price"
            )
        ]
        ordering = ["-date"]


class InvestmentTransaction(TimeStampedModel):
    transaction = models.OneToOneField(
        Transaction, on_delete=models.PROTECT, related_name="investment_detail"
    )
    security = models.ForeignKey(Security, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=24, decimal_places=8)
    price_per_unit = models.DecimalField(max_digits=20, decimal_places=8)
    gross_amount = models.DecimalField(max_digits=20, decimal_places=4)
    fees = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    taxes = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT)
    exchange_rate = models.DecimalField(max_digits=24, decimal_places=12, null=True, blank=True)
