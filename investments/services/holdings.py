from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import QuerySet

from ledger.models import Transaction

from ..models import InvestmentTransaction, Security

ZERO = Decimal(0)


@dataclass(frozen=True)
class HoldingSnapshot:
    security: Security
    quantity: Decimal
    total_cost_basis: Decimal
    average_cost: Decimal
    native_currency: object
    base_cost_basis: Decimal
    realized_gain: Decimal
    realized_gain_base: Decimal


def _transactions(account, security=None, as_of_date: date | None = None) -> QuerySet:
    queryset = InvestmentTransaction.objects.filter(account=account).select_related(
        "transaction", "security", "currency", "account__currency"
    )
    if security is not None:
        queryset = queryset.filter(security=security)
    if as_of_date is not None:
        queryset = queryset.filter(transaction__transaction_date__lte=as_of_date)
    return queryset.order_by("transaction__transaction_date", "transaction_id")


def _rate_to_account(item):
    return Decimal(1) if item.currency_id == item.account.currency_id else item.exchange_rate


def _calculate_from_items(account, security, items) -> HoldingSnapshot:
    """Apply weighted-average cost in chronological order.

    Buy fees and taxes increase acquisition cost. A sale removes quantity at
    the prevailing average cost; sale fees and taxes reduce realized proceeds
    and never alter the remaining position's cost basis.
    """
    quantity = ZERO
    native_cost = ZERO
    base_cost = ZERO
    realized = ZERO
    realized_base = ZERO
    for item in items:
        kind = item.transaction.transaction_type
        if kind == Transaction.Type.BUY:
            quantity += item.quantity
            acquisition_cost = item.gross_amount + item.fees + item.taxes
            native_cost += acquisition_cost
            base_cost += acquisition_cost * _rate_to_account(item)
        elif kind == Transaction.Type.SELL:
            if item.quantity > quantity:
                raise ValidationError(
                    f"Historical oversell detected for {security.symbol}: "
                    f"tried to sell {item.quantity} while holding {quantity}."
                )
            native_average = native_cost / quantity
            base_average = base_cost / quantity
            allocated_native = native_average * item.quantity
            allocated_base = base_average * item.quantity
            net_proceeds = item.gross_amount - item.fees - item.taxes
            realized += net_proceeds - allocated_native
            realized_base += net_proceeds * _rate_to_account(item) - allocated_base
            quantity -= item.quantity
            native_cost -= allocated_native
            base_cost -= allocated_base
            if quantity == ZERO:
                native_cost = ZERO
                base_cost = ZERO
    average = native_cost / quantity if quantity else ZERO
    return HoldingSnapshot(
        security=security,
        quantity=quantity,
        total_cost_basis=native_cost,
        average_cost=average,
        native_currency=security.currency,
        base_cost_basis=base_cost,
        realized_gain=realized,
        realized_gain_base=realized_base,
    )


def calculate_holding(account, security, as_of_date=None) -> HoldingSnapshot:
    return _calculate_from_items(account, security, _transactions(account, security, as_of_date))


def calculate_holdings(account, as_of_date=None, include_closed=False):
    items = list(_transactions(account, as_of_date=as_of_date))
    grouped = {}
    securities = {}
    for item in items:
        grouped.setdefault(item.security_id, []).append(item)
        securities[item.security_id] = item.security
    snapshots = [
        _calculate_from_items(account, securities[security_id], grouped[security_id])
        for security_id in sorted(grouped, key=lambda pk: securities[pk].symbol)
    ]
    return snapshots if include_closed else [item for item in snapshots if item.quantity != ZERO]


def calculate_holding_quantity(account, security, as_of_date=None):
    return calculate_holding(account, security, as_of_date).quantity


def calculate_holding_cost_basis(account, security, as_of_date=None):
    return calculate_holding(account, security, as_of_date).total_cost_basis


def calculate_average_cost(account, security, as_of_date=None):
    return calculate_holding(account, security, as_of_date).average_cost
