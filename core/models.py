from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Currency(TimeStampedModel):
    code = models.CharField(max_length=3, unique=True)
    name = models.CharField(max_length=64)
    symbol = models.CharField(max_length=8)
    decimal_places = models.PositiveSmallIntegerField(default=2)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.code


class ExchangeRate(TimeStampedModel):
    date = models.DateField()
    base_currency = models.ForeignKey(Currency, on_delete=models.PROTECT, related_name="base_rates")
    quote_currency = models.ForeignKey(
        Currency, on_delete=models.PROTECT, related_name="quote_rates"
    )
    rate = models.DecimalField(max_digits=24, decimal_places=12)
    source = models.CharField(max_length=64, default="manual")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["date", "base_currency", "quote_currency", "source"], name="unique_fx_rate"
            ),
            models.CheckConstraint(
                condition=~models.Q(base_currency=models.F("quote_currency")),
                name="fx_currencies_differ",
            ),
            models.CheckConstraint(condition=models.Q(rate__gt=0), name="fx_rate_positive"),
        ]
        ordering = ["-date"]
