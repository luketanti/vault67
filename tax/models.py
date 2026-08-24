from django.db import models

from core.models import TimeStampedModel


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
