from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("dashboard.urls")),
    path("accounts/", include("accounts.urls")),
    path("ledger/", include("ledger.urls")),
    path("investments/", include("investments.urls")),
    path("tax/", include("tax.urls")),
]
