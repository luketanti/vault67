from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import ValidationError

from .holdings import calculate_holding


@dataclass(frozen=True)
class RealizedGainResult:
    net_proceeds: Decimal
    allocated_cost_basis: Decimal
    gain: Decimal


def calculate_realized_gain(account, security, quantity, gross_proceeds, fees=0, taxes=0):
    holding = calculate_holding(account, security)
    quantity = Decimal(quantity)
    if quantity <= 0:
        raise ValidationError("Quantity must be positive.")
    if quantity > holding.quantity:
        raise ValidationError(
            f"Insufficient holdings to sell {quantity} shares; current holding is "
            f"{holding.quantity}."
        )
    allocated = holding.average_cost * quantity
    net = Decimal(gross_proceeds) - Decimal(fees) - Decimal(taxes)
    return RealizedGainResult(
        net_proceeds=net, allocated_cost_basis=allocated, gain=net - allocated
    )
