from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from accounts.models import FinancialAccount, User
from core.models import Currency


@pytest.fixture
def savings_owner(db):
    owner = User.objects.create_user(username="saver", password="password")
    currency = Currency.objects.create(code="EUR", name="Euro", symbol="€")
    return owner, currency


@pytest.mark.django_db
def test_create_savings_account_with_interest_rate(client, savings_owner):
    owner, currency = savings_owner
    client.force_login(owner)

    response = client.post(
        reverse("accounts:create"),
        {
            "name": "Rainy day fund",
            "account_type": FinancialAccount.Type.SAVINGS,
            "currency": currency.pk,
            "savings_annual_interest_rate_percent": "3.25",
        },
    )

    assert response.status_code == 302
    account = FinancialAccount.objects.get(owner=owner, name="Rainy day fund")
    assert account.savings_annual_interest_rate == Decimal("0.03250000")

    detail = client.get(reverse("accounts:detail", args=[account.pk])).content.decode()
    account_list = client.get(reverse("accounts:list")).content.decode()
    edit = client.get(reverse("accounts:edit", args=[account.pk])).content.decode()
    assert "3.25%" in detail
    assert "3.25% annual interest" in account_list
    assert 'id="id_savings_annual_interest_rate_percent"' in edit
    assert 'value="3.25"' in edit


@pytest.mark.django_db
def test_interest_rate_posted_for_non_savings_account_is_ignored(client, savings_owner):
    owner, currency = savings_owner
    client.force_login(owner)

    response = client.post(
        reverse("accounts:create"),
        {
            "name": "Current account",
            "account_type": FinancialAccount.Type.CHECKING,
            "currency": currency.pk,
            "savings_annual_interest_rate_percent": "9.99",
        },
    )

    assert response.status_code == 302
    account = FinancialAccount.objects.get(owner=owner, name="Current account")
    assert account.savings_annual_interest_rate is None


@pytest.mark.django_db
def test_model_rejects_savings_interest_rate_on_other_account_types(savings_owner):
    owner, currency = savings_owner
    account = FinancialAccount(
        owner=owner,
        name="Invalid rate",
        account_type=FinancialAccount.Type.CASH,
        currency=currency,
        savings_annual_interest_rate=Decimal("0.02"),
    )

    with pytest.raises(ValidationError):
        account.full_clean()
