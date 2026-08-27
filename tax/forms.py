from django import forms

from .models import (
    ReturnTaxTreatment,
    TaxAdjustment,
    TaxAllowance,
    TaxDeduction,
    TaxRule,
    TaxYear,
)

DATE_WIDGET = forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})


class ReturnTaxTreatmentForm(forms.ModelForm):
    class Meta:
        model = ReturnTaxTreatment
        fields = [
            "name",
            "treatment_type",
            "tax_rate",
            "jurisdiction",
            "tax_deducted_at_source",
            "notes",
        ]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}
        help_texts = {
            "jurisdiction": "Optional ISO 3166-1 alpha-2 country code; informational only.",
            "tax_deducted_at_source": "Used by Custom Tax Rate to classify the estimate as withholding.",
        }

    def clean_jurisdiction(self):
        return self.cleaned_data["jurisdiction"].upper()


class TaxYearForm(forms.ModelForm):
    class Meta:
        model = TaxYear
        fields = [
            "name",
            "jurisdiction",
            "start_date",
            "end_date",
            "reporting_currency",
            "status",
            "notes",
        ]
        widgets = {"start_date": DATE_WIDGET, "end_date": DATE_WIDGET}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.owner = user

    def clean_jurisdiction(self):
        return self.cleaned_data["jurisdiction"].upper()


class TaxYearItemForm(forms.ModelForm):
    def __init__(self, *args, user, tax_year, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.owner = user
        self.instance.tax_year = tax_year


class TaxDeductionForm(TaxYearItemForm):
    class Meta:
        model = TaxDeduction
        fields = ["name", "category", "amount", "currency", "date", "notes", "active"]
        widgets = {"date": DATE_WIDGET}


class TaxAllowanceForm(TaxYearItemForm):
    class Meta:
        model = TaxAllowance
        fields = ["name", "category", "amount", "currency", "notes", "active"]


class TaxAdjustmentForm(TaxYearItemForm):
    class Meta:
        model = TaxAdjustment
        fields = [
            "category",
            "applies_to",
            "description",
            "amount",
            "currency",
            "date",
            "notes",
            "active",
        ]
        widgets = {"date": DATE_WIDGET}


class TaxRuleForm(TaxYearItemForm):
    class Meta:
        model = TaxRule
        fields = [
            "name",
            "rule_type",
            "category",
            "rate",
            "threshold",
            "fixed_amount",
            "priority",
            "metadata",
            "active",
        ]
        widgets = {"metadata": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        selected_type = (
            self.data.get(self.add_prefix("rule_type"))
            if self.is_bound
            else self.instance.rule_type
        )
        if not selected_type:
            selected_type = TaxRule.Type.FLAT_RATE
            self.initial["rule_type"] = selected_type
        relevant = {
            TaxRule.Type.FLAT_RATE: "rate",
            TaxRule.Type.THRESHOLD: "threshold",
            TaxRule.Type.ALLOWANCE: "fixed_amount",
            TaxRule.Type.DEDUCTION: "fixed_amount",
        }.get(selected_type)
        for name in ("rate", "threshold", "fixed_amount"):
            if relevant and name != relevant:
                self.fields.pop(name)
