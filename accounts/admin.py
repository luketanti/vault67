from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import FinancialAccount, FixedTermDetails, Institution, User

admin.site.register(User, UserAdmin)


@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "institution_type", "active")
    search_fields = ("name",)
    list_filter = ("institution_type", "active")


@admin.register(FinancialAccount)
class FinancialAccountAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "owner",
        "account_type",
        "currency",
        "savings_annual_interest_rate",
        "active",
    )
    search_fields = ("name",)
    list_filter = ("account_type", "active", "currency")


@admin.register(FixedTermDetails)
class FixedTermDetailsAdmin(admin.ModelAdmin):
    list_display = (
        "account",
        "principal",
        "annual_interest_rate",
        "start_date",
        "maturity_date",
        "calculated_status",
    )
    search_fields = ("account__name", "account__owner__username")
    list_filter = ("interest_method", "compounding_frequency", "maturity_date")
    ordering = ("maturity_date",)

    @admin.display(description="Status")
    def calculated_status(self, obj):
        return obj.fixed_term_status.title()
