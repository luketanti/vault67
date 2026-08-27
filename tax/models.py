from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models import Currency, TimeStampedModel


class TaxCategory(models.TextChoices):
    INTEREST = "INTEREST", "Interest"
    DIVIDEND = "DIVIDEND", "Dividend"
    CAPITAL_GAIN = "CAPITAL_GAIN", "Capital gain"
    CAPITAL_LOSS = "CAPITAL_LOSS", "Capital loss"
    EMPLOYMENT_INCOME = "EMPLOYMENT_INCOME", "Employment income"
    OTHER_INCOME = "OTHER_INCOME", "Other income"
    DEDUCTION = "DEDUCTION", "Deduction"
    ALLOWANCE = "ALLOWANCE", "Allowance"
    WITHHOLDING_TAX = "WITHHOLDING_TAX", "Withholding tax"
    TAX_PAYMENT = "TAX_PAYMENT", "Tax payment"


class TaxableCategory(models.TextChoices):
    INTEREST = TaxCategory.INTEREST, "Interest"
    DIVIDEND = TaxCategory.DIVIDEND, "Dividend"
    CAPITAL_GAIN = TaxCategory.CAPITAL_GAIN, "Capital gain"
    EMPLOYMENT_INCOME = TaxCategory.EMPLOYMENT_INCOME, "Employment income"
    OTHER_INCOME = TaxCategory.OTHER_INCOME, "Other income"
    OVERALL = "OVERALL", "Overall taxable basis"


class ReturnTaxTreatment(TimeStampedModel):
    """A reusable, user-owned estimated tax treatment for investment returns.

    ``tax_rate`` is stored as a user-facing percentage: ``15.00`` means 15%.
    It is intentionally a static estimate, not jurisdiction-specific tax law.
    """

    class TreatmentType(models.TextChoices):
        NONE = "NONE", "No Tax"
        WITHHOLDING = "WITHHOLDING", "Withholding Tax"
        YEAR_END = "YEAR_END", "Taxable at Year End"
        EXEMPT = "EXEMPT", "Tax Exempt"
        CUSTOM = "CUSTOM", "Custom Tax Rate"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="return_tax_treatments"
    )
    name = models.CharField(max_length=120)
    treatment_type = models.CharField(max_length=16, choices=TreatmentType.choices)
    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Percentage rate: 15.00 means 15%.",
    )
    jurisdiction = models.CharField(max_length=2, blank=True)
    tax_deducted_at_source = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "name"], name="unique_return_tax_treatment_per_owner"
            )
        ]

    def clean(self):
        errors = {}
        taxable_types = {
            self.TreatmentType.WITHHOLDING,
            self.TreatmentType.YEAR_END,
            self.TreatmentType.CUSTOM,
        }
        if self.treatment_type in taxable_types and self.tax_rate is None:
            errors["tax_rate"] = "A tax rate is required for this treatment."
        if self.treatment_type in {
            self.TreatmentType.NONE,
            self.TreatmentType.EXEMPT,
        } and self.tax_rate not in (None, 0):
            errors["tax_rate"] = "No Tax and Tax Exempt treatments must use a zero or blank rate."
        if self.jurisdiction:
            self.jurisdiction = self.jurisdiction.upper()
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.name


class TaxYear(TimeStampedModel):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        CLOSED = "CLOSED", "Closed"
        FILED = "FILED", "Filed"
        ARCHIVED = "ARCHIVED", "Archived"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tax_years"
    )
    name = models.CharField(max_length=80)
    jurisdiction = models.CharField(max_length=2)
    start_date = models.DateField()
    end_date = models.DateField()
    reporting_currency = models.ForeignKey(Currency, on_delete=models.PROTECT)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-start_date", "jurisdiction", "name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="tax_year_dates_valid",
            ),
            models.UniqueConstraint(
                fields=["owner", "jurisdiction", "name"], name="unique_named_tax_year"
            ),
        ]

    def clean(self):
        errors = {}
        self.jurisdiction = self.jurisdiction.upper()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            errors["end_date"] = "End date must be on or after the start date."
        if self.owner_id and self.start_date and self.end_date and self.jurisdiction:
            overlap = TaxYear.objects.filter(
                owner_id=self.owner_id,
                jurisdiction=self.jurisdiction,
                start_date__lte=self.end_date,
                end_date__gte=self.start_date,
            ).exclude(pk=self.pk)
            if overlap.exists():
                errors["start_date"] = (
                    "This period overlaps another tax year for the same jurisdiction."
                )
        if self.pk:
            previous = TaxYear.objects.filter(pk=self.pk).first()
            if previous and previous.status == self.Status.FILED:
                tracked = (
                    "name",
                    "jurisdiction",
                    "start_date",
                    "end_date",
                    "reporting_currency_id",
                    "status",
                    "notes",
                )
                if any(getattr(previous, field) != getattr(self, field) for field in tracked):
                    errors["status"] = (
                        "This tax year cannot be edited because it is marked as Filed."
                    )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.jurisdiction})"


class TaxYearItem(TimeStampedModel):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    tax_year = models.ForeignKey(TaxYear, on_delete=models.CASCADE)
    active = models.BooleanField(default=True)

    class Meta:
        abstract = True

    def clean(self):
        errors = {}
        if self.owner_id and self.tax_year_id and self.owner_id != self.tax_year.owner_id:
            errors["tax_year"] = "Tax year must belong to the same user."
        if self.tax_year_id and self.tax_year.status == TaxYear.Status.FILED:
            errors["tax_year"] = "This tax year cannot be edited because it is marked as Filed."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.tax_year.status == TaxYear.Status.FILED:
            raise ValidationError("This tax year cannot be edited because it is marked as Filed.")
        return super().delete(*args, **kwargs)


class TaxDeduction(TaxYearItem):
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=24, choices=TaxableCategory.choices)
    amount = models.DecimalField(max_digits=20, decimal_places=4, validators=[MinValueValidator(0)])
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT)
    date = models.DateField()
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["date", "name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gte=0), name="tax_deduction_nonnegative"
            )
        ]

    def clean(self):
        super().clean()
        if (
            self.tax_year_id
            and self.date
            and not self.tax_year.start_date <= self.date <= self.tax_year.end_date
        ):
            raise ValidationError({"date": "Date must fall inside the tax year."})

    def __str__(self):
        return self.name


class TaxAllowance(TaxYearItem):
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=24, choices=TaxableCategory.choices)
    amount = models.DecimalField(max_digits=20, decimal_places=4, validators=[MinValueValidator(0)])
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["category", "name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gte=0), name="tax_allowance_nonnegative"
            )
        ]

    def __str__(self):
        return self.name


class TaxAdjustment(TaxYearItem):
    category = models.CharField(max_length=24, choices=TaxCategory.choices)
    applies_to = models.CharField(max_length=24, choices=TaxableCategory.choices, blank=True)
    description = models.CharField(max_length=180)
    amount = models.DecimalField(max_digits=20, decimal_places=4)
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT)
    date = models.DateField()
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["date", "category", "description"]
        constraints = [
            models.CheckConstraint(condition=~models.Q(amount=0), name="tax_adjustment_nonzero")
        ]

    def clean(self):
        super().clean()
        if (
            self.tax_year_id
            and self.date
            and not self.tax_year.start_date <= self.date <= self.tax_year.end_date
        ):
            raise ValidationError({"date": "Date must fall inside the tax year."})

    def __str__(self):
        return self.description


class TaxRule(TimeStampedModel):
    class Type(models.TextChoices):
        FLAT_RATE = "FLAT_RATE", "Flat rate"
        THRESHOLD = "THRESHOLD", "Threshold"
        ALLOWANCE = "ALLOWANCE", "Allowance"
        DEDUCTION = "DEDUCTION", "Deduction"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tax_rules",
        null=True,
        blank=True,
    )
    tax_year = models.ForeignKey(
        TaxYear, on_delete=models.CASCADE, related_name="rules", null=True, blank=True
    )
    legacy_tax_year = models.PositiveIntegerField(null=True, blank=True)
    jurisdiction = models.CharField(max_length=8)
    rule_type = models.CharField(max_length=32, choices=Type.choices)
    category = models.CharField(max_length=24, choices=TaxableCategory.choices)
    name = models.CharField(max_length=120)
    rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    threshold = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    lower_bound = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    upper_bound = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    fixed_amount = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    priority = models.PositiveSmallIntegerField(default=100)
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["priority", "name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(rate__isnull=True)
                | (models.Q(rate__gte=0) & models.Q(rate__lte=100)),
                name="annual_tax_rule_rate_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(threshold__isnull=True) | models.Q(threshold__gte=0),
                name="annual_tax_rule_threshold_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(fixed_amount__isnull=True) | models.Q(fixed_amount__gte=0),
                name="annual_tax_rule_fixed_nonnegative",
            ),
        ]

    def clean(self):
        errors = {}
        if not self.owner_id:
            errors["owner"] = "An owner is required for annual tax rules."
        if not self.tax_year_id:
            errors["tax_year"] = "A tax year is required for annual tax rules."
        elif self.owner_id and self.owner_id != self.tax_year.owner_id:
            errors["tax_year"] = "Tax year must belong to the same user."
        elif self.tax_year.status == TaxYear.Status.FILED:
            errors["tax_year"] = "This tax year cannot be edited because it is marked as Filed."
        if self.tax_year_id:
            self.jurisdiction = self.tax_year.jurisdiction
        if self.rule_type == self.Type.FLAT_RATE and self.rate is None:
            errors["rate"] = "A rate is required for a flat-rate rule."
        if self.rule_type == self.Type.THRESHOLD and self.threshold is None:
            errors["threshold"] = "A threshold is required for a threshold rule."
        if (
            self.rule_type in {self.Type.ALLOWANCE, self.Type.DEDUCTION}
            and self.fixed_amount is None
        ):
            errors["fixed_amount"] = "A fixed amount is required for this rule type."
        if self.rule_type == self.Type.FLAT_RATE:
            self.threshold = None
            self.fixed_amount = None
        elif self.rule_type == self.Type.THRESHOLD:
            self.rate = None
            self.fixed_amount = None
        elif self.rule_type in {self.Type.ALLOWANCE, self.Type.DEDUCTION}:
            self.rate = None
            self.threshold = None
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.tax_year_id and self.tax_year.status == TaxYear.Status.FILED:
            raise ValidationError("This tax year cannot be edited because it is marked as Filed.")
        return super().delete(*args, **kwargs)

    def __str__(self):
        return self.name
