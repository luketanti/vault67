from datetime import date
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from accounts.models import FinancialAccount, User
from core.models import Currency
from ledger.models import Transaction
from ledger.services import account_balance


@pytest.fixture
def import_account(db):
    user = User.objects.create_user(username="importer", password="password")
    currency = Currency.objects.create(code="EUR", name="Euro", symbol="€")
    account = FinancialAccount.objects.create(
        owner=user, name="Current", account_type="CHECKING", currency=currency
    )
    return user, account


def csv_upload(content):
    return SimpleUploadedFile("transactions.csv", content.encode(), content_type="text/csv")


@pytest.mark.django_db
def test_imports_sample_format_into_selected_account(client, import_account):
    user, account = import_account
    client.force_login(user)
    content = (
        "Transaction Date;Value Date;Description;Amount\n"
        "14/08/2026;14/08/2026;ACCRUED INTEREST TIME DEPOSIT;19.88\n"
        "14/08/2026;14/08/2026;15% WITHHOLDING TAX;-2.98\n"
    )

    response = client.post(
        reverse("ledger:import", args=[account.pk]), {"csv_file": csv_upload(content)}
    )

    assert response.status_code == 302
    assert response.url == reverse("accounts:detail", args=[account.pk])
    assert account_balance(account) == Decimal("16.9000")
    transactions = Transaction.objects.order_by("description")
    assert [item.transaction_type for item in transactions] == ["TAX", "INTEREST"]
    assert transactions[1].transaction_date == date(2026, 8, 14)
    assert transactions[1].notes == "Value date: 2026-08-14"


@pytest.mark.django_db
def test_invalid_row_rejects_entire_import(client, import_account):
    user, account = import_account
    client.force_login(user)
    content = (
        "Transaction Date;Description;Amount\n"
        "14/08/2026;Valid;10.00\n"
        "not-a-date;Invalid;-2.00\n"
    )

    response = client.post(
        reverse("ledger:import", args=[account.pk]), {"csv_file": csv_upload(content)}
    )

    assert response.status_code == 200
    assert "Row 3" in response.content.decode()
    assert Transaction.objects.count() == 0


@pytest.mark.django_db
def test_user_cannot_import_into_another_users_account(client, import_account):
    _, account = import_account
    other_user = User.objects.create_user(username="other", password="password")
    client.force_login(other_user)

    response = client.get(reverse("ledger:import", args=[account.pk]))

    assert response.status_code == 404


@pytest.mark.django_db
def test_anonymous_user_is_redirected_from_import(client, import_account):
    _, account = import_account

    response = client.get(reverse("ledger:import", args=[account.pk]))

    assert response.status_code == 302
    assert response.url.startswith(reverse("dashboard:login"))
