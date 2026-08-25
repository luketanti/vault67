from django.contrib import admin

from .models import ReturnTaxTreatment, TaxRule

admin.site.register(TaxRule)


@admin.register(ReturnTaxTreatment)
class ReturnTaxTreatmentAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "treatment_type", "tax_rate", "jurisdiction", "active")
    list_filter = ("treatment_type", "jurisdiction", "active")
    search_fields = ("name", "owner__username")
