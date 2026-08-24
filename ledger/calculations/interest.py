from datetime import date
from decimal import Decimal


def calculate_simple_interest(
    principal: Decimal, annual_rate: Decimal, start_date: date, end_date: date
) -> Decimal:
    """Return unrounded simple interest using an actual/365 day count and decimal rate (0.05 = 5%)."""
    if end_date < start_date:
        raise ValueError("end_date must not precede start_date")
    return principal * annual_rate * Decimal((end_date - start_date).days) / Decimal(365)


def calculate_compound_interest(
    principal: Decimal,
    annual_rate: Decimal,
    start_date: date,
    end_date: date,
    compounding_frequency: str,
) -> Decimal:
    """Return unrounded compound interest using whole fractional annual periods (actual/365)."""
    periods = {
        "daily": Decimal(365),
        "monthly": Decimal(12),
        "quarterly": Decimal(4),
        "annually": Decimal(1),
    }
    if compounding_frequency not in periods:
        raise ValueError("Unsupported compounding frequency")
    if end_date < start_date:
        raise ValueError("end_date must not precede start_date")
    frequency = periods[compounding_frequency]
    years = Decimal((end_date - start_date).days) / Decimal(365)
    return principal * ((Decimal(1) + annual_rate / frequency) ** (frequency * years) - Decimal(1))
