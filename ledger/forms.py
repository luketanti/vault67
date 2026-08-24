from django import forms


class EntryForm(forms.Form):
    account = forms.ModelChoiceField(queryset=None)
    amount = forms.DecimalField(min_value=0.0001, decimal_places=4, max_digits=20)
    transaction_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    description = forms.CharField(max_length=255)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if "account" in self.fields:
            self.fields["account"].queryset = (
                user.financial_accounts.filter(active=True) if user else None
            )


class TransferForm(EntryForm):
    source = forms.ModelChoiceField(queryset=None)
    destination = forms.ModelChoiceField(queryset=None)
    account = None

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, user=user, **kwargs)
        qs = user.financial_accounts.filter(active=True) if user else None
        self.fields["source"].queryset = qs
        self.fields["destination"].queryset = qs

    def clean(self):
        data = super().clean()
        if data.get("source") == data.get("destination"):
            self.add_error("destination", "Choose a different destination account.")
        return data
