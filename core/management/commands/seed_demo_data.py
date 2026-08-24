from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts.models import FinancialAccount, Institution
from core.models import Currency
from investments.models import Security
from ledger.services import create_deposit, create_transfer, create_withdrawal


class Command(BaseCommand):
    help = "Create non-production demo data."

    def handle(self, *args, **options):
        currencies = [
            ("EUR", "Euro", "€", 2),
            ("USD", "US Dollar", "$", 2),
            ("GBP", "Pound Sterling", "£", 2),
            ("CHF", "Swiss Franc", "CHF", 2),
            ("JPY", "Japanese Yen", "¥", 0),
        ]
        for code, name, symbol, places in currencies:
            Currency.objects.get_or_create(
                code=code, defaults={"name": name, "symbol": symbol, "decimal_places": places}
            )
        user, created = get_user_model().objects.get_or_create(
            username="demo", defaults={"email": "demo@example.invalid"}
        )
        if created:
            user.set_password("demo")
            user.save()
        eur = Currency.objects.get(code="EUR")
        bank, _ = Institution.objects.get_or_create(
            owner=user, name="Example Bank", defaults={"institution_type": "BANK"}
        )
        broker, _ = Institution.objects.get_or_create(
            owner=user, name="Example Broker", defaults={"institution_type": "BROKER"}
        )
        current, _ = FinancialAccount.objects.get_or_create(
            owner=user,
            name="Main Current Account",
            defaults={"institution": bank, "account_type": "CHECKING", "currency": eur},
        )
        savings, _ = FinancialAccount.objects.get_or_create(
            owner=user,
            name="Savings Account",
            defaults={"institution": bank, "account_type": "SAVINGS", "currency": eur},
        )
        FinancialAccount.objects.get_or_create(
            owner=user,
            name="Brokerage Account",
            defaults={"institution": broker, "account_type": "BROKERAGE", "currency": eur},
        )
        if not user.transactions.exists():
            today = date.today()
            create_deposit(user, current, Decimal(3000), today, "Salary", transaction_type="INCOME")
            create_withdrawal(
                user, current, Decimal("75.40"), today, "Groceries", transaction_type="EXPENSE"
            )
            create_transfer(user, current, savings, Decimal(500), today, "Transfer to savings")
            create_deposit(
                user,
                savings,
                Decimal("1.25"),
                today,
                "Interest payment",
                transaction_type="INTEREST",
            )
        Security.objects.get_or_create(
            symbol="EXETF",
            exchange="XETRA",
            defaults={"name": "Example ETF", "security_type": "ETF", "currency": eur},
        )
        Security.objects.get_or_create(
            symbol="EXSTK",
            exchange="XETRA",
            defaults={"name": "Example Stock", "security_type": "STOCK", "currency": eur},
        )
        self.stdout.write(self.style.SUCCESS("Demo data ready (username: demo, password: demo)."))
