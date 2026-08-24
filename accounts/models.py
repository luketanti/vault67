from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models

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

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
