from django.urls import path

from . import views

app_name = "tax"
urlpatterns = [
    path("", views.TaxYearListView.as_view(), name="year_list"),
    path("years/new/", views.TaxYearCreateView.as_view(), name="year_create"),
    path("years/<int:pk>/", views.TaxYearDetailView.as_view(), name="year_detail"),
    path("years/<int:pk>/edit/", views.TaxYearUpdateView.as_view(), name="year_edit"),
    path("years/<int:pk>/export/", views.export_tax_year_csv, name="year_export"),
    path("years/<int:tax_year_pk>/deductions/new/", views.TaxDeductionCreateView.as_view(), name="deduction_create"),
    path("years/<int:tax_year_pk>/deductions/<int:pk>/edit/", views.TaxDeductionUpdateView.as_view(), name="deduction_edit"),
    path("years/<int:tax_year_pk>/allowances/new/", views.TaxAllowanceCreateView.as_view(), name="allowance_create"),
    path("years/<int:tax_year_pk>/allowances/<int:pk>/edit/", views.TaxAllowanceUpdateView.as_view(), name="allowance_edit"),
    path("years/<int:tax_year_pk>/adjustments/new/", views.TaxAdjustmentCreateView.as_view(), name="adjustment_create"),
    path("years/<int:tax_year_pk>/adjustments/<int:pk>/edit/", views.TaxAdjustmentUpdateView.as_view(), name="adjustment_edit"),
    path("years/<int:tax_year_pk>/rules/new/", views.TaxRuleCreateView.as_view(), name="rule_create"),
    path("years/<int:tax_year_pk>/rules/<int:pk>/edit/", views.TaxRuleUpdateView.as_view(), name="rule_edit"),
    path("years/<int:tax_year_pk>/<str:kind>/<int:pk>/archive/", views.archive_tax_item, name="item_archive"),
    path("treatments/", views.TaxTreatmentListView.as_view(), name="treatment_list"),
    path("treatments/new/", views.TaxTreatmentCreateView.as_view(), name="treatment_create"),
    path("treatments/<int:pk>/edit/", views.TaxTreatmentUpdateView.as_view(), name="treatment_edit"),
    path("treatments/<int:pk>/archive/", views.archive_tax_treatment, name="treatment_archive"),
]
