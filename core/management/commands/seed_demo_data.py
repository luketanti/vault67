from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts.models import FinancialAccount, FixedTermDetails, Institution
from core.models import Currency, ExchangeRate
from investments.models import Security, SecurityPrice
from investments.services.transactions import create_investment_transaction
from ledger.models import Transaction
from ledger.services import create_deposit, create_transfer, create_withdrawal
from tax.models import ReturnTaxTreatment


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
        brokerage, _ = FinancialAccount.objects.get_or_create(
            owner=user,
            name="Brokerage Account",
            defaults={"institution": broker, "account_type": "BROKERAGE", "currency": eur},
        )
        fixed_term, _ = FinancialAccount.objects.get_or_create(
            owner=user,
            name="12 Month Fixed Deposit",
            defaults={
                "institution": bank,
                "account_type": FinancialAccount.Type.FIXED_TERM,
                "currency": eur,
                "opening_date": date(2026, 1, 1),
            },
        )
        tax_treatment, _ = ReturnTaxTreatment.objects.get_or_create(
            owner=user,
            name="Demo Bank Interest Tax",
            defaults={
                "treatment_type": ReturnTaxTreatment.TreatmentType.WITHHOLDING,
                "tax_rate": Decimal("15.00"),
                "jurisdiction": "MT",
                "tax_deducted_at_source": True,
            },
        )
        if fixed_term.return_tax_treatment_id != tax_treatment.pk:
            fixed_term.return_tax_treatment = tax_treatment
            fixed_term.save(update_fields=["return_tax_treatment", "updated_at"])
        FixedTermDetails.objects.get_or_create(
            account=fixed_term,
            defaults={
                "principal": Decimal(25000),
                "start_date": date(2026, 1, 1),
                "maturity_date": date(2027, 1, 1),
                "annual_interest_rate": Decimal("0.0325"),
                "interest_method": FixedTermDetails.InterestMethod.SIMPLE,
                "interest_payment_method": FixedTermDetails.PaymentMethod.AT_MATURITY,
                "interest_destination": FixedTermDetails.InterestDestination.CAPITALIZED,
                "maturity_instruction": FixedTermDetails.MaturityInstruction.UNDECIDED,
            },
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
        if not fixed_term.entries.exists():
            create_deposit(
                user,
                fixed_term,
                Decimal(25000),
                date(2026, 1, 1),
                "Opening principal: 12 Month Fixed Deposit",
            )
        etf, _ = Security.objects.get_or_create(
            symbol="EXETF",
            exchange="XETRA",
            defaults={"name": "Example ETF", "security_type": "ETF", "currency": eur},
        )
        usd = Currency.objects.get(code="USD")
        stock, _ = Security.objects.get_or_create(
            symbol="EXSTK",
            exchange="NASDAQ",
            defaults={"name": "Example Stock", "security_type": "STOCK", "currency": usd},
        )
        demo_date = date(2026, 8, 1)
        ExchangeRate.objects.get_or_create(
            date=demo_date,
            base_currency=eur,
            quote_currency=usd,
            source="MANUAL",
            defaults={"rate": Decimal("1.20")},
        )
        SecurityPrice.objects.get_or_create(
            security=etf,
            date=demo_date,
            source=SecurityPrice.Source.MANUAL,
            defaults={"price": Decimal("112.50"), "currency": eur},
        )
        SecurityPrice.objects.get_or_create(
            security=stock,
            date=demo_date,
            source=SecurityPrice.Source.MANUAL,
            defaults={"price": Decimal("155.00"), "currency": usd},
        )
        if not brokerage.investment_transactions.exists():
            create_deposit(user, brokerage, Decimal(10000), demo_date, "Brokerage funding")
            create_investment_transaction(
                owner=user,
                account=brokerage,
                security=etf,
                transaction_type=Transaction.Type.BUY,
                trade_date=demo_date,
                settlement_date=demo_date,
                quantity=Decimal(20),
                price_per_unit=Decimal(100),
                gross_amount=Decimal(2000),
                fees=Decimal(5),
                taxes=Decimal(0),
                currency=eur,
            )
            create_investment_transaction(
                owner=user,
                account=brokerage,
                security=stock,
                transaction_type=Transaction.Type.BUY,
                trade_date=demo_date,
                settlement_date=demo_date,
                quantity=Decimal(10),
                price_per_unit=Decimal(140),
                gross_amount=Decimal(1400),
                fees=Decimal(4),
                taxes=Decimal(0),
                currency=usd,
                exchange_rate=Decimal("0.833333333333"),
            )
            create_investment_transaction(
                owner=user,
                account=brokerage,
                security=etf,
                transaction_type=Transaction.Type.DIVIDEND,
                trade_date=demo_date,
                gross_amount=Decimal(50),
                fees=Decimal(1),
                taxes=Decimal("7.50"),
                currency=eur,
            )
        self.stdout.write(self.style.SUCCESS("Demo data ready (username: demo, password: demo)."))
