from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from core.models import Currency, TimeStampedModel


class User(AbstractUser):
    pass


class Institution(TimeStampedModel):
    class Type(models.TextChoices):
        BANK = "BANK", "Bank"
        BROKER = "BROKER", "Broker"
        LENDER = "LENDER", "Lender"
        CRYPTO_EXCHANGE = "CRYPTO_EXCHANGE", "Crypto exchange"
        OTHER = "OTHER", "Other"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="institutions"
    )
    name = models.CharField(max_length=120)
    institution_type = models.CharField(max_length=20, choices=Type.choices, default=Type.BANK)
    country = models.CharField(max_length=2, blank=True)
    website = models.URLField(blank=True)
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="unique_institution_per_owner")
        ]

    def __str__(self):
        return self.name


class FinancialAccount(TimeStampedModel):
    class Type(models.TextChoices):
        CHECKING = "CHECKING", "Checking"
        SAVINGS = "SAVINGS", "Savings"
        FIXED_TERM = "FIXED_TERM", "Fixed Term Deposit"
        CASH = "CASH", "Cash"
        BROKERAGE = "BROKERAGE", "Brokerage"
        CREDIT_CARD = "CREDIT_CARD", "Credit card"
        LOAN = "LOAN", "Loan"
        MORTGAGE = "MORTGAGE", "Mortgage"
        CRYPTO = "CRYPTO", "Crypto"
        OTHER = "OTHER", "Other"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="financial_accounts"
    )
    name = models.CharField(max_length=120)
    institution = models.ForeignKey(
        Institution, on_delete=models.PROTECT, related_name="accounts", null=True, blank=True
    )
    account_type = models.CharField(max_length=20, choices=Type.choices)
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT)
    account_number_last4 = models.CharField(max_length=4, blank=True)
    opening_date = models.DateField(null=True, blank=True)
    closing_date = models.DateField(null=True, blank=True)
    active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    return_tax_treatment = models.ForeignKey(
        "tax.ReturnTaxTreatment",
        on_delete=models.PROTECT,
        related_name="accounts",
        null=True,
        blank=True,
    )
    savings_annual_interest_rate = models.DecimalField(
        max_digits=12,
        decimal_places=8,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        help_text="Annual rate stored as a decimal fraction; 0.0325 means 3.25%.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def clean(self):
        errors = {}
        if (
            self.return_tax_treatment_id
            and self.owner_id
            and self.return_tax_treatment.owner_id != self.owner_id
        ):
            errors["return_tax_treatment"] = "Tax treatment must belong to the same user."
        if self.savings_annual_interest_rate is not None and self.account_type != self.Type.SAVINGS:
            errors["savings_annual_interest_rate"] = (
                "An interest rate can only be set on a savings account."
            )
        if errors:
            raise ValidationError(errors)

    @property
    def savings_annual_interest_rate_percent(self):
        if self.savings_annual_interest_rate is None:
            return None
        return self.savings_annual_interest_rate * Decimal(100)


class FixedTermDetails(TimeStampedModel):
    """Contract terms for a fixed-term account.

    ``annual_interest_rate`` is a decimal fraction: 0.0325 means 3.25%.
    Contractual principal is historical contract data; ledger entries remain the
    source of truth for the account's actual cash balance.
    """

    class InterestMethod(models.TextChoices):
        SIMPLE = "SIMPLE", "Simple Interest"
        COMPOUND = "COMPOUND", "Compound Interest"

    class CompoundingFrequency(models.TextChoices):
        DAILY = "DAILY", "Daily"
        MONTHLY = "MONTHLY", "Monthly"
        QUARTERLY = "QUARTERLY", "Quarterly"
        ANNUALLY = "ANNUALLY", "Annually"

    class PaymentMethod(models.TextChoices):
        AT_MATURITY = "AT_MATURITY", "At maturity"
        MONTHLY = "MONTHLY", "Monthly"
        QUARTERLY = "QUARTERLY", "Quarterly"
        ANNUALLY = "ANNUALLY", "Annually"

    class InterestDestination(models.TextChoices):
        CAPITALIZED = "CAPITALIZED", "Added to principal"
        PAID_OUT = "PAID_OUT", "Paid to another account"

    class MaturityInstruction(models.TextChoices):
        RETURN_TO_ACCOUNT = "RETURN_TO_ACCOUNT", "Return funds"
        RENEW_PRINCIPAL = "RENEW_PRINCIPAL", "Renew principal"
        RENEW_PRINCIPAL_AND_INTEREST = (
            "RENEW_PRINCIPAL_AND_INTEREST",
            "Renew principal and interest",
        )
        UNDECIDED = "UNDECIDED", "Undecided"

    account = models.OneToOneField(
        FinancialAccount, on_delete=models.CASCADE, related_name="fixed_term_details"
    )
    principal = models.DecimalField(
        max_digits=20, decimal_places=4, validators=[MinValueValidator(0.0001)]
    )
    start_date = models.DateField()
    maturity_date = models.DateField()
    annual_interest_rate = models.DecimalField(
        max_digits=12, decimal_places=8, validators=[MinValueValidator(0)]
    )
    interest_method = models.CharField(max_length=10, choices=InterestMethod.choices)
    compounding_frequency = models.CharField(
        max_length=12, choices=CompoundingFrequency.choices, blank=True
    )
    interest_payment_method = models.CharField(
        max_length=16, choices=PaymentMethod.choices, default=PaymentMethod.AT_MATURITY
    )
    interest_destination = models.CharField(
        max_length=12,
        choices=InterestDestination.choices,
        default=InterestDestination.CAPITALIZED,
    )
    interest_destination_account = models.ForeignKey(
        FinancialAccount,
        on_delete=models.PROTECT,
        related_name="fixed_term_interest_destinations",
        null=True,
        blank=True,
    )
    early_withdrawal_allowed = models.BooleanField(default=False)
    early_withdrawal_penalty_notes = models.TextField(blank=True)
    maturity_instruction = models.CharField(
        max_length=32,
        choices=MaturityInstruction.choices,
        default=MaturityInstruction.UNDECIDED,
    )
    maturity_destination_account = models.ForeignKey(
        FinancialAccount,
        on_delete=models.PROTECT,
        related_name="fixed_term_maturity_destinations",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name_plural = "fixed term details"
        constraints = [
            models.CheckConstraint(condition=models.Q(principal__gt=0), name="fixed_principal_gt_zero"),
            models.CheckConstraint(condition=models.Q(annual_interest_rate__gte=0), name="fixed_rate_nonnegative"),
            models.CheckConstraint(condition=models.Q(maturity_date__gt=models.F("start_date")), name="fixed_maturity_after_start"),
        ]

    def clean(self):
        errors = {}
        if self.account_id and self.account.account_type != FinancialAccount.Type.FIXED_TERM:
            errors["account"] = "Fixed-term details require a Fixed Term Deposit account."
        if self.start_date and self.maturity_date and self.maturity_date <= self.start_date:
            errors["maturity_date"] = "Maturity date must be after the start date."
        if self.interest_method == self.InterestMethod.COMPOUND and not self.compounding_frequency:
            errors["compounding_frequency"] = "Compound interest requires a frequency."
        for field_name in ("interest_destination_account", "maturity_destination_account"):
            destination = getattr(self, field_name, None)
            if destination and self.account_id:
                if destination.owner_id != self.account.owner_id:
                    errors[field_name] = "Destination account must belong to the same user."
                elif destination.pk == self.account_id:
                    errors[field_name] = "Choose an account other than this fixed-term account."
        if self.interest_destination == self.InterestDestination.PAID_OUT and not self.interest_destination_account:
            errors["interest_destination_account"] = "Select where paid-out interest should go."
        if errors:
            raise ValidationError(errors)

    def status_as_of(self, as_of_date):
        from .services.fixed_term import get_fixed_term_status

        return get_fixed_term_status(self, as_of_date)

    @property
    def fixed_term_status(self):
        return self.status_as_of(timezone.localdate())

    @property
    def annual_interest_rate_percent(self):
        return self.annual_interest_rate * 100

    def __str__(self):
        return f"{self.account.name} fixed-term contract"
