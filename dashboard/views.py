from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone
from django.views.generic import TemplateView

from accounts.models import FinancialAccount
from ledger.models import Transaction, TransactionEntry


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
        fixed_term_accounts = [
            account
            for account in reporting_accounts
            if account.account_type == FinancialAccount.Type.FIXED_TERM
        ]
        next_maturity = (
            self.request.user.financial_accounts.filter(
                active=True,
                account_type=FinancialAccount.Type.FIXED_TERM,
                fixed_term_details__maturity_date__gte=timezone.localdate(),
            )
            .order_by("fixed_term_details__maturity_date")
            .values_list("fixed_term_details__maturity_date", flat=True)
            .first()
        )
        account_chart = self._account_chart(reporting_accounts, liabilities)
        cashflow_chart = self._cashflow_chart()
        ctx.update(
            accounts=accounts,
            total_assets=assets,
            total_liabilities=liability,
            net_worth=assets - liability,
            reporting_currency=settings.DEFAULT_CURRENCY,
            unvalued_account_count=len(accounts) - len(reporting_accounts),
            fixed_term_total=sum((account.balance for account in fixed_term_accounts), Decimal(0)),
            fixed_term_count=len(fixed_term_accounts),
            next_fixed_term_maturity=next_maturity,
            account_chart=account_chart,
            cashflow_chart=cashflow_chart,
            recent_transactions=Transaction.objects.filter(
                owner=self.request.user
            ).prefetch_related("entries__account")[:8],
        )
        return ctx

    def _account_chart(self, accounts, liabilities):
        chart_accounts = []
        for account in accounts:
            amount = abs(account.balance)
            if not amount:
                continue
            chart_accounts.append(
                {
                    "name": account.name,
                    "amount": amount,
                    "is_liability": account.account_type in liabilities,
                }
            )

        chart_accounts.sort(key=lambda item: item["amount"], reverse=True)
        maximum = max((item["amount"] for item in chart_accounts), default=Decimal(1))
        for item in chart_accounts:
            item["percentage"] = max(4, int(item["amount"] / maximum * 100))
        return chart_accounts[:8]

    def _cashflow_chart(self):
        today = timezone.localdate()
        first_month = date(today.year, today.month, 1)
        months = []
        for _ in range(6):
            months.append(first_month)
            first_month = (first_month - timedelta(days=1)).replace(day=1)
        months.reverse()

        totals = {
            row["month"]: row["amount"] or Decimal(0)
            for row in TransactionEntry.objects.filter(
                transaction__owner=self.request.user,
                account__currency__code=settings.DEFAULT_CURRENCY,
                transaction__transaction_date__gte=months[0],
            )
            .annotate(month=TruncMonth("transaction__transaction_date"))
            .values("month")
            .annotate(amount=Sum("amount"))
        }
        chart = [
            {"label": month.strftime("%b"), "amount": totals.get(month, Decimal(0))}
            for month in months
        ]
        maximum = max((abs(item["amount"]) for item in chart), default=Decimal(1))
        for item in chart:
            item["percentage"] = int(abs(item["amount"]) / maximum * 100) if maximum else 0
            item["is_positive"] = item["amount"] >= 0
        return chart
