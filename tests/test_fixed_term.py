from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from accounts.models import FinancialAccount, FixedTermDetails, User
from accounts.services.fixed_term import (
    calculate_fixed_term_progress,
    calculate_fixed_term_projection,
    get_fixed_term_status,
)
from core.models import Currency
from ledger.services import account_balance


@pytest.fixture
def fixed_term_base(db):
    owner = User.objects.create_user(username="term-owner", password="password")
    currency = Currency.objects.create(code="EUR", name="Euro", symbol="€")
    account = FinancialAccount.objects.create(
        owner=owner,
        name="Fixed deposit",
        account_type=FinancialAccount.Type.FIXED_TERM,
        currency=currency,
    )
    return owner, currency, account


def make_details(account, **overrides):
    values = {
        "principal": Decimal(10000),
        "start_date": date(2026, 1, 1),
        "maturity_date": date(2027, 1, 1),
        "annual_interest_rate": Decimal("0.03"),
        "interest_method": FixedTermDetails.InterestMethod.SIMPLE,
        "interest_payment_method": FixedTermDetails.PaymentMethod.AT_MATURITY,
        "interest_destination": FixedTermDetails.InterestDestination.CAPITALIZED,
        "maturity_instruction": FixedTermDetails.MaturityInstruction.UNDECIDED,
    }
    values.update(overrides)
    return FixedTermDetails(account=account, **values)


@pytest.mark.django_db
def test_valid_fixed_term_and_invalid_principal(fixed_term_base):
    _, _, account = fixed_term_base
    valid = make_details(account)
    valid.full_clean()
    for principal in (Decimal(0), Decimal(-1)):
        invalid = make_details(account, principal=principal)
        with pytest.raises(ValidationError):
            invalid.full_clean()


@pytest.mark.django_db
@pytest.mark.parametrize("maturity", [date(2025, 12, 31), date(2026, 1, 1)])
def test_maturity_must_follow_start(fixed_term_base, maturity):
    details = make_details(fixed_term_base[2], maturity_date=maturity)
    with pytest.raises(ValidationError):
        details.full_clean()


@pytest.mark.django_db
def test_compound_requires_frequency(fixed_term_base):
    details = make_details(
        fixed_term_base[2],
        interest_method=FixedTermDetails.InterestMethod.COMPOUND,
        compounding_frequency="",
    )
    with pytest.raises(ValidationError):
        details.full_clean()


def test_simple_interest_act_365():
    projection = calculate_fixed_term_projection(
        Decimal(10000), Decimal("0.03"), date(2026, 1, 1), date(2027, 1, 1), "SIMPLE"
    )
    assert projection.gross_interest == Decimal(300)
    assert projection.maturity_value == Decimal(10300)


def test_partial_period_accrual(fixed_term_base):
    details = make_details(fixed_term_base[2])
    progress = calculate_fixed_term_progress(details, date(2026, 7, 2))
    assert progress.days_elapsed == 182
    assert progress.accrued_interest == Decimal(10000) * Decimal("0.03") * Decimal(182) / Decimal(365)


@pytest.mark.django_db
def test_fixed_term_edit_keeps_native_date_values_and_formats_rate(client, fixed_term_base):
    owner, _, account = fixed_term_base
    details = make_details(account, annual_interest_rate=Decimal("0.0325"))
    details.full_clean()
    details.save()
    client.force_login(owner)

    edit_response = client.get(reverse("accounts:edit", args=[account.pk]))
    detail_response = client.get(reverse("accounts:detail", args=[account.pk]))

    assert 'id="id_fixed_start_date"' in edit_response.content.decode()
    assert 'value="2026-01-01"' in edit_response.content.decode()
    assert 'value="2027-01-01"' in edit_response.content.decode()
    assert 'id="id_fixed_annual_rate_percent"' in edit_response.content.decode()
    assert 'value="3.25"' in edit_response.content.decode()
    assert "3.25%" in detail_response.content.decode()


@pytest.mark.parametrize("frequency,periods", [("MONTHLY", 12), ("QUARTERLY", 4), ("ANNUALLY", 1)])
def test_compound_interest_frequencies(frequency, periods):
    projection = calculate_fixed_term_projection(
        Decimal(10000), Decimal("0.03"), date(2026, 1, 1), date(2027, 1, 1), "COMPOUND", frequency
    )
    expected = Decimal(10000) * ((Decimal(1) + Decimal("0.03") / Decimal(periods)) ** Decimal(periods) - Decimal(1))
    assert abs(projection.gross_interest - expected) < Decimal("0.00000001")


@pytest.mark.django_db
def test_lifecycle_is_deterministic(fixed_term_base):
    details = make_details(fixed_term_base[2])
    assert get_fixed_term_status(details, date(2025, 12, 31)) == "PLANNED"
    assert get_fixed_term_status(details, date(2026, 6, 1)) == "ACTIVE"
    assert get_fixed_term_status(details, date(2027, 1, 1)) == "MATURED"
    details.account.active = False
    assert get_fixed_term_status(details, date(2026, 6, 1)) == "CLOSED"


@pytest.mark.django_db
def test_create_fixed_term_with_funding_posts_one_transfer(client):
    owner = User.objects.create_user(username="owner", password="password")
    currency = Currency.objects.create(code="EUR", name="Euro", symbol="€")
    funding = FinancialAccount.objects.create(
        owner=owner, name="Savings", account_type=FinancialAccount.Type.SAVINGS, currency=currency
    )
    client.force_login(owner)
    response = client.post(
        reverse("accounts:create"),
        {
            "name": "One year term",
            "account_type": "FIXED_TERM",
            "currency": currency.pk,
            "fixed_principal": "10000.00",
            "fixed_start_date": "2026-01-01",
            "fixed_maturity_date": "2027-01-01",
            "fixed_annual_rate_percent": "3.00",
            "fixed_interest_method": "SIMPLE",
            "fixed_interest_payment_method": "AT_MATURITY",
            "fixed_interest_destination": "CAPITALIZED",
            "fixed_maturity_instruction": "UNDECIDED",
            "funding_account": funding.pk,
        },
    )
    assert response.status_code == 302
    account = FinancialAccount.objects.get(owner=owner, name="One year term")
    transaction = account.entries.get().transaction
    assert transaction.entries.count() == 2
    assert account_balance(funding) == Decimal("-10000.0000")
    assert account_balance(account) == Decimal("10000.0000")


@pytest.mark.django_db
def test_failed_funding_rolls_back_account_and_contract(client, monkeypatch):
    owner = User.objects.create_user(username="rollback-owner", password="password")
    currency = Currency.objects.create(code="EUR", name="Euro", symbol="€")
    funding = FinancialAccount.objects.create(
        owner=owner, name="Savings", account_type=FinancialAccount.Type.SAVINGS, currency=currency
    )
    client.force_login(owner)

    def fail_transfer(*args, **kwargs):
        raise RuntimeError("simulated ledger failure")

    monkeypatch.setattr("accounts.views.create_transfer", fail_transfer)
    with pytest.raises(RuntimeError, match="simulated ledger failure"):
        client.post(
            reverse("accounts:create"),
            {
                "name": "Rolled back term",
                "account_type": "FIXED_TERM",
                "currency": currency.pk,
                "fixed_principal": "10000.00",
                "fixed_start_date": "2026-01-01",
                "fixed_maturity_date": "2027-01-01",
                "fixed_annual_rate_percent": "3.00",
                "fixed_interest_method": "SIMPLE",
                "fixed_interest_payment_method": "AT_MATURITY",
                "fixed_interest_destination": "CAPITALIZED",
                "fixed_maturity_instruction": "UNDECIDED",
                "funding_account": funding.pk,
            },
        )
    assert not FinancialAccount.objects.filter(owner=owner, name="Rolled back term").exists()
    assert not FixedTermDetails.objects.filter(account__owner=owner).exists()


@pytest.mark.django_db
def test_forged_destination_account_is_rejected(client):
    owner = User.objects.create_user(username="owner", password="password")
    other = User.objects.create_user(username="other", password="password")
    currency = Currency.objects.create(code="EUR", name="Euro", symbol="€")
    foreign_account = FinancialAccount.objects.create(
        owner=other, name="Foreign", account_type=FinancialAccount.Type.SAVINGS, currency=currency
    )
    client.force_login(owner)
    response = client.post(
        reverse("accounts:create"),
        {
            "name": "Forged term",
            "account_type": "FIXED_TERM",
            "currency": currency.pk,
            "fixed_principal": "1000.00",
            "fixed_start_date": "2026-01-01",
            "fixed_maturity_date": "2027-01-01",
            "fixed_annual_rate_percent": "3.00",
            "fixed_interest_method": "SIMPLE",
            "fixed_interest_payment_method": "AT_MATURITY",
            "fixed_interest_destination": "PAID_OUT",
            "fixed_interest_destination_account": foreign_account.pk,
            "fixed_maturity_instruction": "UNDECIDED",
        },
    )
    assert response.status_code == 200
    assert not FinancialAccount.objects.filter(owner=owner, name="Forged term").exists()
    assert "Select a valid choice" in response.content.decode()


@pytest.mark.django_db
def test_user_cannot_view_edit_or_fund_from_another_users_fixed_term(client, fixed_term_base):
    _, currency, fixed_account = fixed_term_base
    details = make_details(fixed_account)
    details.full_clean()
    details.save()
    attacker = User.objects.create_user(username="attacker", password="password")
    attacker_account = FinancialAccount.objects.create(
        owner=attacker,
        name="Attacker savings",
        account_type=FinancialAccount.Type.SAVINGS,
        currency=currency,
    )
    client.force_login(attacker)
    assert client.get(reverse("accounts:detail", args=[fixed_account.pk])).status_code == 404
    assert client.get(reverse("accounts:edit", args=[fixed_account.pk])).status_code == 404
    response = client.post(
        reverse("accounts:create"),
        {
            "name": "Forged funding",
            "account_type": "FIXED_TERM",
            "currency": currency.pk,
            "fixed_principal": "1000.00",
            "fixed_start_date": "2026-01-01",
            "fixed_maturity_date": "2027-01-01",
            "fixed_annual_rate_percent": "3.00",
            "fixed_interest_method": "SIMPLE",
            "fixed_interest_payment_method": "AT_MATURITY",
            "fixed_interest_destination": "CAPITALIZED",
            "fixed_maturity_instruction": "UNDECIDED",
            "funding_account": fixed_account.pk,
        },
    )
    assert response.status_code == 200
    assert not FinancialAccount.objects.filter(owner=attacker, name="Forged funding").exists()
    assert FinancialAccount.objects.filter(pk=attacker_account.pk).exists()
