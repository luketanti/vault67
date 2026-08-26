from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction

from accounts.models import FinancialAccount
from ledger.models import Transaction, TransactionEntry

from ..models import InvestmentTransaction
from .holdings import calculate_holding_quantity

MONEY_QUANTUM = Decimal("0.0001")


def create_investment_transaction(
    *,
    owner,
    account,
    security,
    transaction_type,
    trade_date,
    gross_amount,
    currency,
    quantity=None,
    price_per_unit=None,
    fees=Decimal(0),
    taxes=Decimal(0),
    settlement_date=None,
    exchange_rate=None,
    reference="",
    notes="",
):
    """Atomically post investment metadata and its one brokerage cash entry."""
    if account.owner_id != owner.id:
        raise ValidationError("Account does not belong to user.")
    if account.account_type != FinancialAccount.Type.BROKERAGE:
        raise ValidationError("Investment transactions require a brokerage account.")
    if transaction_type not in {
        Transaction.Type.BUY,
        Transaction.Type.SELL,
        Transaction.Type.DIVIDEND,
        Transaction.Type.FEE,
        Transaction.Type.TAX,
    }:
        raise ValidationError("Unsupported investment transaction type.")
    gross_amount = Decimal(gross_amount)
    fees = Decimal(fees)
    taxes = Decimal(taxes)
    quantity = Decimal(quantity) if quantity is not None else None
    price_per_unit = Decimal(price_per_unit) if price_per_unit is not None else None
    exchange_rate = Decimal(exchange_rate) if exchange_rate is not None else None
    description = f"{transaction_type.title()} {security.symbol}"
    with db_transaction.atomic():
        # Serialize investment posting per account so two concurrent sells cannot
        # both validate against the same pre-sale quantity.
        FinancialAccount.objects.select_for_update().get(pk=account.pk)
        if transaction_type == Transaction.Type.SELL:
            held = calculate_holding_quantity(account, security, trade_date)
            if quantity is None or quantity > held:
                raise ValidationError(
                    f"Insufficient holdings to sell {quantity} shares; current holding is {held}."
                )
        ledger_transaction = Transaction.objects.create(
            owner=owner,
            transaction_date=trade_date,
            description=description,
            transaction_type=transaction_type,
            reference=reference,
            notes=notes,
        )
        detail = InvestmentTransaction(
            transaction=ledger_transaction,
            account=account,
            security=security,
            settlement_date=settlement_date,
            quantity=quantity,
            price_per_unit=price_per_unit,
            gross_amount=gross_amount,
            fees=fees,
            taxes=taxes,
            currency=currency,
            exchange_rate=exchange_rate,
        )
        detail.full_clean()
        detail.save()
        rate = Decimal(1) if currency.pk == account.currency_id else exchange_rate
        cash_amount = (detail.net_cash_impact_native * rate).quantize(MONEY_QUANTUM)
        if cash_amount == 0:
            raise ValidationError("Net cash impact must not be zero.")
        TransactionEntry.objects.create(
            transaction=ledger_transaction,
            account=account,
            amount=cash_amount,
            currency=account.currency,
            exchange_rate=rate,
            base_currency_amount=cash_amount,
            entry_type=transaction_type,
        )
    return detail
