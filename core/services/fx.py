from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils import timezone

from core.models import Currency, ExchangeRate


class MissingExchangeRate(ValidationError):
    pass


def _currency(value):
    return value if isinstance(value, Currency) else Currency.objects.get(code=str(value).upper())


def get_fx_rate(from_currency, to_currency, as_of_date: date | None = None):
    """Return units of ``to_currency`` for one unit of ``from_currency``.

    Stored rates use the convention ``1 base_currency = rate quote_currency``.
    Direct and inverse historical rates are both supported, always using a rate
    dated on or before the requested date.
    """
    source = _currency(from_currency)
    target = _currency(to_currency)
    if source.pk == target.pk:
        return Decimal(1)
    cutoff = as_of_date or timezone.localdate()
    direct = (
        ExchangeRate.objects.filter(base_currency=source, quote_currency=target, date__lte=cutoff)
        .order_by("-date", "source", "-created_at")
        .first()
    )
    inverse = (
        ExchangeRate.objects.filter(base_currency=target, quote_currency=source, date__lte=cutoff)
        .order_by("-date", "source", "-created_at")
        .first()
    )
    if direct and (inverse is None or direct.date >= inverse.date):
        return direct.rate
    if inverse:
        return Decimal(1) / inverse.rate
    raise MissingExchangeRate(
        f"No FX rate available for {source.code} -> {target.code} on or before {cutoff}."
    )


def convert_currency(amount, from_currency, to_currency, as_of_date=None):
    return Decimal(amount) * get_fx_rate(from_currency, to_currency, as_of_date)
