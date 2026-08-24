from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from accounts.models import FinancialAccount, User
from core.models import Currency
from ledger.models import Transaction


@pytest.fixture
def owned_accounts(db):
    currency = Currency.objects.create(code="EUR", name="Euro", symbol="€")
    owner = User.objects.create_user(username="owner", password="password")
    attacker = User.objects.create_user(username="attacker", password="password")
    owner_account = FinancialAccount.objects.create(
        owner=owner, name="Owner account", account_type="CHECKING", currency=currency
    )
    attacker_account = FinancialAccount.objects.create(
        owner=attacker, name="Attacker account", account_type="CHECKING", currency=currency
    )
    return owner, attacker, owner_account, attacker_account


@pytest.mark.django_db
def test_anonymous_users_are_redirected_from_financial_pages(client):
    response = client.get(reverse("accounts:list"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("dashboard:login"))


@pytest.mark.django_db
def test_forged_transfer_account_id_is_rejected(client, owned_accounts):
    _, attacker, owner_account, attacker_account = owned_accounts
    client.force_login(attacker)
    response = client.post(
        reverse("ledger:transfer"),
        {"source": owner_account.pk, "destination": attacker_account.pk, "amount": "10.00", "transaction_date": date.today(), "description": "Forged"},
    )
    assert response.status_code == 200
    assert Transaction.objects.filter(owner=attacker).count() == 0
    assert "Select a valid choice" in response.content.decode()


@pytest.mark.django_db
def test_user_cannot_archive_another_users_account(client, owned_accounts):
    _, attacker, owner_account, _ = owned_accounts
    client.force_login(attacker)
    response = client.post(reverse("accounts:archive", args=[owner_account.pk]))
    assert response.status_code == 404
    owner_account.refresh_from_db()
    assert owner_account.active is True


@pytest.mark.django_db
def test_csrf_middleware_rejects_missing_token(client, owned_accounts):
    _, attacker, _, attacker_account = owned_accounts
    client.force_login(attacker)
    csrf_client = type(client)(enforce_csrf_checks=True)
    csrf_client.force_login(attacker)
    response = csrf_client.post(
        reverse("ledger:deposit"),
        {"account": attacker_account.pk, "amount": Decimal("1.00"), "transaction_date": date.today(), "description": "CSRF"},
    )
    assert response.status_code == 403
