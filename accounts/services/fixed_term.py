from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import QuerySet

from ledger.calculations.interest import calculate_compound_interest, calculate_simple_interest


@dataclass(frozen=True)
class FixedTermProjection:
    principal: Decimal
    gross_interest: Decimal
    maturity_value: Decimal
    duration_days: int


@dataclass(frozen=True)
class FixedTermProgress:
    accrued_interest: Decimal
    days_elapsed: int
    days_remaining: int
    progress_percent: Decimal


def calculate_fixed_term_projection(
    principal: Decimal,
    annual_interest_rate: Decimal,
    start_date: date,
    maturity_date: date,
    calculation_method: str,
    compounding_frequency: str | None = None,
) -> FixedTermProjection:
    """Project gross interest on ACT/365 without rounding intermediate values.

    Rates are decimal fractions (``0.0325`` means 3.25%). ACT/365 always
    divides actual elapsed calendar days by 365, including across leap years.
    """
    if principal <= 0:
        raise ValueError("principal must be positive")
    if annual_interest_rate < 0:
        raise ValueError("annual_interest_rate must not be negative")
    if maturity_date <= start_date:
        raise ValueError("maturity_date must be after start_date")
    method = calculation_method.upper()
    if method == "SIMPLE":
        interest = calculate_simple_interest(
            principal, annual_interest_rate, start_date, maturity_date
        )
    elif method == "COMPOUND":
        if not compounding_frequency:
            raise ValueError("compound interest requires compounding_frequency")
        interest = calculate_compound_interest(
            principal,
            annual_interest_rate,
            start_date,
            maturity_date,
            compounding_frequency.lower(),
        )
    else:
        raise ValueError("unsupported interest calculation method")
    return FixedTermProjection(
        principal=principal,
        gross_interest=interest,
        maturity_value=principal + interest,
        duration_days=(maturity_date - start_date).days,
    )


def calculate_fixed_term_progress(details, as_of_date: date) -> FixedTermProgress:
    duration_days = (details.maturity_date - details.start_date).days
    if as_of_date < details.start_date:
        return FixedTermProgress(Decimal(0), 0, duration_days, Decimal(0))
    effective_date = min(as_of_date, details.maturity_date)
    elapsed = (effective_date - details.start_date).days
    accrued_interest = Decimal(0)
    if elapsed:
        accrued_interest = calculate_fixed_term_projection(
            details.principal,
            details.annual_interest_rate,
            details.start_date,
            effective_date,
            details.interest_method,
            details.compounding_frequency or None,
        ).gross_interest
    remaining = max((details.maturity_date - as_of_date).days, 0)
    percent = min(Decimal(elapsed) * Decimal(100) / Decimal(duration_days), Decimal(100))
    return FixedTermProgress(accrued_interest, elapsed, remaining, percent)


def get_fixed_term_status(details, as_of_date: date) -> str:
    if not details.account.active or details.account.closing_date:
        return "CLOSED"
    if as_of_date < details.start_date:
        return "PLANNED"
    if as_of_date < details.maturity_date:
        return "ACTIVE"
    return "MATURED"


def get_upcoming_maturities(owner, as_of_date: date, days: int = 30) -> QuerySet:
    from accounts.models import FixedTermDetails

    return FixedTermDetails.objects.filter(
        account__owner=owner,
        account__active=True,
        maturity_date__gte=as_of_date,
        maturity_date__lte=as_of_date + timedelta(days=days),
    ).select_related("account", "account__currency")
