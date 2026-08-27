from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from accounts.models import FinancialAccount, FixedTermDetails, User
from core.models import Currency, ExchangeRate
from investments.models import Security
from investments.services.transactions import create_investment_transaction
from ledger.models import Transaction
from ledger.services import create_deposit
from tax.models import (
    TaxAdjustment,
    TaxAllowance,
    TaxCategory,
    TaxDeduction,
    TaxRule,
    TaxYear,
)
from tax.services.aggregation import build_tax_year_summary


@pytest.fixture
def tax_data(db):
    user = User.objects.create_user(username="annual-tax", password="password")
    eur = Currency.objects.create(code="EUR", name="Euro", symbol="€")
    usd = Currency.objects.create(code="USD", name="US Dollar", symbol="$")
    tax_year = TaxYear.objects.create(
        owner=user,
        name="2026",
        jurisdiction="MT",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        reporting_currency=eur,
    )
    savings = FinancialAccount.objects.create(
        owner=user,
        name="Savings",
        account_type=FinancialAccount.Type.SAVINGS,
        currency=eur,
    )
    brokerage = FinancialAccount.objects.create(
        owner=user,
        name="Brokerage",
        account_type=FinancialAccount.Type.BROKERAGE,
        currency=eur,
    )
    security = Security.objects.create(
        symbol="TAX",
        name="Tax Test ETF",
        security_type=Security.Type.ETF,
        currency=eur,
        exchange="XETRA",
    )
    return user, eur, usd, tax_year, savings, brokerage, security


def add_rule(tax_data, category, rate):
    user, _eur, _usd, tax_year, *_rest = tax_data
    return TaxRule.objects.create(
        owner=user,
        tax_year=tax_year,
        jurisdiction=tax_year.jurisdiction,
        name=f"{category} {rate}%",
        rule_type=TaxRule.Type.FLAT_RATE,
        category=category,
        rate=Decimal(rate),
    )


def trade(tax_data, kind, trade_date, quantity, price, security=None, **kwargs):
    user, eur, _usd, _year, _savings, brokerage, default_security = tax_data
    return create_investment_transaction(
        owner=user,
        account=brokerage,
        security=security or default_security,
        transaction_type=kind,
        trade_date=trade_date,
        quantity=Decimal(quantity),
        price_per_unit=Decimal(price),
        gross_amount=Decimal(quantity) * Decimal(price),
        fees=Decimal(kwargs.get("fees", 0)),
        taxes=Decimal(kwargs.get("taxes", 0)),
        currency=eur,
    )


@pytest.mark.django_db
def test_tax_year_validation_overlap_and_status_change(tax_data):
    user, eur, _usd, tax_year, *_rest = tax_data
    with pytest.raises(ValidationError):
        TaxYear(
            owner=user,
            name="reversed",
            jurisdiction="GB",
            start_date=date(2026, 12, 31),
            end_date=date(2026, 1, 1),
            reporting_currency=eur,
        ).full_clean()
    with pytest.raises(ValidationError, match="overlaps"):
        TaxYear(
            owner=user,
            name="overlap",
            jurisdiction="MT",
            start_date=date(2026, 6, 1),
            end_date=date(2027, 5, 31),
            reporting_currency=eur,
        ).full_clean()
    tax_year.status = TaxYear.Status.CLOSED
    tax_year.save()
    assert tax_year.status == TaxYear.Status.CLOSED


@pytest.mark.django_db
def test_interest_date_boundaries_and_projected_interest_excluded(tax_data):
    user, eur, _usd, tax_year, savings, *_rest = tax_data
    for when, amount in (
        (date(2025, 12, 31), 1),
        (date(2026, 1, 1), 10),
        (date(2026, 12, 31), 20),
        (date(2027, 1, 1), 2),
    ):
        create_deposit(
            user,
            savings,
            Decimal(amount),
            when,
            f"Interest {when}",
            transaction_type=Transaction.Type.INTEREST,
        )
    fixed = FinancialAccount.objects.create(
        owner=user,
        name="Projected term",
        account_type=FinancialAccount.Type.FIXED_TERM,
        currency=eur,
    )
    FixedTermDetails.objects.create(
        account=fixed,
        principal=Decimal(10000),
        start_date=date(2026, 1, 1),
        maturity_date=date(2027, 1, 1),
        annual_interest_rate=Decimal("0.05"),
        interest_method=FixedTermDetails.InterestMethod.SIMPLE,
        interest_payment_method=FixedTermDetails.PaymentMethod.AT_MATURITY,
        interest_destination=FixedTermDetails.InterestDestination.CAPITALIZED,
        maturity_instruction=FixedTermDetails.MaturityInstruction.UNDECIDED,
    )
    summary = build_tax_year_summary(tax_year)
    assert summary.gross_interest == Decimal(30)
    assert len(summary.interest_lines) == 2


@pytest.mark.django_db
def test_dividend_gross_withholding_and_net_are_distinct(tax_data):
    user, eur, _usd, tax_year, _savings, brokerage, security = tax_data
    create_investment_transaction(
        owner=user,
        account=brokerage,
        security=security,
        transaction_type=Transaction.Type.DIVIDEND,
        trade_date=date(2026, 3, 15),
        gross_amount=Decimal(100),
        taxes=Decimal(15),
        fees=Decimal(0),
        currency=eur,
    )
    summary = build_tax_year_summary(tax_year)
    assert summary.gross_dividends == Decimal(100)
    assert summary.tax_withheld == Decimal(15)
    assert summary.dividend_lines[0].net_original == Decimal(85)


@pytest.mark.django_db
def test_realized_gains_and_losses_are_separate_and_use_trade_date(tax_data):
    _user, eur, _usd, tax_year, _savings, _brokerage, _security = tax_data
    loss_security = Security.objects.create(
        symbol="LOSS",
        name="Loss ETF",
        security_type=Security.Type.ETF,
        currency=eur,
        exchange="XETRA",
    )
    trade(tax_data, Transaction.Type.BUY, date(2025, 12, 1), 10, 100)
    trade(tax_data, Transaction.Type.SELL, date(2026, 2, 1), 5, 150)
    trade(tax_data, Transaction.Type.BUY, date(2026, 1, 2), 10, 100, security=loss_security)
    trade(tax_data, Transaction.Type.SELL, date(2026, 4, 1), 5, 80, security=loss_security)
    summary = build_tax_year_summary(tax_year)
    assert summary.realized_capital_gains == Decimal(250)
    assert summary.realized_capital_losses == Decimal(-100)
    assert summary.net_realized_gain == Decimal(150)


@pytest.mark.django_db
def test_flat_rule_allowance_and_deduction_order(tax_data):
    user, eur, _usd, tax_year, savings, *_rest = tax_data
    create_deposit(
        user,
        savings,
        Decimal(1000),
        date(2026, 1, 10),
        "Interest",
        transaction_type=Transaction.Type.INTEREST,
    )
    TaxAllowance.objects.create(
        owner=user,
        tax_year=tax_year,
        name="Interest allowance",
        category=TaxCategory.INTEREST,
        amount=Decimal(100),
        currency=eur,
    )
    TaxDeduction.objects.create(
        owner=user,
        tax_year=tax_year,
        name="Expense",
        category=TaxCategory.INTEREST,
        amount=Decimal(100),
        currency=eur,
        date=date(2026, 2, 1),
    )
    add_rule(tax_data, TaxCategory.INTEREST, "15")
    summary = build_tax_year_summary(tax_year)
    interest = summary.categories[0]
    assert interest.taxable_amount == Decimal(800)
    assert interest.estimated_tax == Decimal(120)


@pytest.mark.django_db
def test_capital_gain_allowance_does_not_make_taxable_negative(tax_data):
    user, eur, _usd, tax_year, *_rest = tax_data
    TaxAdjustment.objects.create(
        owner=user,
        tax_year=tax_year,
        category=TaxCategory.CAPITAL_GAIN,
        description="Manual gain",
        amount=Decimal(5000),
        currency=eur,
        date=date(2026, 6, 1),
    )
    TaxAllowance.objects.create(
        owner=user,
        tax_year=tax_year,
        name="Capital allowance",
        category=TaxCategory.CAPITAL_GAIN,
        amount=Decimal(1000),
        currency=eur,
    )
    add_rule(tax_data, TaxCategory.CAPITAL_GAIN, "15")
    summary = build_tax_year_summary(tax_year)
    capital = next(row for row in summary.categories if row.category == TaxCategory.CAPITAL_GAIN)
    assert capital.taxable_amount == Decimal(4000)
    assert capital.estimated_tax == Decimal(600)


@pytest.mark.django_db
def test_threshold_allowance_and_deduction_rules_are_traced_in_priority_order(tax_data):
    user, eur, _usd, tax_year, *_rest = tax_data
    TaxAdjustment.objects.create(
        owner=user,
        tax_year=tax_year,
        category=TaxCategory.OTHER_INCOME,
        description="Other taxable income",
        amount=Decimal(1000),
        currency=eur,
        date=date(2026, 5, 1),
    )
    for priority, rule_type, field in (
        (10, TaxRule.Type.THRESHOLD, {"threshold": Decimal(100)}),
        (20, TaxRule.Type.ALLOWANCE, {"fixed_amount": Decimal(100)}),
        (30, TaxRule.Type.DEDUCTION, {"fixed_amount": Decimal(100)}),
        (40, TaxRule.Type.FLAT_RATE, {"rate": Decimal(10)}),
    ):
        TaxRule.objects.create(
            owner=user,
            tax_year=tax_year,
            jurisdiction="MT",
            name=f"Rule {priority}",
            rule_type=rule_type,
            category=TaxCategory.OTHER_INCOME,
            priority=priority,
            **field,
        )
    summary = build_tax_year_summary(tax_year)
    other = next(row for row in summary.categories if row.category == TaxCategory.OTHER_INCOME)
    assert other.taxable_amount == Decimal(700)
    assert other.estimated_tax == Decimal(70)
    assert [trace.rule.priority for trace in other.applied_rules] == [10, 20, 30, 40]


@pytest.mark.django_db
def test_withholding_credit_due_and_overwithholding_refund(tax_data):
    user, eur, _usd, tax_year, *_rest = tax_data
    TaxAdjustment.objects.create(
        owner=user,
        tax_year=tax_year,
        category=TaxCategory.INTEREST,
        description="Interest",
        amount=Decimal(1000),
        currency=eur,
        date=date(2026, 5, 1),
    )
    withheld = TaxAdjustment.objects.create(
        owner=user,
        tax_year=tax_year,
        category=TaxCategory.WITHHOLDING_TAX,
        applies_to=TaxCategory.INTEREST,
        description="Actual withholding",
        amount=Decimal(150),
        currency=eur,
        date=date(2026, 5, 1),
    )
    add_rule(tax_data, TaxCategory.INTEREST, "20")
    summary = build_tax_year_summary(tax_year)
    assert summary.estimated_tax_liability == Decimal(200)
    assert summary.tax_withheld == Decimal(150)
    assert summary.estimated_tax_due == Decimal(50)
    withheld.amount = Decimal(230)
    withheld.save()
    summary = build_tax_year_summary(tax_year)
    assert summary.estimated_tax_due == Decimal(0)
    assert summary.estimated_refund_credit == Decimal(30)


@pytest.mark.django_db
def test_historical_fx_and_missing_fx_completeness(tax_data):
    user, eur, usd, tax_year, _savings, *_rest = tax_data
    usd_account = FinancialAccount.objects.create(
        owner=user,
        name="USD savings",
        account_type=FinancialAccount.Type.SAVINGS,
        currency=usd,
    )
    create_deposit(
        user,
        usd_account,
        Decimal(120),
        date(2026, 3, 15),
        "USD interest",
        transaction_type=Transaction.Type.INTEREST,
    )
    missing = build_tax_year_summary(tax_year)
    assert missing.completeness == "INCOMPLETE"
    assert missing.gross_interest == Decimal(0)
    ExchangeRate.objects.create(
        date=date(2026, 3, 15),
        base_currency=eur,
        quote_currency=usd,
        rate=Decimal("1.20"),
    )
    complete = build_tax_year_summary(tax_year)
    assert complete.gross_interest == Decimal(100)


@pytest.mark.django_db
def test_actual_tax_payment_is_separate_from_withholding(tax_data):
    user, _eur, _usd, tax_year, savings, *_rest = tax_data
    from ledger.services import create_withdrawal

    create_withdrawal(
        user,
        savings,
        Decimal(75),
        date(2026, 9, 1),
        "Tax authority payment",
        transaction_type=Transaction.Type.TAX,
    )
    summary = build_tax_year_summary(tax_year)
    assert summary.tax_paid == Decimal(75)
    assert summary.tax_withheld == Decimal(0)
    assert summary.tax_payment_lines[0].description == "Tax authority payment"


@pytest.mark.django_db
def test_filed_year_rejects_item_edits_and_new_forms(client, tax_data):
    user, eur, _usd, tax_year, *_rest = tax_data
    deduction = TaxDeduction.objects.create(
        owner=user,
        tax_year=tax_year,
        name="Before filing",
        category=TaxCategory.INTEREST,
        amount=Decimal(10),
        currency=eur,
        date=date(2026, 1, 1),
    )
    tax_year.status = TaxYear.Status.FILED
    tax_year.save()
    deduction.amount = Decimal(20)
    with pytest.raises(ValidationError, match="Filed"):
        deduction.save()
    client.force_login(user)
    assert client.get(reverse("tax:deduction_create", args=[tax_year.pk])).status_code == 403
    assert (
        client.get(reverse("tax:deduction_edit", args=[tax_year.pk, deduction.pk])).status_code
        == 403
    )


@pytest.mark.django_db
def test_tax_year_permissions_and_csv_formula_safety(client, tax_data):
    owner, eur, _usd, tax_year, *_rest = tax_data
    deduction = TaxDeduction.objects.create(
        owner=owner,
        tax_year=tax_year,
        name='=HYPERLINK("bad")',
        category=TaxCategory.INTEREST,
        amount=Decimal(10),
        currency=eur,
        date=date(2026, 1, 1),
    )
    allowance = TaxAllowance.objects.create(
        owner=owner,
        tax_year=tax_year,
        name="Private allowance",
        category=TaxCategory.INTEREST,
        amount=Decimal(5),
        currency=eur,
    )
    rule = TaxRule.objects.create(
        owner=owner,
        tax_year=tax_year,
        jurisdiction="MT",
        name="Private rule",
        rule_type=TaxRule.Type.FLAT_RATE,
        category=TaxCategory.INTEREST,
        rate=Decimal(10),
    )
    outsider = User.objects.create_user(username="tax-outsider", password="password")
    other_year = TaxYear.objects.create(
        owner=outsider,
        name="Private 2026",
        jurisdiction="MT",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        reporting_currency=eur,
    )
    client.force_login(outsider)
    assert client.get(reverse("tax:year_detail", args=[tax_year.pk])).status_code == 404
    assert client.get(reverse("tax:year_export", args=[tax_year.pk])).status_code == 404
    assert (
        client.get(reverse("tax:deduction_edit", args=[tax_year.pk, deduction.pk])).status_code
        == 404
    )
    assert (
        client.get(reverse("tax:allowance_edit", args=[tax_year.pk, allowance.pk])).status_code
        == 404
    )
    assert client.get(reverse("tax:rule_edit", args=[tax_year.pk, rule.pk])).status_code == 404
    client.force_login(owner)
    detail = client.get(reverse("tax:year_detail", args=[tax_year.pk]))
    assert detail.status_code == 200
    assert "Explainable category calculation" in detail.content.decode()
    export = client.get(reverse("tax:year_export", args=[tax_year.pk]))
    assert export.status_code == 200
    assert "'=HYPERLINK" in export.content.decode()
    assert other_year.name not in client.get(reverse("tax:year_list")).content.decode()
