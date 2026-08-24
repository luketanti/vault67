from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from accounts.models import FinancialAccount, User
from core.models import Currency
from ledger.services import account_balance, create_deposit, create_transfer, create_withdrawal


@pytest.fixture
def user(db):
    return User.objects.create_user(username="alice", password="password")


@pytest.fixture
def accounts(user):
    eur = Currency.objects.create(code="EUR", name="Euro", symbol="€")
    return (
        FinancialAccount.objects.create(
            owner=user, name="Current", account_type="CHECKING", currency=eur
        ),
        FinancialAccount.objects.create(
            owner=user, name="Savings", account_type="SAVINGS", currency=eur
        ),
    )


@pytest.mark.django_db
def test_deposit_and_withdrawal_balance(user, accounts):
    current, _ = accounts
    create_deposit(user, current, Decimal("100.00"), date.today(), "Deposit")
    create_withdrawal(user, current, Decimal("12.25"), date.today(), "Cash")
    assert account_balance(current) == Decimal("87.7500")


@pytest.mark.django_db
def test_transfer_is_linked_and_net_zero(user, accounts):
    source, destination = accounts
    tx = create_transfer(user, source, destination, Decimal(50), date.today(), "Move funds")
    assert tx.entries.count() == 2
    assert account_balance(source) == Decimal("-50.0000")
    assert account_balance(destination) == Decimal("50.0000")
    assert sum(e.amount for e in tx.entries.all()) == 0


@pytest.mark.django_db
def test_transfer_rejects_same_account(user, accounts):
    with pytest.raises(ValidationError):
        create_transfer(user, accounts[0], accounts[0], Decimal(1), date.today(), "No")
