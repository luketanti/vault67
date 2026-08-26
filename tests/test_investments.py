from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from accounts.models import FinancialAccount, User
from core.models import Currency, ExchangeRate
from core.services.fx import MissingExchangeRate, get_fx_rate
from investments.models import InvestmentTransaction, Security, SecurityPrice
from investments.services.cost_basis import calculate_realized_gain
from investments.services.holdings import calculate_holding
from investments.services.pricing import get_latest_price
from investments.services.transactions import create_investment_transaction
from investments.services.valuation import calculate_portfolio_value
from ledger.models import Transaction, TransactionEntry
from ledger.services import account_balance, create_deposit


@pytest.fixture
def investment_data(db):
    user = User.objects.create_user(username="investor", password="password")
    eur = Currency.objects.create(code="EUR", name="Euro", symbol="€")
    usd = Currency.objects.create(code="USD", name="US Dollar", symbol="$")
    account = FinancialAccount.objects.create(
        owner=user, name="Broker", account_type=FinancialAccount.Type.BROKERAGE, currency=eur
    )
    security = Security.objects.create(
        symbol="V67",
        name="Vault ETF",
        security_type=Security.Type.ETF,
        currency=eur,
        exchange="XETRA",
    )
    return user, eur, usd, account, security


def post_trade(data, kind, quantity, price, **kwargs):
    user, eur, _usd, account, security = data
    return create_investment_transaction(
        owner=user,
        account=account,
        security=security,
        transaction_type=kind,
        trade_date=kwargs.pop("trade_date", date(2026, 1, 1)),
        quantity=Decimal(quantity),
        price_per_unit=Decimal(price),
        gross_amount=Decimal(quantity) * Decimal(price),
        fees=Decimal(kwargs.pop("fees", "0")),
        taxes=Decimal(kwargs.pop("taxes", "0")),
        currency=eur,
        **kwargs,
    )


@pytest.mark.django_db
def test_holdings_quantity_and_weighted_average_cost(investment_data):
    post_trade(investment_data, Transaction.Type.BUY, "10", "100")
    post_trade(investment_data, Transaction.Type.BUY, "5", "120", trade_date=date(2026, 1, 2))
    post_trade(investment_data, Transaction.Type.SELL, "4", "150", trade_date=date(2026, 1, 3))

    holding = calculate_holding(investment_data[3], investment_data[4])

    assert holding.quantity == Decimal(11)
    assert holding.total_cost_basis == Decimal("1173.333333333333333333333333")
    assert holding.average_cost == Decimal("106.6666666666666666666666666")


@pytest.mark.django_db
def test_weighted_average_partial_sale_and_sell_costs(investment_data):
    post_trade(investment_data, Transaction.Type.BUY, "10", "100")
    post_trade(investment_data, Transaction.Type.BUY, "10", "120", trade_date=date(2026, 1, 2))
    preview = calculate_realized_gain(
        investment_data[3], investment_data[4], Decimal(5), Decimal(750), Decimal(10), Decimal(5)
    )
    post_trade(
        investment_data,
        Transaction.Type.SELL,
        "5",
        "150",
        fees="10",
        taxes="5",
        trade_date=date(2026, 1, 3),
    )
    holding = calculate_holding(investment_data[3], investment_data[4])

    assert preview.allocated_cost_basis == Decimal(550)
    assert preview.net_proceeds == Decimal(735)
    assert preview.gain == Decimal(185)
    assert holding.quantity == Decimal(15)
    assert holding.total_cost_basis == Decimal(1650)
    assert holding.average_cost == Decimal(110)
    assert holding.realized_gain == Decimal(185)


@pytest.mark.django_db
def test_buy_fees_increase_cost_and_cash_decreases(investment_data):
    item = post_trade(investment_data, Transaction.Type.BUY, "10", "100", fees="10")
    holding = calculate_holding(investment_data[3], investment_data[4])
    assert holding.total_cost_basis == Decimal(1010)
    assert holding.average_cost == Decimal(101)
    assert item.transaction.entries.get().amount == Decimal("-1010.0000")
    assert account_balance(investment_data[3]) == Decimal("-1010.0000")


@pytest.mark.django_db
def test_fully_sold_position_still_contributes_realized_gain(investment_data):
    post_trade(investment_data, Transaction.Type.BUY, "5", "100")
    post_trade(
        investment_data,
        Transaction.Type.SELL,
        "5",
        "120",
        fees="10",
        trade_date=date(2026, 1, 2),
    )
    valuation = calculate_portfolio_value(investment_data[3])
    assert valuation.holdings == []
    assert valuation.realized_gain == Decimal(90)


@pytest.mark.django_db
def test_overselling_is_rejected_without_writes(investment_data):
    post_trade(investment_data, Transaction.Type.BUY, "5", "100")
    before = (
        Transaction.objects.count(),
        InvestmentTransaction.objects.count(),
        TransactionEntry.objects.count(),
    )
    with pytest.raises(ValidationError, match="Insufficient holdings"):
        post_trade(investment_data, Transaction.Type.SELL, "6", "120", trade_date=date(2026, 1, 2))
    assert (
        Transaction.objects.count(),
        InvestmentTransaction.objects.count(),
        TransactionEntry.objects.count(),
    ) == before


@pytest.mark.django_db
def test_dividend_posts_net_cash(investment_data):
    user, eur, _usd, account, security = investment_data
    detail = create_investment_transaction(
        owner=user,
        account=account,
        security=security,
        transaction_type=Transaction.Type.DIVIDEND,
        trade_date=date(2026, 2, 1),
        gross_amount=Decimal(100),
        fees=Decimal(1),
        taxes=Decimal(15),
        currency=eur,
    )
    assert detail.net_cash_impact_native == Decimal(84)
    assert account_balance(account) == Decimal("84.0000")


@pytest.mark.django_db
def test_latest_price_never_uses_future_price(investment_data):
    security, eur = investment_data[4], investment_data[1]
    SecurityPrice.objects.create(security=security, date=date(2026, 1, 1), price=100, currency=eur)
    SecurityPrice.objects.create(security=security, date=date(2026, 2, 1), price=110, currency=eur)
    assert get_latest_price(security, date(2026, 1, 15)).price == Decimal(100)


@pytest.mark.django_db
def test_fx_direct_inverse_same_currency_and_missing(investment_data):
    _user, eur, usd, _account, _security = investment_data
    ExchangeRate.objects.create(
        date=date(2026, 1, 1), base_currency=eur, quote_currency=usd, rate=Decimal("1.20")
    )
    assert get_fx_rate(eur, usd, date(2026, 1, 2)) == Decimal("1.20")
    assert get_fx_rate(usd, eur, date(2026, 1, 2)) == Decimal(1) / Decimal("1.20")
    ExchangeRate.objects.create(
        date=date(2026, 2, 1),
        base_currency=usd,
        quote_currency=eur,
        rate=Decimal("0.80"),
    )
    assert get_fx_rate(eur, usd, date(2026, 2, 2)) == Decimal(1) / Decimal("0.80")
    assert get_fx_rate(eur, eur) == Decimal(1)
    gbp = Currency.objects.create(code="GBP", name="Pound", symbol="£")
    with pytest.raises(MissingExchangeRate, match="No FX rate"):
        get_fx_rate(gbp, eur, date(2026, 1, 2))


@pytest.mark.django_db
def test_multi_currency_unrealized_valuation(investment_data):
    user, eur, usd, account, _security = investment_data
    stock = Security.objects.create(
        symbol="USD",
        name="US Stock",
        security_type=Security.Type.STOCK,
        currency=usd,
        exchange="NYSE",
    )
    create_deposit(user, account, Decimal(5000), date(2026, 1, 1), "Funding")
    create_investment_transaction(
        owner=user,
        account=account,
        security=stock,
        transaction_type=Transaction.Type.BUY,
        trade_date=date(2026, 1, 1),
        quantity=Decimal(10),
        price_per_unit=Decimal(100),
        gross_amount=Decimal(1000),
        fees=Decimal(0),
        taxes=Decimal(0),
        currency=usd,
        exchange_rate=Decimal("0.80"),
    )
    SecurityPrice.objects.create(
        security=stock, date=date(2026, 2, 1), price=Decimal(125), currency=usd
    )
    ExchangeRate.objects.create(
        date=date(2026, 2, 1), base_currency=eur, quote_currency=usd, rate=Decimal("1.25")
    )
    value = calculate_portfolio_value(account, date(2026, 2, 1), eur)
    assert value.market_value == Decimal(1000)
    assert value.cost_basis == Decimal(800)
    assert value.unrealized_gain == Decimal(200)
    assert value.unrealized_gain_percent == Decimal("25.00")
    assert value.total_account_value == Decimal("5200.0000")


@pytest.mark.django_db
def test_missing_price_makes_portfolio_explicitly_incomplete(investment_data):
    post_trade(investment_data, Transaction.Type.BUY, "1", "100")
    value = calculate_portfolio_value(investment_data[3], date(2026, 1, 2))
    assert value.complete is False
    assert value.market_value is None
    assert value.total_account_value is None
    assert value.holdings[0].error == "Price unavailable for V67."


@pytest.mark.django_db(transaction=True)
def test_atomic_post_rolls_back_all_records_when_entry_fails(investment_data):
    with (
        patch(
            "investments.services.transactions.TransactionEntry.objects.create",
            side_effect=RuntimeError("forced"),
        ),
        pytest.raises(RuntimeError, match="forced"),
    ):
        post_trade(investment_data, Transaction.Type.BUY, "1", "100")
    assert Transaction.objects.count() == 0
    assert InvestmentTransaction.objects.count() == 0
    assert TransactionEntry.objects.count() == 0


@pytest.mark.django_db
def test_investment_views_enforce_account_ownership(client, investment_data):
    _owner, eur, _usd, account, security = investment_data
    outsider = User.objects.create_user(username="outsider", password="password")
    client.force_login(outsider)
    for name in ("account_detail", "buy", "sell", "dividend"):
        response = client.get(reverse(f"investments:{name}", args=[account.pk]))
        assert response.status_code == 404
    response = client.post(
        reverse("investments:buy", args=[account.pk]),
        data={
            "account": account.pk,
            "security": security.pk,
            "trade_date": "2026-01-01",
            "quantity": "1",
            "price_per_unit": "100",
            "fees": "0",
            "taxes": "0",
            "currency": eur.pk,
        },
    )
    assert response.status_code == 404
    assert InvestmentTransaction.objects.count() == 0


@pytest.mark.django_db
def test_portfolio_only_contains_current_users_accounts(client, investment_data):
    outsider = User.objects.create_user(username="portfolio-outsider", password="password")
    client.force_login(outsider)
    response = client.get(reverse("investments:portfolio"))
    assert response.status_code == 200
    assert investment_data[3].name not in response.content.decode()

    security_response = client.get(
        reverse("investments:security_detail", args=[investment_data[4].pk])
    )
    assert security_response.status_code == 200
    assert investment_data[3].name not in security_response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url_name",
    ["portfolio", "security_list", "price_list", "price_add", "fx_list", "fx_add"],
)
def test_anonymous_users_cannot_access_investment_pages(client, url_name):
    response = client.get(reverse(f"investments:{url_name}"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("dashboard:login"))


@pytest.mark.django_db
def test_gross_amount_mismatch_rolls_back(investment_data):
    user, eur, _usd, account, security = investment_data
    with pytest.raises(ValidationError, match="Gross amount"):
        create_investment_transaction(
            owner=user,
            account=account,
            security=security,
            transaction_type=Transaction.Type.BUY,
            trade_date=date(2026, 1, 1),
            quantity=Decimal(2),
            price_per_unit=Decimal(100),
            gross_amount=Decimal(199),
            currency=eur,
        )
    assert Transaction.objects.count() == 0
