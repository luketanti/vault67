from datetime import date
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from accounts.models import FinancialAccount, FixedTermDetails, User
from core.models import Currency
from tax.models import ReturnTaxTreatment
from tax.services.returns import calculate_return_tax


def make_treatment(owner, treatment_type, rate=None, **kwargs):
    return ReturnTaxTreatment.objects.create(
        owner=owner,
        name=f"{treatment_type}-{rate}",
        treatment_type=treatment_type,
        tax_rate=rate,
        **kwargs,
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("treatment_type", "withheld", "due_later", "net"),
    [
        ("NONE", "0", "0", "100"),
        ("WITHHOLDING", "15", "0", "85"),
        ("YEAR_END", "0", "15", "85"),
        ("EXEMPT", "0", "0", "100"),
    ],
)
def test_return_tax_treatment_semantics(treatment_type, withheld, due_later, net):
    owner = User.objects.create_user(username=f"tax-{treatment_type}")
    rate = None if treatment_type in {"NONE", "EXEMPT"} else Decimal("15.00")
    treatment = make_treatment(owner, treatment_type, rate)

    result = calculate_return_tax(Decimal(100), treatment)

    assert result.estimated_tax == Decimal(100) - Decimal(net)
    assert result.tax_withheld == Decimal(withheld)
    assert result.estimated_tax_due_later == Decimal(due_later)
    assert result.net_return == Decimal(net)


@pytest.mark.django_db
def test_custom_tax_treatment_respects_deduction_source():
    owner = User.objects.create_user(username="custom-tax")
    treatment = make_treatment(owner, "CUSTOM", Decimal("15.00"), tax_deducted_at_source=True)
    result = calculate_return_tax(Decimal(100), treatment)
    assert result.tax_withheld == Decimal(15)
    assert result.estimated_tax_due_later == Decimal(0)


@pytest.mark.django_db
def test_tax_calculation_keeps_decimal_precision_until_display():
    owner = User.objects.create_user(username="precision-tax")
    treatment = make_treatment(owner, "WITHHOLDING", Decimal("15.00"))
    result = calculate_return_tax(Decimal("812.50"), treatment)

    assert result.estimated_tax == Decimal("121.875")
    assert result.net_return == Decimal("690.625")
    assert result.estimated_tax.quantize(Decimal("0.01"), ROUND_HALF_UP) == Decimal("121.88")
    assert result.net_return.quantize(Decimal("0.01"), ROUND_HALF_EVEN) == Decimal("690.62")


@pytest.mark.django_db
def test_tax_treatment_validation():
    owner = User.objects.create_user(username="validation-tax")
    for rate in (Decimal("-0.01"), Decimal("100.01")):
        treatment = ReturnTaxTreatment(
            owner=owner, name=str(rate), treatment_type="WITHHOLDING", tax_rate=rate
        )
        with pytest.raises(ValidationError):
            treatment.full_clean()
    with pytest.raises(ValidationError):
        ReturnTaxTreatment(owner=owner, name="missing", treatment_type="YEAR_END").full_clean()
    ReturnTaxTreatment(owner=owner, name="none", treatment_type="NONE").full_clean()
    ReturnTaxTreatment(owner=owner, name="exempt", treatment_type="EXEMPT", tax_rate=0).full_clean()


@pytest.mark.django_db
def test_fixed_term_projection_includes_estimated_tax(client):
    owner = User.objects.create_user(username="term-tax")
    currency = Currency.objects.create(code="EUR", name="Euro", symbol="€")
    treatment = make_treatment(owner, "WITHHOLDING", Decimal("15.00"))
    account = FinancialAccount.objects.create(
        owner=owner,
        name="Taxable term",
        account_type="FIXED_TERM",
        currency=currency,
        return_tax_treatment=treatment,
    )
    FixedTermDetails.objects.create(
        account=account,
        principal=Decimal(25000),
        start_date=date(2026, 1, 1),
        maturity_date=date(2027, 1, 1),
        annual_interest_rate=Decimal("0.0325"),
        interest_method="SIMPLE",
        interest_payment_method="AT_MATURITY",
        interest_destination="CAPITALIZED",
        maturity_instruction="UNDECIDED",
    )
    client.force_login(owner)
    response = client.get(reverse("accounts:detail", args=[account.pk]))
    content = response.content.decode()
    assert "812.50 EUR" in content
    assert "121.88 EUR" in content
    assert "690.62 EUR" in content
    assert "25,690.62 EUR" in content


@pytest.mark.django_db
def test_tax_treatment_ownership_and_forged_account_assignment(client):
    owner = User.objects.create_user(username="tax-owner", password="password")
    other = User.objects.create_user(username="tax-other", password="password")
    currency = Currency.objects.create(code="EUR", name="Euro", symbol="€")
    foreign_treatment = make_treatment(other, "WITHHOLDING", Decimal("15.00"))
    client.force_login(owner)

    list_response = client.get(reverse("tax:treatment_list"))
    assert foreign_treatment.name not in list_response.content.decode()
    assert client.get(reverse("tax:treatment_edit", args=[foreign_treatment.pk])).status_code == 404
    assert (
        client.post(reverse("tax:treatment_archive", args=[foreign_treatment.pk])).status_code
        == 404
    )
    response = client.post(
        reverse("accounts:create"),
        {
            "name": "Forged taxable term",
            "account_type": "FIXED_TERM",
            "currency": currency.pk,
            "return_tax_treatment": foreign_treatment.pk,
            "fixed_principal": "1000.00",
            "fixed_start_date": "2026-01-01",
            "fixed_maturity_date": "2027-01-01",
            "fixed_annual_rate_percent": "3.00",
            "fixed_interest_method": "SIMPLE",
            "fixed_interest_payment_method": "AT_MATURITY",
            "fixed_interest_destination": "CAPITALIZED",
            "fixed_maturity_instruction": "UNDECIDED",
        },
    )
    assert response.status_code == 200
    assert not FinancialAccount.objects.filter(owner=owner, name="Forged taxable term").exists()
