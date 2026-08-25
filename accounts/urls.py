from django.urls import path

from . import views

app_name = "accounts"
urlpatterns = [
    path("", views.AccountListView.as_view(), name="list"),
    path("new/", views.AccountCreateView.as_view(), name="create"),
    path("<int:pk>/export.csv", views.export_account_csv, name="export"),
    path("<int:pk>/", views.AccountDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.AccountUpdateView.as_view(), name="edit"),
    path("<int:pk>/archive/", views.archive_account, name="archive"),
]
