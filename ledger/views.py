from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import FormView, ListView, TemplateView

from accounts.models import FinancialAccount

from .forms import EntryForm, TransactionImportForm, TransferForm
from .imports import TransactionImportError, import_transactions
from .models import Transaction, TransactionEntry
from .services import (
    create_deposit,
    create_transfer,
    create_withdrawal,
    delete_account_transactions,
    delete_transaction,
)


class TransactionListView(LoginRequiredMixin, ListView):
    template_name = "ledger/list.html"
    context_object_name = "transactions"
    paginate_by = 25

    def get_queryset(self):
        return Transaction.objects.filter(owner=self.request.user).prefetch_related(
            "entries__account"
        )


class EntryCreateView(LoginRequiredMixin, FormView):
    template_name = "form.html"
    form_class = EntryForm
    operation = "deposit"
    title = "Add transaction"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = self.title
        return context

    def form_valid(self, form):
        fn, typ = (
            (
                create_deposit,
                Transaction.Type.INCOME if self.operation == "income" else Transaction.Type.DEPOSIT,
            )
            if self.operation in ("deposit", "income")
            else (
                create_withdrawal,
                (
                    Transaction.Type.EXPENSE
                    if self.operation == "expense"
                    else Transaction.Type.WITHDRAWAL
                ),
            )
        )
        fn(
            self.request.user,
            form.cleaned_data["account"],
            form.cleaned_data["amount"],
            form.cleaned_data["transaction_date"],
            form.cleaned_data["description"],
            typ,
        )
        messages.success(self.request, "Transaction recorded.")
        return redirect("ledger:list")


class TransferCreateView(LoginRequiredMixin, FormView):
    template_name = "form.html"
    form_class = TransferForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        create_transfer(
            self.request.user,
            form.cleaned_data["source"],
            form.cleaned_data["destination"],
            form.cleaned_data["amount"],
            form.cleaned_data["transaction_date"],
            form.cleaned_data["description"],
        )
        messages.success(self.request, "Transfer recorded.")
        return redirect("ledger:list")


class TransactionImportView(LoginRequiredMixin, FormView):
    template_name = "ledger/import.html"
    form_class = TransactionImportForm

    def get_account(self):
        if not hasattr(self, "account"):
            self.account = get_object_or_404(
                FinancialAccount.objects.select_related("currency"),
                pk=self.kwargs["account_pk"],
                owner=self.request.user,
            )
        return self.account

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["account"] = self.get_account()
        return context

    def form_valid(self, form):
        try:
            count = import_transactions(
                self.request.user, self.get_account(), form.cleaned_data["csv_file"]
            )
        except TransactionImportError as exc:
            form.add_error("csv_file", str(exc))
            return self.form_invalid(form)
        messages.success(self.request, f"Imported {count} transaction{'s' if count != 1 else ''}.")
        return redirect("accounts:detail", pk=self.get_account().pk)


class TransactionDeleteView(LoginRequiredMixin, TemplateView):
    template_name = "ledger/transaction_confirm_delete.html"

    def get_transaction(self):
        if not hasattr(self, "entry_transaction"):
            self.entry_transaction = get_object_or_404(
                Transaction.objects.prefetch_related("entries__account"),
                pk=self.kwargs["pk"],
                owner=self.request.user,
            )
        return self.entry_transaction

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["transaction"] = self.get_transaction()
        context["cancel_url"] = reverse("ledger:list")
        return context

    def post(self, request, *args, **kwargs):
        entry_transaction = self.get_transaction()
        description = entry_transaction.description
        delete_transaction(request.user, entry_transaction)
        messages.success(request, f'Deleted transaction "{description}".')
        return redirect("ledger:list")


class AccountTransactionsDeleteView(LoginRequiredMixin, TemplateView):
    template_name = "ledger/account_transactions_confirm_delete.html"

    def get_account(self):
        if not hasattr(self, "account"):
            self.account = get_object_or_404(
                FinancialAccount.objects.select_related("currency"),
                pk=self.kwargs["account_pk"],
                owner=self.request.user,
            )
        return self.account

    def get_transactions(self):
        return Transaction.objects.filter(
            owner=self.request.user, entries__account=self.get_account()
        ).distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        transactions = self.get_transactions()
        context["account"] = self.get_account()
        context["transaction_count"] = transactions.count()
        context["affects_other_accounts"] = (
            TransactionEntry.objects.filter(transaction__in=transactions)
            .exclude(account=self.get_account())
            .exists()
        )
        return context

    def post(self, request, *args, **kwargs):
        account = self.get_account()
        count = delete_account_transactions(request.user, account)
        messages.success(
            request,
            f"Deleted {count} transaction{'s' if count != 1 else ''} from {account.name}.",
        )
        return redirect("accounts:detail", pk=account.pk)
