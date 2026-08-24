from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from .models import FinancialAccount, FixedTermDetails, Institution


class InstitutionForm(forms.ModelForm):
    class Meta:
        model = Institution
        fields = ["name", "institution_type", "country", "website", "notes"]


class FinancialAccountForm(forms.ModelForm):
    fixed_principal = forms.DecimalField(
        min_value=Decimal("0.0001"), max_digits=20, decimal_places=4, required=False
    )
    fixed_start_date = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    fixed_maturity_date = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    fixed_annual_rate_percent = forms.DecimalField(
        min_value=Decimal(0), max_digits=10, decimal_places=6, required=False,
        help_text="Percentage rate, for example 3.25 for 3.25%.",
    )
    fixed_interest_method = forms.ChoiceField(
        choices=FixedTermDetails.InterestMethod.choices, required=False
    )
    fixed_compounding_frequency = forms.ChoiceField(
        choices=[("", "—")] + list(FixedTermDetails.CompoundingFrequency.choices),
        required=False,
    )
    fixed_interest_payment_method = forms.ChoiceField(
        choices=FixedTermDetails.PaymentMethod.choices, required=False
    )
    fixed_interest_destination = forms.ChoiceField(
        choices=FixedTermDetails.InterestDestination.choices, required=False
    )
    fixed_interest_destination_account = forms.ModelChoiceField(
        queryset=FinancialAccount.objects.none(), required=False
    )
    fixed_early_withdrawal_allowed = forms.BooleanField(required=False)
    fixed_early_withdrawal_penalty_notes = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 3})
    )
    fixed_maturity_instruction = forms.ChoiceField(
        choices=FixedTermDetails.MaturityInstruction.choices, required=False
    )
    fixed_maturity_destination_account = forms.ModelChoiceField(
        queryset=FinancialAccount.objects.none(), required=False
    )
    funding_account = forms.ModelChoiceField(
        queryset=FinancialAccount.objects.none(), required=False,
        help_text="Optional. Creates one linked transfer for the contractual principal.",
    )

    class Meta:
        model = FinancialAccount
        fields = [
            "name",
            "institution",
            "account_type",
            "currency",
            "account_number_last4",
            "opening_date",
            "notes",
        ]
        widgets = {"opening_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user:
            self.fields["institution"].queryset = Institution.objects.filter(
                owner=user, active=True
            )
            accounts = FinancialAccount.objects.filter(owner=user, active=True)
            if self.instance.pk:
                accounts = accounts.exclude(pk=self.instance.pk)
            for name in (
                "fixed_interest_destination_account",
                "fixed_maturity_destination_account",
                "funding_account",
            ):
                self.fields[name].queryset = accounts
        if self.instance.pk:
            self.fields.pop("funding_account")
        if self.instance.pk and self.instance.account_type == FinancialAccount.Type.FIXED_TERM:
            try:
                details = self.instance.fixed_term_details
            except FixedTermDetails.DoesNotExist:
                details = None
            if details:
                self.initial.update(
                    fixed_principal=details.principal,
                    fixed_start_date=details.start_date,
                    fixed_maturity_date=details.maturity_date,
                    fixed_annual_rate_percent=details.annual_interest_rate * Decimal(100),
                    fixed_interest_method=details.interest_method,
                    fixed_compounding_frequency=details.compounding_frequency,
                    fixed_interest_payment_method=details.interest_payment_method,
                    fixed_interest_destination=details.interest_destination,
                    fixed_interest_destination_account=details.interest_destination_account,
                    fixed_early_withdrawal_allowed=details.early_withdrawal_allowed,
                    fixed_early_withdrawal_penalty_notes=details.early_withdrawal_penalty_notes,
                    fixed_maturity_instruction=details.maturity_instruction,
                    fixed_maturity_destination_account=details.maturity_destination_account,
                )

    def clean(self):
        cleaned = super().clean()
        if (
            self.instance.pk
            and cleaned.get("account_type")
            and cleaned["account_type"] != self.instance.account_type
        ):
            self.add_error("account_type", "Account type cannot be changed after creation.")
        if cleaned.get("account_type") != FinancialAccount.Type.FIXED_TERM:
            return cleaned
        required = {
            "fixed_principal": "Principal is required.",
            "fixed_start_date": "Start date is required.",
            "fixed_maturity_date": "Maturity date is required.",
            "fixed_annual_rate_percent": "Annual interest rate is required.",
            "fixed_interest_method": "Interest method is required.",
            "fixed_interest_payment_method": "Interest payment method is required.",
            "fixed_interest_destination": "Interest destination is required.",
            "fixed_maturity_instruction": "Maturity instruction is required.",
        }
        for name, message in required.items():
            if cleaned.get(name) in (None, ""):
                self.add_error(name, message)
        if (
            cleaned.get("fixed_start_date")
            and cleaned.get("fixed_maturity_date")
            and cleaned["fixed_maturity_date"] <= cleaned["fixed_start_date"]
        ):
            self.add_error("fixed_maturity_date", "Maturity date must be after the start date.")
        if (
            cleaned.get("fixed_interest_method") == FixedTermDetails.InterestMethod.COMPOUND
            and not cleaned.get("fixed_compounding_frequency")
        ):
            self.add_error("fixed_compounding_frequency", "Compound interest requires a frequency.")
        if (
            cleaned.get("fixed_interest_destination") == FixedTermDetails.InterestDestination.PAID_OUT
            and not cleaned.get("fixed_interest_destination_account")
        ):
            self.add_error("fixed_interest_destination_account", "Select a payout account.")
        funding = cleaned.get("funding_account")
        currency = cleaned.get("currency")
        if funding and currency and funding.currency_id != currency.pk:
            self.add_error("funding_account", "Funding account currency must match.")
        return cleaned

    def save_fixed_term_details(self, account):
        if account.account_type != FinancialAccount.Type.FIXED_TERM:
            FixedTermDetails.objects.filter(account=account).delete()
            return None
        details, _ = FixedTermDetails.objects.get_or_create(
            account=account,
            defaults={
                "principal": self.cleaned_data["fixed_principal"],
                "start_date": self.cleaned_data["fixed_start_date"],
                "maturity_date": self.cleaned_data["fixed_maturity_date"],
                "annual_interest_rate": self.cleaned_data["fixed_annual_rate_percent"] / Decimal(100),
                "interest_method": self.cleaned_data["fixed_interest_method"],
            },
        )
        details.principal = self.cleaned_data["fixed_principal"]
        details.start_date = self.cleaned_data["fixed_start_date"]
        details.maturity_date = self.cleaned_data["fixed_maturity_date"]
        details.annual_interest_rate = self.cleaned_data["fixed_annual_rate_percent"] / Decimal(100)
        details.interest_method = self.cleaned_data["fixed_interest_method"]
        details.compounding_frequency = self.cleaned_data["fixed_compounding_frequency"]
        details.interest_payment_method = self.cleaned_data["fixed_interest_payment_method"]
        details.interest_destination = self.cleaned_data["fixed_interest_destination"]
        details.interest_destination_account = self.cleaned_data["fixed_interest_destination_account"]
        details.early_withdrawal_allowed = self.cleaned_data["fixed_early_withdrawal_allowed"]
        details.early_withdrawal_penalty_notes = self.cleaned_data["fixed_early_withdrawal_penalty_notes"]
        details.maturity_instruction = self.cleaned_data["fixed_maturity_instruction"]
        details.maturity_destination_account = self.cleaned_data["fixed_maturity_destination_account"]
        try:
            details.full_clean()
        except ValidationError as error:
            raise ValidationError(error.message_dict) from error
        details.save()
        return details
