from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction

from .models import Transaction, TransactionEntry


def _create(owner, account, amount, transaction_type, date, description, notes=""):
    if amount == Decimal(0):
        raise ValidationError("Amount must not be zero.")
    if account.owner_id != owner.id:
        raise ValidationError("Account does not belong to user.")
    with db_transaction.atomic():
        entry_transaction = Transaction.objects.create(
            owner=owner,
            transaction_date=date,
            description=description,
            notes=notes,
            transaction_type=transaction_type,
        )
        TransactionEntry.objects.create(
            transaction=entry_transaction,
            account=account,
            amount=amount,
            currency=account.currency,
            entry_type=transaction_type,
        )
    return entry_transaction


def create_deposit(
    owner, account, amount, date, description, transaction_type=Transaction.Type.DEPOSIT, notes=""
):
    return _create(owner, account, amount, transaction_type, date, description, notes)


def create_withdrawal(
    owner,
    account,
    amount,
    date,
    description,
    transaction_type=Transaction.Type.WITHDRAWAL,
    notes="",
):
    return (
        _create(owner, account, -amount, transaction_type, date, description, notes)
        if amount > Decimal(0)
        else (_ for _ in ()).throw(ValidationError("Amount must be positive."))
    )


def create_transfer(owner, source, destination, amount, date, description, notes=""):
    if amount <= Decimal(0):
        raise ValidationError("Amount must be positive.")
    if source.pk == destination.pk:
        raise ValidationError("Source and destination must differ.")
    if source.owner_id != owner.id or destination.owner_id != owner.id:
        raise ValidationError("Accounts must belong to user.")
    if source.currency_id != destination.currency_id:
        raise ValidationError("Cross-currency transfers need an explicit FX rate.")
    with db_transaction.atomic():
        entry_transaction = Transaction.objects.create(
            owner=owner,
            transaction_date=date,
            description=description,
            notes=notes,
            transaction_type=Transaction.Type.TRANSFER,
        )
        TransactionEntry.objects.bulk_create(
            [
                TransactionEntry(
                    transaction=entry_transaction,
                    account=source,
                    amount=-amount,
                    currency=source.currency,
                    entry_type="TRANSFER_OUT",
                ),
                TransactionEntry(
                    transaction=entry_transaction,
                    account=destination,
                    amount=amount,
                    currency=destination.currency,
                    entry_type="TRANSFER_IN",
                ),
            ]
        )
    return entry_transaction


def account_balance(account):
    from django.db.models import Sum

    return account.entries.aggregate(total=Sum("amount"))["total"] or Decimal(0)
