from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views.generic import FormView, ListView

from .forms import EntryForm, TransferForm
from .models import Transaction
from .services import create_deposit, create_transfer, create_withdrawal


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
