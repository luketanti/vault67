from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models import TimeStampedModel


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


class TaxRule(TimeStampedModel):
    jurisdiction = models.CharField(max_length=8)
    tax_year = models.PositiveIntegerField()
    rule_type = models.CharField(max_length=32)
    name = models.CharField(max_length=120)
    rate = models.DecimalField(max_digits=12, decimal_places=8, null=True, blank=True)
    threshold = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    lower_bound = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    upper_bound = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    active = models.BooleanField(default=True)
