from dataclasses import dataclass
from decimal import Decimal

from tax.models import ReturnTaxTreatment


@dataclass(frozen=True)
class ReturnTaxResult:
    """Unrounded estimated tax outcome for one gross return."""

    gross_return: Decimal
    estimated_tax: Decimal
    tax_withheld: Decimal
    estimated_tax_due_later: Decimal
    net_return: Decimal
    effective_tax_rate: Decimal


def calculate_return_tax(
    gross_return: Decimal, tax_treatment: ReturnTaxTreatment | None
) -> ReturnTaxResult:
    """Calculate estimated tax without creating or changing ledger entries.

    ``CUSTOM`` follows its ``tax_deducted_at_source`` setting; withholding is
    always estimated as deducted at source, while year-end tax is due later.
    Monetary values are deliberately unrounded so presentation can apply the
    account currency's precision without affecting financial calculations.
    """
    if gross_return < 0:
        raise ValueError("gross_return must not be negative")
    zero = Decimal(0)
    treatment_type = (
        tax_treatment.treatment_type if tax_treatment else ReturnTaxTreatment.TreatmentType.NONE
    )
    rate = zero if not tax_treatment or tax_treatment.tax_rate is None else tax_treatment.tax_rate
    rate_fraction = rate / Decimal(100)
    taxable_types = {
        ReturnTaxTreatment.TreatmentType.WITHHOLDING,
        ReturnTaxTreatment.TreatmentType.YEAR_END,
        ReturnTaxTreatment.TreatmentType.CUSTOM,
    }
    estimated_tax = gross_return * rate_fraction if treatment_type in taxable_types else zero
    withheld = zero
    due_later = zero
    if treatment_type == ReturnTaxTreatment.TreatmentType.WITHHOLDING:
        withheld = estimated_tax
    elif treatment_type == ReturnTaxTreatment.TreatmentType.YEAR_END:
        due_later = estimated_tax
    elif treatment_type == ReturnTaxTreatment.TreatmentType.CUSTOM:
        if tax_treatment.tax_deducted_at_source:
            withheld = estimated_tax
        else:
            due_later = estimated_tax
    return ReturnTaxResult(
        gross_return=gross_return,
        estimated_tax=estimated_tax,
        tax_withheld=withheld,
        estimated_tax_due_later=due_later,
        net_return=gross_return - estimated_tax,
        effective_tax_rate=rate_fraction if treatment_type in taxable_types else zero,
    )
