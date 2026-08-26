from decimal import Decimal
from types import SimpleNamespace

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, FormView, ListView, TemplateView

from accounts.models import FinancialAccount
from core.models import Currency, ExchangeRate
from ledger.models import Transaction

from .forms import ExchangeRateForm, SecurityForm, SecurityPriceForm
from .models import InvestmentTransaction, Security, SecurityPrice
from .services.holdings import calculate_holdings
from .services.pricing import get_latest_price
from .services.transactions import create_investment_transaction
from .services.valuation import calculate_portfolio_value


class PortfolioView(LoginRequiredMixin, TemplateView):
    template_name = "investments/portfolio.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        accounts = FinancialAccount.objects.filter(
            owner=self.request.user, active=True, account_type=FinancialAccount.Type.BROKERAGE
        ).select_related("currency", "institution")
        reporting_currency = Currency.objects.filter(code=settings.DEFAULT_CURRENCY).first()
        valuations = [
            calculate_portfolio_value(
                account, reporting_currency=reporting_currency or account.currency
            )
            for account in accounts
        ]
        context["valuations"] = valuations
        context["accounts"] = accounts
        context["recent_transactions"] = InvestmentTransaction.objects.filter(
            account__owner=self.request.user
        ).select_related("transaction", "account", "security", "currency").order_by(
            "-transaction__transaction_date", "-transaction_id"
        )[:10]
        complete = all(value.complete for value in valuations)
        context["summary"] = SimpleNamespace(
            reporting_currency=reporting_currency,
            complete=complete,
            total_account_value=(
                sum((value.total_account_value for value in valuations), Decimal(0))
                if complete and reporting_currency
                else None
            ),
            cash=(
                sum((value.cash_balance for value in valuations), Decimal(0)) if complete else None
            ),
            cost_basis=(
                sum((value.cost_basis for value in valuations), Decimal(0)) if complete else None
            ),
            unrealized_gain=(
                sum((value.unrealized_gain for value in valuations), Decimal(0))
                if complete
                else None
            ),
            realized_gain=(
                sum((value.realized_gain for value in valuations), Decimal(0)) if complete else None
            ),
        )
        return context


class BrokerageDetailView(LoginRequiredMixin, DetailView):
    template_name = "investments/account_detail.html"
    context_object_name = "account"

    def get_queryset(self):
        return FinancialAccount.objects.filter(
            owner=self.request.user, account_type=FinancialAccount.Type.BROKERAGE
        ).select_related("currency", "institution")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        valuation = calculate_portfolio_value(self.object)
        context["valuation"] = valuation
        context["allocation_chart"] = [
            {"category": item.category, "market_value": item.market_value}
            for item in valuation.allocation
        ]
        context["investment_transactions"] = (
            InvestmentTransaction.objects.filter(account=self.object)
            .select_related("transaction", "security", "currency")
            .order_by("-transaction__transaction_date", "-transaction_id")[:30]
        )
        return context


class InvestmentCreateView(LoginRequiredMixin, FormView):
    template_name = "investments/transaction_form.html"
    transaction_type = Transaction.Type.BUY

    def get_account(self):
        account_pk = self.kwargs.get("account_pk")
        if not account_pk:
            return None
        return get_object_or_404(
            FinancialAccount,
            pk=account_pk,
            owner=self.request.user,
            account_type=FinancialAccount.Type.BROKERAGE,
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(
            user=self.request.user,
            transaction_type=self.transaction_type,
            account=self.get_account(),
        )
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["transaction_type"] = self.transaction_type
        context["title"] = f"Record {self.transaction_type.lower()}"
        if self.transaction_type == Transaction.Type.SELL and self.get_account():
            context["sell_holdings"] = calculate_holdings(self.get_account())
        return context

    def form_valid(self, form):
        try:
            detail = create_investment_transaction(
                owner=self.request.user,
                transaction_type=self.transaction_type,
                **form.cleaned_data,
            )
        except ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)
        messages.success(self.request, f"{self.transaction_type.title()} recorded atomically.")
        return redirect("investments:account_detail", pk=detail.account_id)


class SecurityListView(LoginRequiredMixin, ListView):
    model = Security
    template_name = "investments/security_list.html"
    context_object_name = "securities"

    def get_queryset(self):
        return Security.objects.select_related("currency").order_by("symbol", "exchange")


class SecurityCreateView(LoginRequiredMixin, CreateView):
    model = Security
    form_class = SecurityForm
    template_name = "form.html"
    success_url = reverse_lazy("investments:security_list")

    def get_context_data(self, **kwargs):
        return super().get_context_data(title="Add security", **kwargs)


class SecurityDetailView(LoginRequiredMixin, DetailView):
    model = Security
    template_name = "investments/security_detail.html"
    context_object_name = "security"

    def get_queryset(self):
        return Security.objects.select_related("currency")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        accounts = FinancialAccount.objects.filter(
            owner=self.request.user, account_type=FinancialAccount.Type.BROKERAGE
        ).select_related("currency")
        reporting_currency = Currency.objects.filter(code=settings.DEFAULT_CURRENCY).first()
        positions = []
        for account in accounts:
            valuation = calculate_portfolio_value(
                account, reporting_currency=reporting_currency or account.currency
            )
            row = next(
                (row for row in valuation.holdings if row.security.pk == self.object.pk), None
            )
            if row:
                positions.append(SimpleNamespace(account=account, valuation=row))
        context["positions"] = positions
        complete = all(position.valuation.market_value is not None for position in positions)
        context["position_summary"] = SimpleNamespace(
            currency=reporting_currency,
            quantity=sum((position.valuation.quantity for position in positions), Decimal(0)),
            market_value=(
                sum((position.valuation.market_value for position in positions), Decimal(0))
                if complete
                else None
            ),
            cost_basis=(
                sum((position.valuation.cost_basis for position in positions), Decimal(0))
                if complete
                else None
            ),
            unrealized_gain=(
                sum((position.valuation.unrealized_gain for position in positions), Decimal(0))
                if complete
                else None
            ),
        )
        context["latest_price"] = get_latest_price(self.object)
        context["prices"] = self.object.prices.select_related("currency")[:20]
        context["transactions"] = (
            InvestmentTransaction.objects.filter(
                account__owner=self.request.user, security=self.object
            )
            .select_related("transaction", "account", "currency")
            .order_by("-transaction__transaction_date")[:20]
        )
        return context


class PriceListView(LoginRequiredMixin, ListView):
    model = SecurityPrice
    template_name = "investments/price_list.html"
    context_object_name = "prices"

    def get_queryset(self):
        return SecurityPrice.objects.select_related("security", "currency")[:100]


class PriceCreateView(LoginRequiredMixin, CreateView):
    model = SecurityPrice
    form_class = SecurityPriceForm
    template_name = "form.html"
    success_url = reverse_lazy("investments:price_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        security_pk = self.request.GET.get("security")
        kwargs["security"] = get_object_or_404(Security, pk=security_pk) if security_pk else None
        return kwargs

    def get_context_data(self, **kwargs):
        return super().get_context_data(title="Add manual security price", **kwargs)


class ExchangeRateListView(LoginRequiredMixin, ListView):
    model = ExchangeRate
    template_name = "investments/fx_list.html"
    context_object_name = "rates"

    def get_queryset(self):
        return ExchangeRate.objects.select_related("base_currency", "quote_currency")[:100]


class ExchangeRateCreateView(LoginRequiredMixin, CreateView):
    model = ExchangeRate
    form_class = ExchangeRateForm
    template_name = "form.html"
    success_url = reverse_lazy("investments:fx_list")

    def get_context_data(self, **kwargs):
        return super().get_context_data(title="Add manual FX rate", **kwargs)
