from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from accounts.models import FinancialAccount
from core.models import Currency, TimeStampedModel


class Transaction(TimeStampedModel):
    class Type(models.TextChoices):
        DEPOSIT = "DEPOSIT", "Deposit"
        WITHDRAWAL = "WITHDRAWAL", "Withdrawal"
        TRANSFER = "TRANSFER", "Transfer"
        INCOME = "INCOME", "Income"
        EXPENSE = "EXPENSE", "Expense"
        INTEREST = "INTEREST", "Interest"
        DIVIDEND = "DIVIDEND", "Dividend"
        BUY = "BUY", "Buy"
        SELL = "SELL", "Sell"
        FEE = "FEE", "Fee"
        TAX = "TAX", "Tax"
        ADJUSTMENT = "ADJUSTMENT", "Adjustment"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="transactions"
    )
    transaction_date = models.DateField()
    description = models.CharField(max_length=255)
    transaction_type = models.CharField(max_length=16, choices=Type.choices)
    reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-transaction_date", "-created_at"]

    def __str__(self):
        return f"{self.transaction_date}: {self.description}"


class TransactionEntry(models.Model):
    """Signed ledger entry: positive increases the displayed account balance; negative decreases it."""

    transaction = models.ForeignKey(Transaction, on_delete=models.PROTECT, related_name="entries")
    account = models.ForeignKey(FinancialAccount, on_delete=models.PROTECT, related_name="entries")
    amount = models.DecimalField(max_digits=20, decimal_places=4)
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT)
    exchange_rate = models.DecimalField(
        max_digits=24, decimal_places=12, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    base_currency_amount = models.DecimalField(
        max_digits=20, decimal_places=4, null=True, blank=True
    )
    entry_type = models.CharField(max_length=16, blank=True)

    class Meta:
        ordering = ["transaction__transaction_date", "id"]
        constraints = [
            models.CheckConstraint(condition=~models.Q(amount=0), name="entry_amount_nonzero")
        ]
