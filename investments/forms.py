from decimal import Decimal

from django import forms

from accounts.models import FinancialAccount
from core.models import Currency, ExchangeRate
from ledger.models import Transaction

from .models import Security, SecurityPrice
from .services.holdings import calculate_holding

DATE_WIDGET = forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})


class SecurityForm(forms.ModelForm):
    class Meta:
        model = Security
        fields = ["symbol", "name", "security_type", "currency", "isin", "exchange", "active"]

    def clean_symbol(self):
        return self.cleaned_data["symbol"].strip().upper()

    def clean_isin(self):
        return self.cleaned_data["isin"].strip().upper()


class InvestmentTransactionForm(forms.Form):
    account = forms.ModelChoiceField(queryset=FinancialAccount.objects.none())
    security = forms.ModelChoiceField(queryset=Security.objects.none())
    trade_date = forms.DateField(widget=DATE_WIDGET)
    settlement_date = forms.DateField(widget=DATE_WIDGET, required=False)
    quantity = forms.DecimalField(
        max_digits=28, decimal_places=8, min_value=Decimal("0.00000001"), required=False
    )
    price_per_unit = forms.DecimalField(
        max_digits=28, decimal_places=8, min_value=Decimal(0), required=False
    )
    gross_amount = forms.DecimalField(
        max_digits=20, decimal_places=4, min_value=Decimal(0), required=False
    )
    fees = forms.DecimalField(max_digits=20, decimal_places=4, min_value=Decimal(0), initial=0)
    taxes = forms.DecimalField(
        label="Taxes / withholding",
        max_digits=20,
        decimal_places=4,
        min_value=Decimal(0),
        initial=0,
    )
    currency = forms.ModelChoiceField(queryset=Currency.objects.filter(active=True))
    exchange_rate = forms.DecimalField(
        max_digits=24,
        decimal_places=12,
        min_value=Decimal("0.000000000001"),
        required=False,
        help_text="Required for foreign trades: 1 transaction currency in account-currency units.",
    )
    reference = forms.CharField(max_length=100, required=False)
    notes = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False)

    def __init__(self, *args, user, transaction_type, account=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.transaction_type = transaction_type
        self.fields["account"].queryset = FinancialAccount.objects.filter(
            owner=user, active=True, account_type=FinancialAccount.Type.BROKERAGE
        ).select_related("currency")
        self.fields["security"].queryset = Security.objects.filter(active=True).select_related(
            "currency"
        )
        if account is not None:
            self.fields["account"].initial = account
        if transaction_type in (
            Transaction.Type.DIVIDEND,
            Transaction.Type.FEE,
            Transaction.Type.TAX,
        ):
            self.fields.pop("quantity")
            self.fields.pop("price_per_unit")
            self.fields["gross_amount"].required = True
            self.fields["gross_amount"].label = (
                "Gross dividend" if transaction_type == Transaction.Type.DIVIDEND else "Amount"
            )
        else:
            self.fields.pop("gross_amount")
        if transaction_type not in (Transaction.Type.BUY, Transaction.Type.SELL):
            self.fields.pop("settlement_date")
        if transaction_type == Transaction.Type.DIVIDEND:
            self.fields["trade_date"].label = "Payment date"

    def clean(self):
        cleaned = super().clean()
        account = cleaned.get("account")
        security = cleaned.get("security")
        currency = cleaned.get("currency")
        if account and account.owner_id != self.user.id:
            self.add_error("account", "Select a valid brokerage account.")
        if security and currency and security.currency_id != currency.pk:
            self.add_error("currency", "Transaction currency must match the security currency.")
        if account and currency:
            if account.currency_id != currency.pk and not cleaned.get("exchange_rate"):
                self.add_error(
                    "exchange_rate",
                    "An exchange rate is required for this foreign-currency transaction.",
                )
            elif account.currency_id == currency.pk and cleaned.get("exchange_rate") not in (
                None,
                Decimal(1),
            ):
                self.add_error("exchange_rate", "Same-currency transactions must use a rate of 1.")
        if self.transaction_type in (Transaction.Type.BUY, Transaction.Type.SELL):
            quantity = cleaned.get("quantity")
            price = cleaned.get("price_per_unit")
            if quantity is not None and price is not None:
                cleaned["gross_amount"] = (quantity * price).quantize(Decimal("0.0001"))
            if self.transaction_type == Transaction.Type.SELL and account and security and quantity:
                held = calculate_holding(account, security, cleaned.get("trade_date")).quantity
                if quantity > held:
                    self.add_error(
                        "quantity",
                        f"Insufficient holdings to sell {quantity} shares; current holding is {held}.",
                    )
        return cleaned


class SecurityPriceForm(forms.ModelForm):
    class Meta:
        model = SecurityPrice
        fields = ["security", "date", "price", "currency", "source"]
        widgets = {"date": DATE_WIDGET}

    def __init__(self, *args, security=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["security"].queryset = Security.objects.filter(active=True)
        if security:
            self.fields["security"].initial = security

    def clean(self):
        cleaned = super().clean()
        security = cleaned.get("security")
        currency = cleaned.get("currency")
        if security and currency and security.currency_id != currency.pk:
            self.add_error("currency", "Price currency must match the security currency.")
        return cleaned


class ExchangeRateForm(forms.ModelForm):
    class Meta:
        model = ExchangeRate
        fields = ["date", "base_currency", "quote_currency", "rate", "source"]
        widgets = {"date": DATE_WIDGET}

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("base_currency") == cleaned.get("quote_currency"):
            self.add_error("quote_currency", "Base and quote currencies must differ.")
        return cleaned
