from django.urls import path

from .views import (
    AccountTransactionsDeleteView,
    EntryCreateView,
    TransactionDeleteView,
    TransactionImportView,
    TransactionListView,
    TransferCreateView,
)

app_name = "ledger"
urlpatterns = [
    path("", TransactionListView.as_view(), name="list"),
    path(
        "deposit/",
        EntryCreateView.as_view(operation="deposit", title="Record deposit"),
        name="deposit",
    ),
    path(
        "withdrawal/",
        EntryCreateView.as_view(operation="withdrawal", title="Record withdrawal"),
        name="withdrawal",
    ),
    path(
        "income/", EntryCreateView.as_view(operation="income", title="Record income"), name="income"
    ),
    path(
        "expense/",
        EntryCreateView.as_view(operation="expense", title="Record expense"),
        name="expense",
    ),
    path("transfer/", TransferCreateView.as_view(), name="transfer"),
    path("import/<int:account_pk>/", TransactionImportView.as_view(), name="import"),
    path("<int:pk>/delete/", TransactionDeleteView.as_view(), name="delete"),
    path(
        "account/<int:account_pk>/delete-all/",
        AccountTransactionsDeleteView.as_view(),
        name="delete-account-transactions",
    ),
]
