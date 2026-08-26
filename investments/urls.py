from django.urls import path

from ledger.models import Transaction

from .views import (
    BrokerageDetailView,
    ExchangeRateCreateView,
    ExchangeRateListView,
    InvestmentCreateView,
    PortfolioView,
    PriceCreateView,
    PriceListView,
    SecurityCreateView,
    SecurityDetailView,
    SecurityListView,
)

app_name = "investments"

urlpatterns = [
    path("", PortfolioView.as_view(), name="portfolio"),
    path("accounts/<int:pk>/", BrokerageDetailView.as_view(), name="account_detail"),
    path(
        "accounts/<int:account_pk>/buy/",
        InvestmentCreateView.as_view(transaction_type=Transaction.Type.BUY),
        name="buy",
    ),
    path(
        "accounts/<int:account_pk>/sell/",
        InvestmentCreateView.as_view(transaction_type=Transaction.Type.SELL),
        name="sell",
    ),
    path(
        "accounts/<int:account_pk>/dividend/",
        InvestmentCreateView.as_view(transaction_type=Transaction.Type.DIVIDEND),
        name="dividend",
    ),
    path(
        "accounts/<int:account_pk>/fee/",
        InvestmentCreateView.as_view(transaction_type=Transaction.Type.FEE),
        name="fee",
    ),
    path(
        "accounts/<int:account_pk>/tax/",
        InvestmentCreateView.as_view(transaction_type=Transaction.Type.TAX),
        name="tax",
    ),
    path("securities/", SecurityListView.as_view(), name="security_list"),
    path("securities/add/", SecurityCreateView.as_view(), name="security_add"),
    path("securities/<int:pk>/", SecurityDetailView.as_view(), name="security_detail"),
    path("prices/", PriceListView.as_view(), name="price_list"),
    path("prices/add/", PriceCreateView.as_view(), name="price_add"),
    path("fx/", ExchangeRateListView.as_view(), name="fx_list"),
    path("fx/add/", ExchangeRateCreateView.as_view(), name="fx_add"),
]
