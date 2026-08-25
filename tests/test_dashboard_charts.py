from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from accounts.models import FinancialAccount, User
from core.models import Currency
from ledger.services import create_deposit


@pytest.mark.django_db
def test_dashboard_shows_account_allocation_and_monthly_movement(client):
    user = User.objects.create_user(username="chart-user", password="password")
    currency = Currency.objects.create(code="EUR", name="Euro", symbol="€")
    account = FinancialAccount.objects.create(
        owner=user,
        name="Chart account",
        account_type=FinancialAccount.Type.CHECKING,
        currency=currency,
    )
    create_deposit(user, account, Decimal("250"), date.today(), "Opening balance")
    client.force_login(user)

    response = client.get(reverse("dashboard:index"))

    assert response.status_code == 200
    assert "Account allocation" in response.content.decode()
    assert "Net-worth movement" in response.content.decode()
    assert "Chart account" in response.content.decode()
