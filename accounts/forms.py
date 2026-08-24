from django import forms

from .models import FinancialAccount, Institution


class InstitutionForm(forms.ModelForm):
    class Meta:
        model = Institution
        fields = ["name", "institution_type", "country", "website", "notes"]


class FinancialAccountForm(forms.ModelForm):
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
        if user:
            self.fields["institution"].queryset = Institution.objects.filter(
                owner=user, active=True
            )
