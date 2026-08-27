from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import ValidationError

from ledger.models import Transaction

from ..models import InvestmentTransaction
from .holdings import calculate_holding


@dataclass(frozen=True)
class RealizedGainResult:
    net_proceeds: Decimal
    allocated_cost_basis: Decimal
    gain: Decimal


@dataclass(frozen=True)
class RealizedGainEvent:
    investment_transaction: InvestmentTransaction
    net_proceeds: Decimal
    allocated_cost_basis: Decimal
    gain: Decimal
    net_proceeds_base: Decimal
    allocated_cost_basis_base: Decimal
    gain_base: Decimal


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


def calculate_realized_gain_events(account, as_of_date=None):
    """Replay trades and return an auditable weighted-average result per sale."""
    queryset = InvestmentTransaction.objects.filter(
        account=account,
        transaction__transaction_type__in=[Transaction.Type.BUY, Transaction.Type.SELL],
    ).select_related("transaction", "security", "currency", "account__currency")
    if as_of_date is not None:
        queryset = queryset.filter(transaction__transaction_date__lte=as_of_date)
    positions = {}
    events = []
    for item in queryset.order_by("transaction__transaction_date", "transaction_id"):
        quantity, native_cost, base_cost = positions.get(
            item.security_id, (Decimal(0), Decimal(0), Decimal(0))
        )
        rate = Decimal(1) if item.currency_id == account.currency_id else item.exchange_rate
        if item.transaction_type == Transaction.Type.BUY:
            acquisition = item.gross_amount + item.fees + item.taxes
            positions[item.security_id] = (
                quantity + item.quantity,
                native_cost + acquisition,
                base_cost + acquisition * rate,
            )
            continue
        if item.quantity > quantity or not quantity:
            raise ValidationError(
                f"Capital gain calculation is incomplete because cost basis is unavailable "
                f"for {item.security.symbol}."
            )
        allocated = native_cost / quantity * item.quantity
        allocated_base = base_cost / quantity * item.quantity
        net = item.gross_amount - item.fees - item.taxes
        net_base = net * rate
        events.append(
            RealizedGainEvent(
                investment_transaction=item,
                net_proceeds=net,
                allocated_cost_basis=allocated,
                gain=net - allocated,
                net_proceeds_base=net_base,
                allocated_cost_basis_base=allocated_base,
                gain_base=net_base - allocated_base,
            )
        )
        remaining_quantity = quantity - item.quantity
        positions[item.security_id] = (
            remaining_quantity,
            Decimal(0) if not remaining_quantity else native_cost - allocated,
            Decimal(0) if not remaining_quantity else base_cost - allocated_base,
        )
    return events
