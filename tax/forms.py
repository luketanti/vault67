from django import forms

from .models import ReturnTaxTreatment


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
