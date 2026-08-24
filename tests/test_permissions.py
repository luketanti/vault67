import pytest
from django.urls import reverse

from accounts.models import FinancialAccount, User
from core.models import Currency


@pytest.mark.django_db
def test_user_cannot_view_another_users_account(client):
    eur = Currency.objects.create(code="EUR", name="Euro", symbol="€")
    owner = User.objects.create_user(username="owner", password="x")
    outsider = User.objects.create_user(username="outsider", password="x")
    account = FinancialAccount.objects.create(
        owner=owner, name="Private", account_type="CHECKING", currency=eur
    )
    client.force_login(outsider)
    assert client.get(reverse("accounts:detail", args=[account.pk])).status_code == 404
