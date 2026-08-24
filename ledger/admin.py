from django.contrib import admin

from .models import Transaction, TransactionEntry


class EntryInline(admin.TabularInline):
    model = TransactionEntry
    extra = 0


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("transaction_date", "description", "owner", "transaction_type")
    search_fields = ("description", "reference")
    list_filter = ("transaction_type",)
    inlines = [EntryInline]


@admin.register(TransactionEntry)
class EntryAdmin(admin.ModelAdmin):
    list_display = ("transaction", "account", "amount", "currency")
    list_filter = ("currency",)
