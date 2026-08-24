from datetime import date
from decimal import Decimal

from ledger.calculations.interest import calculate_compound_interest, calculate_simple_interest


def test_simple_interest_uses_decimal_and_leap_day_period():
    assert calculate_simple_interest(
        Decimal(1000), Decimal("0.05"), date(2024, 2, 28), date(2024, 2, 29)
    ) == Decimal(50) / Decimal(365)


def test_compound_interest_annually():
    result = calculate_compound_interest(
        Decimal(1000), Decimal("0.10"), date(2024, 1, 1), date(2025, 1, 1), "annually"
    )
    assert result > Decimal(100)
