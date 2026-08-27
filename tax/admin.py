from django.contrib import admin

from .models import (
    ReturnTaxTreatment,
    TaxAdjustment,
    TaxAllowance,
    TaxDeduction,
    TaxRule,
    TaxYear,
)


@admin.register(ReturnTaxTreatment)
class ReturnTaxTreatmentAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "treatment_type", "tax_rate", "jurisdiction", "active")
    list_filter = ("treatment_type", "jurisdiction", "active")
    search_fields = ("name", "owner__username")


@admin.register(TaxYear)
class TaxYearAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "jurisdiction", "start_date", "end_date", "status")
    list_filter = ("jurisdiction", "status", "reporting_currency")
    search_fields = ("name", "owner__username", "jurisdiction")
    ordering = ("-start_date",)


@admin.register(TaxRule)
class TaxRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "tax_year", "category", "rule_type", "rate", "priority", "active")
    list_filter = ("rule_type", "category", "jurisdiction", "active")
    search_fields = ("name", "owner__username", "tax_year__name")
    ordering = ("tax_year", "priority", "name")


class TaxYearItemAdmin(admin.ModelAdmin):
    list_filter = ("tax_year__jurisdiction", "tax_year__status", "active")
    search_fields = ("owner__username", "tax_year__name", "name")


@admin.register(TaxDeduction)
class TaxDeductionAdmin(TaxYearItemAdmin):
    list_display = ("name", "owner", "tax_year", "category", "amount", "currency", "date", "active")


@admin.register(TaxAllowance)
class TaxAllowanceAdmin(TaxYearItemAdmin):
    list_display = ("name", "owner", "tax_year", "category", "amount", "currency", "active")


@admin.register(TaxAdjustment)
class TaxAdjustmentAdmin(admin.ModelAdmin):
    list_display = ("description", "owner", "tax_year", "category", "amount", "currency", "date", "active")
    list_filter = ("category", "tax_year__jurisdiction", "tax_year__status", "active")
    search_fields = ("description", "owner__username", "tax_year__name")
