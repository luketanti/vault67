from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def currency_amount(value, _currency):
    """Format a monetary Decimal with grouping and exactly two places."""
    if value is None:
        return ""
    quantum = Decimal("0.01")
    return f"{Decimal(value).quantize(quantum):,.2f}"
