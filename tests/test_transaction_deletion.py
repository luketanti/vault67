from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from accounts.models import FinancialAccount, User
from core.models import Currency
from ledger.models import Transaction, TransactionEntry
from ledger.services import account_balance, create_deposit, create_transfer


@pytest.fixture
def deletion_accounts(db):
    user = User.objects.create_user(username="deleter", password="password")
    currency = Currency.objects.create(code="EUR", name="Euro", symbol="€")
    first = FinancialAccount.objects.create(
        owner=user, name="First", account_type="CHECKING", currency=currency
    )
    second = FinancialAccount.objects.create(
        owner=user, name="Second", account_type="SAVINGS", currency=currency
    )
    return user, first, second


@pytest.mark.django_db
def test_transaction_requires_confirmation_then_deletes_all_transfer_entries(
    client, deletion_accounts
):
    user, first, second = deletion_accounts
    entry_transaction = create_transfer(
        user, first, second, Decimal(25), date.today(), "Move funds"
    )
    client.force_login(user)
    url = reverse("ledger:delete", args=[entry_transaction.pk])

    confirmation = client.get(url)

    assert confirmation.status_code == 200
    assert "Yes, delete transaction" in confirmation.content.decode()
    assert Transaction.objects.filter(pk=entry_transaction.pk).exists()

    response = client.post(url)

    assert response.status_code == 302
    assert not Transaction.objects.filter(pk=entry_transaction.pk).exists()
    assert TransactionEntry.objects.count() == 0
    assert account_balance(first) == 0
    assert account_balance(second) == 0


@pytest.mark.django_db
def test_delete_all_only_deletes_transactions_associated_with_account(client, deletion_accounts):
    user, first, second = deletion_accounts
    create_deposit(user, first, Decimal(10), date.today(), "First only")
    create_transfer(user, first, second, Decimal(3), date.today(), "Transfer")
    remaining = create_deposit(user, second, Decimal(7), date.today(), "Second only")
    client.force_login(user)
    url = reverse("ledger:delete-account-transactions", args=[first.pk])

    confirmation = client.get(url)

    assert confirmation.status_code == 200
    content = confirmation.content.decode()
    assert "2 transactions" in content
    assert "other accounts" in content
    assert Transaction.objects.count() == 3

    response = client.post(url)

    assert response.status_code == 302
    assert list(Transaction.objects.values_list("pk", flat=True)) == [remaining.pk]
    assert account_balance(first) == 0
    assert account_balance(second) == Decimal("7.0000")


@pytest.mark.django_db
def test_user_cannot_delete_another_users_transaction_or_account(client, deletion_accounts):
    owner, first, _ = deletion_accounts
    entry_transaction = create_deposit(owner, first, Decimal(10), date.today(), "Protected")
    other_user = User.objects.create_user(username="other-deleter", password="password")
    client.force_login(other_user)

    transaction_response = client.post(reverse("ledger:delete", args=[entry_transaction.pk]))
    account_response = client.post(reverse("ledger:delete-account-transactions", args=[first.pk]))

    assert transaction_response.status_code == 404
    assert account_response.status_code == 404
    assert Transaction.objects.filter(pk=entry_transaction.pk).exists()
