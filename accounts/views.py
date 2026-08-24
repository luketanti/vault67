from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import FinancialAccountForm
from .models import FinancialAccount


class AccountListView(LoginRequiredMixin, ListView):
    template_name = "accounts/list.html"
    context_object_name = "accounts"

    def get_queryset(self):
        return FinancialAccount.objects.filter(owner=self.request.user, active=True).select_related(
            "currency", "institution"
        )


class AccountDetailView(LoginRequiredMixin, DetailView):
    template_name = "accounts/detail.html"
    context_object_name = "account"

    def get_queryset(self):
        return FinancialAccount.objects.filter(owner=self.request.user).select_related(
            "currency", "institution"
        )

    def get_context_data(self, **kwargs):
        from ledger.services import account_balance

        context = super().get_context_data(**kwargs)
        context["balance"] = account_balance(self.object)
        context["recent_entries"] = self.object.entries.select_related("transaction")[:20]
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
        form.instance.owner = self.request.user
        return super().form_valid(form)


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


@login_required
@require_POST
def archive_account(request, pk):
    account = get_object_or_404(FinancialAccount, pk=pk, owner=request.user)
    account.active = False
    account.save(update_fields=["active", "updated_at"])
    return redirect("accounts:list")
