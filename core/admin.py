from django.contrib import admin

from .models import Currency, ExchangeRate

admin.site.register(Currency)


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ("date", "base_currency", "quote_currency", "rate", "source")
    list_filter = ("source", "base_currency", "quote_currency", "date")
    search_fields = ("base_currency__code", "quote_currency__code")
    ordering = ("-date", "base_currency__code", "quote_currency__code")
