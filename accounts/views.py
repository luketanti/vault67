from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction as db_transaction
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from ledger.exports import export_account_transactions
from ledger.services import account_balance, create_deposit, create_transfer
from tax.services.returns import calculate_return_tax

from .forms import FinancialAccountForm
from .models import FinancialAccount, FixedTermDetails
from .services.fixed_term import (
    calculate_fixed_term_progress,
    calculate_fixed_term_projection,
)


class AccountListView(LoginRequiredMixin, ListView):
    template_name = "accounts/list.html"
    context_object_name = "accounts"

    def get_queryset(self):
        return (
            FinancialAccount.objects.filter(owner=self.request.user, active=True)
            .select_related("currency", "institution", "fixed_term_details", "return_tax_treatment")
            .annotate(
                balance=Sum("entries__amount", default=Decimal(0)),
                transaction_count=Count("entries"),
            )
        )


class AccountDetailView(LoginRequiredMixin, DetailView):
    template_name = "accounts/detail.html"
    context_object_name = "account"

    def get_queryset(self):
        return FinancialAccount.objects.filter(owner=self.request.user).select_related(
            "currency", "institution", "return_tax_treatment"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["balance"] = account_balance(self.object)
        context["recent_entries"] = self.object.entries.select_related("transaction").order_by(
            "-transaction__transaction_date", "-id"
        )[:20]
        try:
            details = self.object.fixed_term_details
        except FixedTermDetails.DoesNotExist:
            details = None
        if details:
            projection = calculate_fixed_term_projection(
                details.principal,
                details.annual_interest_rate,
                details.start_date,
                details.maturity_date,
                details.interest_method,
                details.compounding_frequency or None,
            )
            progress = calculate_fixed_term_progress(details, timezone.localdate())
            tax_result = calculate_return_tax(
                projection.gross_interest, self.object.return_tax_treatment
            )
            context.update(
                fixed_term=details,
                fixed_projection=projection,
                fixed_progress=progress,
                fixed_status=details.fixed_term_status,
                fixed_rate_percent=details.annual_interest_rate * Decimal(100),
                principal_differs_from_balance=context["balance"] != details.principal,
                return_tax_result=tax_result,
                net_maturity_value=details.principal + tax_result.net_return,
            )
        return context


class AccountCreateView(LoginRequiredMixin, CreateView):
    template_name = "form.html"
    form_class = FinancialAccountForm
    success_url = reverse_lazy("accounts:list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        with db_transaction.atomic():
            form.instance.owner = self.request.user
            response = super().form_valid(form)
            details = form.save_fixed_term_details(self.object)
            if details:
                funding = form.cleaned_data.get("funding_account")
                if funding:
                    create_transfer(
                        self.request.user,
                        funding,
                        self.object,
                        details.principal,
                        details.start_date,
                        f"Fund {self.object.name}",
                    )
                else:
                    create_deposit(
                        self.request.user,
                        self.object,
                        details.principal,
                        details.start_date,
                        f"Opening principal: {self.object.name}",
                    )
            return response


class AccountUpdateView(LoginRequiredMixin, UpdateView):
    template_name = "form.html"
    form_class = FinancialAccountForm
    success_url = reverse_lazy("accounts:list")

    def get_queryset(self):
        return FinancialAccount.objects.filter(owner=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        with db_transaction.atomic():
            response = super().form_valid(form)
            form.save_fixed_term_details(self.object)
            return response


@login_required
@require_POST
def archive_account(request, pk):
    account = get_object_or_404(FinancialAccount, pk=pk, owner=request.user)
    account.active = False
    account.save(update_fields=["active", "updated_at"])
    return redirect("accounts:list")


@login_required
def export_account_csv(request, pk):
    account = get_object_or_404(
        FinancialAccount.objects.select_related("currency"), pk=pk, owner=request.user
    )
    response = HttpResponse(
        export_account_transactions(account), content_type="text/csv; charset=utf-8"
    )
    filename = slugify(account.name) or f"account-{account.pk}"
    response["Content-Disposition"] = f'attachment; filename="{filename}-transactions.csv"'
    return response
