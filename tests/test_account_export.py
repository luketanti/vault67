import csv
import io
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from accounts.models import FinancialAccount, Institution, User
from core.models import Currency
from ledger.services import create_deposit, create_withdrawal


@pytest.fixture
def export_account(db):
    user = User.objects.create_user(username="exporter", password="password")
    currency = Currency.objects.create(code="EUR", name="Euro", symbol="€")
    institution = Institution.objects.create(owner=user, name="Example Bank")
    account = FinancialAccount.objects.create(
        owner=user,
        name="Daily Account",
        institution=institution,
        account_type="CHECKING",
        currency=currency,
        account_number_last4="1234",
        opening_date=date(2024, 1, 2),
    )
    return user, account


@pytest.mark.django_db
def test_exports_account_transactions_with_two_decimal_amounts(client, export_account):
    user, account = export_account
    create_deposit(
        user,
        account,
        Decimal("123843293.934"),
        date(2026, 8, 14),
        "Interest payment",
        notes="Value date: 2026-08-15",
    )
    create_withdrawal(user, account, Decimal("2182.1"), date(2026, 8, 13), "Fee")
    client.force_login(user)

    response = client.get(reverse("accounts:export", args=[account.pk]))

    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv; charset=utf-8"
    assert response["Content-Disposition"] == (
        'attachment; filename="daily-account-transactions.csv"'
    )
    rows = list(csv.reader(io.StringIO(response.content.decode()), delimiter=";"))
    assert rows == [
        ["Transaction Date", "Value Date", "Description", "Amount"],
        ["14/08/2026", "15/08/2026", "Interest payment", "123,843,293.93"],
        ["13/08/2026", "", "Fee", "-2,182.10"],
    ]


@pytest.mark.django_db
def test_user_cannot_export_another_users_account(client, export_account):
    _, account = export_account
    other_user = User.objects.create_user(username="other-exporter", password="password")
    client.force_login(other_user)

    response = client.get(reverse("accounts:export", args=[account.pk]))

    assert response.status_code == 404


@pytest.mark.django_db
def test_accounts_list_shows_balance_and_account_details(client, export_account):
    user, account = export_account
    create_deposit(user, account, Decimal("182393.93"), date(2026, 8, 14), "Deposit")
    client.force_login(user)

    response = client.get(reverse("accounts:list"))

    content = response.content.decode()
    assert response.status_code == 200
    assert "182,393.93" in content
    assert "Ending 1234" in content
    assert "Opened 2 Jan 2024" in content
    assert "1 transaction" in content
    assert reverse("accounts:export", args=[account.pk]) in content
