from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from core.services.fx import MissingExchangeRate, convert_currency
from ledger.services import account_balance

from .holdings import HoldingSnapshot, calculate_holdings
from .pricing import get_latest_price

ZERO = Decimal(0)


@dataclass
class HoldingValuation:
    holding: HoldingSnapshot
    latest_price: object | None
    market_value_native: Decimal | None
    market_value: Decimal | None
    cost_basis: Decimal | None
    unrealized_gain: Decimal | None
    unrealized_gain_percent: Decimal | None
    allocation_percent: Decimal | None = None
    error: str = ""

    @property
    def security(self):
        return self.holding.security

    @property
    def quantity(self):
        return self.holding.quantity


@dataclass(frozen=True)
class AssetAllocation:
    category: str
    market_value: Decimal
    percentage: Decimal


@dataclass(frozen=True)
class PortfolioValuation:
    account: object
    reporting_currency: object
    holdings: list[HoldingValuation]
    market_value: Decimal | None
    cost_basis: Decimal
    unrealized_gain: Decimal | None
    unrealized_gain_percent: Decimal | None
    realized_gain: Decimal | None
    cash_balance: Decimal | None
    total_account_value: Decimal | None
    complete: bool
    warnings: tuple[str, ...]
    allocation: tuple[AssetAllocation, ...]


def calculate_portfolio_value(account, as_of_date: date | None = None, reporting_currency=None):
    reporting_currency = reporting_currency or account.currency
    all_holdings = calculate_holdings(account, as_of_date, include_closed=True)
    holdings = [holding for holding in all_holdings if holding.quantity != ZERO]
    rows = []
    warnings = []
    total_market = ZERO
    total_cost = ZERO
    realized = sum((holding.realized_gain_base for holding in all_holdings), ZERO)
    complete = True
    for holding in holdings:
        total_cost += holding.base_cost_basis
        price = get_latest_price(holding.security, as_of_date)
        if price is None:
            complete = False
            warning = f"Price unavailable for {holding.security.symbol}."
            warnings.append(warning)
            rows.append(
                HoldingValuation(
                    holding, None, None, None, holding.base_cost_basis, None, None, error=warning
                )
            )
            continue
        native_market = holding.quantity * price.price
        try:
            market = convert_currency(native_market, price.currency, reporting_currency, as_of_date)
            cost = convert_currency(
                holding.base_cost_basis, account.currency, reporting_currency, as_of_date
            )
        except MissingExchangeRate as exc:
            complete = False
            warning = exc.messages[0]
            warnings.append(warning)
            rows.append(
                HoldingValuation(
                    holding,
                    price,
                    native_market,
                    None,
                    holding.base_cost_basis,
                    None,
                    None,
                    error=warning,
                )
            )
            continue
        gain = market - cost
        percent = gain / cost * Decimal(100) if cost else None
        total_market += market
        rows.append(HoldingValuation(holding, price, native_market, market, cost, gain, percent))
    if total_market:
        for row in rows:
            if row.market_value is not None:
                row.allocation_percent = row.market_value / total_market * Decimal(100)
    cash = account_balance(account, as_of_date)
    if reporting_currency.pk != account.currency_id:
        try:
            cash = convert_currency(cash, account.currency, reporting_currency, as_of_date)
            total_cost = convert_currency(
                total_cost, account.currency, reporting_currency, as_of_date
            )
            realized = convert_currency(realized, account.currency, reporting_currency, as_of_date)
        except MissingExchangeRate as exc:
            complete = False
            warnings.append(exc.messages[0])
            cash = None
            total_cost = None
            realized = None
    unrealized = total_market - total_cost if complete else None
    unrealized_percent = (
        unrealized / total_cost * Decimal(100) if unrealized is not None and total_cost else None
    )
    total_value = cash + total_market if complete else None
    allocation_values = {}
    if complete:
        for row in rows:
            label = row.security.get_security_type_display()
            allocation_values[label] = allocation_values.get(label, ZERO) + row.market_value
        if cash > 0:
            allocation_values["Cash"] = cash
    allocation_total = sum(allocation_values.values(), ZERO)
    allocation = tuple(
        AssetAllocation(label, amount, amount / allocation_total * Decimal(100))
        for label, amount in sorted(allocation_values.items())
        if allocation_total
    )
    return PortfolioValuation(
        account=account,
        reporting_currency=reporting_currency,
        holdings=rows,
        market_value=total_market if complete else None,
        cost_basis=total_cost,
        unrealized_gain=unrealized,
        unrealized_gain_percent=unrealized_percent,
        realized_gain=realized,
        cash_balance=cash,
        total_account_value=total_value,
        complete=complete,
        warnings=tuple(dict.fromkeys(warnings)),
        allocation=allocation,
    )
