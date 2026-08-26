from django.contrib import admin

from .models import InvestmentTransaction, Security, SecurityPrice


@admin.register(Security)
class SecurityAdmin(admin.ModelAdmin):
    list_display = ("symbol", "name", "security_type", "exchange", "currency", "active")
    list_filter = ("security_type", "currency", "active")
    search_fields = ("symbol", "name", "isin", "exchange")
    ordering = ("symbol", "exchange")


@admin.register(SecurityPrice)
class SecurityPriceAdmin(admin.ModelAdmin):
    list_display = ("security", "date", "price", "currency", "source")
    list_filter = ("source", "currency", "date")
    search_fields = ("security__symbol", "security__name")
    ordering = ("-date", "security__symbol")


@admin.register(InvestmentTransaction)
class InvestmentTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "trade_date",
        "transaction_type",
        "account",
        "security",
        "quantity",
        "gross_amount",
        "currency",
    )
    list_filter = ("transaction__transaction_type", "account", "currency")
    search_fields = ("security__symbol", "security__name", "transaction__reference")
    ordering = ("-transaction__transaction_date", "-transaction_id")
    list_select_related = ("transaction", "account", "security", "currency")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
