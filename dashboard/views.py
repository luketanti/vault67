from decimal import Decimal

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.views.generic import TemplateView

from accounts.models import FinancialAccount
from ledger.models import Transaction


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/index.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        accounts = list(
            FinancialAccount.objects.filter(owner=self.request.user, active=True).select_related(
                "currency"
            )
        )
        for account in accounts:
            account.balance = account.entries.aggregate(value=Sum("amount"))["value"] or Decimal(0)
        reporting_accounts = [
            account for account in accounts if account.currency.code == settings.DEFAULT_CURRENCY
        ]
        liabilities = {"CREDIT_CARD", "LOAN", "MORTGAGE"}
        assets = sum(
            (a.balance for a in reporting_accounts if a.account_type not in liabilities), Decimal(0)
        )
        liability = sum(
            (-a.balance for a in reporting_accounts if a.account_type in liabilities), Decimal(0)
        )
        ctx.update(
            accounts=accounts,
            total_assets=assets,
            total_liabilities=liability,
            net_worth=assets - liability,
            reporting_currency=settings.DEFAULT_CURRENCY,
            unvalued_account_count=len(accounts) - len(reporting_accounts),
            recent_transactions=Transaction.objects.filter(
                owner=self.request.user
            ).prefetch_related("entries__account")[:8],
        )
        return ctx
