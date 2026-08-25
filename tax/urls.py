from django.urls import path

from . import views

app_name = "tax"
urlpatterns = [
    path("treatments/", views.TaxTreatmentListView.as_view(), name="treatment_list"),
    path("treatments/new/", views.TaxTreatmentCreateView.as_view(), name="treatment_create"),
    path("treatments/<int:pk>/edit/", views.TaxTreatmentUpdateView.as_view(), name="treatment_edit"),
    path("treatments/<int:pk>/archive/", views.archive_tax_treatment, name="treatment_archive"),
]
