from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import FinancialAccount, Institution, User

admin.site.register(User, UserAdmin)


@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "institution_type", "active")
    search_fields = ("name",)
    list_filter = ("institution_type", "active")


@admin.register(FinancialAccount)
class FinancialAccountAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "account_type", "currency", "active")
    search_fields = ("name",)
    list_filter = ("account_type", "active", "currency")
