from datetime import date

from django.utils import timezone

from ..models import SecurityPrice


def get_latest_price(security, as_of_date: date | None = None):
    """Return the newest price on or before the date; never use future data."""
    cutoff = as_of_date or timezone.localdate()
    return (
        SecurityPrice.objects.filter(security=security, date__lte=cutoff)
        .select_related("currency", "security")
        .order_by("-date", "source", "-created_at")
        .first()
    )
