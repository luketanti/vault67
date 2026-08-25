from django import forms


class TransactionImportForm(forms.Form):
    csv_file = forms.FileField(
        label="CSV or PDF file",
        help_text=(
            "CSV files require Transaction Date, Description, and Amount columns. "
            "Text-based Multitude Bank PDF statements are also accepted."
        ),
        widget=forms.ClearableFileInput(attrs={"accept": ".csv,.pdf,text/csv,application/pdf"}),
    )

    def clean_csv_file(self):
        csv_file = self.cleaned_data["csv_file"]
        if csv_file.size > 5 * 1024 * 1024:
            raise forms.ValidationError("The import file must be 5 MB or smaller.")
        filename = csv_file.name.casefold()
        if not filename.endswith((".csv", ".pdf")):
            raise forms.ValidationError("Choose a CSV or PDF file.")
        if filename.endswith(".pdf"):
            header = csv_file.read(1024)
            csv_file.seek(0)
            if b"%PDF-" not in header:
                raise forms.ValidationError("The selected file is not a valid PDF.")
        return csv_file


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
