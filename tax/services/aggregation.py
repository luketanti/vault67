from dataclasses import dataclass, field
from decimal import Decimal

from django.core.exceptions import ValidationError

from accounts.models import FinancialAccount
from core.services.fx import MissingExchangeRate, convert_currency
from investments.models import InvestmentTransaction
from investments.services.cost_basis import calculate_realized_gain_events
from ledger.models import Transaction, TransactionEntry
from tax.models import (
    TaxableCategory,
    TaxAdjustment,
    TaxAllowance,
    TaxCategory,
    TaxDeduction,
    TaxRule,
    TaxYear,
)

ZERO = Decimal(0)
CATEGORY_ORDER = (
    TaxableCategory.INTEREST,
    TaxableCategory.DIVIDEND,
    TaxableCategory.CAPITAL_GAIN,
    TaxableCategory.EMPLOYMENT_INCOME,
    TaxableCategory.OTHER_INCOME,
)


@dataclass(frozen=True)
class InterestTaxLine:
    account: object
    date: object
    description: str
    original_amount: Decimal
    currency: object
    reporting_amount: Decimal | None


@dataclass(frozen=True)
class DividendTaxLine:
    investment_transaction: InvestmentTransaction
    gross_original: Decimal
    withholding_original: Decimal
    net_original: Decimal
    gross_reporting: Decimal | None
    withholding_reporting: Decimal | None
    net_reporting: Decimal | None


@dataclass(frozen=True)
class CapitalGainTaxLine:
    event: object
    net_proceeds_reporting: Decimal | None
    allocated_cost_reporting: Decimal | None
    gain_reporting: Decimal | None


@dataclass(frozen=True)
class TaxPaymentLine:
    account: object
    date: object
    description: str
    original_amount: Decimal
    currency: object
    reporting_amount: Decimal | None


@dataclass(frozen=True)
class RuleTrace:
    rule: TaxRule
    input_amount: Decimal
    adjustment: Decimal
    output_amount: Decimal
    tax: Decimal


@dataclass
class CategoryTaxBreakdown:
    category: str
    gross_amount: Decimal = ZERO
    losses: Decimal = ZERO
    allowances: Decimal = ZERO
    deductions: Decimal = ZERO
    taxable_amount: Decimal = ZERO
    estimated_tax: Decimal = ZERO
    withholding: Decimal = ZERO
    applied_rules: list[RuleTrace] = field(default_factory=list)

    @property
    def label(self):
        return TaxableCategory(self.category).label


@dataclass(frozen=True)
class TaxYearSummary:
    tax_year: TaxYear
    categories: tuple[CategoryTaxBreakdown, ...]
    interest_lines: tuple[InterestTaxLine, ...]
    dividend_lines: tuple[DividendTaxLine, ...]
    capital_gain_lines: tuple[CapitalGainTaxLine, ...]
    tax_payment_lines: tuple[TaxPaymentLine, ...]
    gross_interest: Decimal
    gross_dividends: Decimal
    realized_capital_gains: Decimal
    realized_capital_losses: Decimal
    net_realized_gain: Decimal
    deductions: Decimal
    allowances: Decimal
    tax_withheld: Decimal
    tax_paid: Decimal
    gross_taxable_income: Decimal
    estimated_tax_liability: Decimal
    estimated_tax_due: Decimal
    estimated_refund_credit: Decimal
    completeness: str
    reasons: tuple[str, ...]
    unclassified_transactions: tuple[Transaction, ...]


def _convert(amount, currency, tax_year, relevant_date, reasons):
    try:
        return convert_currency(amount, currency, tax_year.reporting_currency, relevant_date)
    except MissingExchangeRate as exc:
        reasons.append(exc.messages[0])
        return None


def _convert_investment(amount, item, tax_year, reasons):
    if item.currency_id == tax_year.reporting_currency_id:
        return amount
    trade_date = item.transaction.transaction_date
    if item.exchange_rate is not None:
        account_amount = amount * item.exchange_rate
        return _convert(account_amount, item.account.currency, tax_year, trade_date, reasons)
    return _convert(amount, item.currency, tax_year, trade_date, reasons)


def _apply_overall_reduction(breakdowns, amount, attribute):
    remaining = amount
    for category in CATEGORY_ORDER:
        if remaining <= ZERO:
            break
        row = breakdowns[category]
        available = max(ZERO, row.taxable_amount)
        used = min(available, remaining)
        row.taxable_amount -= used
        setattr(row, attribute, getattr(row, attribute) + used)
        remaining -= used


def build_tax_year_summary(tax_year):
    """Build a live, unrounded, explainable estimate from actual source events.

    Ordering is: aggregate actual events; net capital losses; apply manual
    allowances; apply manual deductions; apply threshold/allowance/deduction
    rules by priority; apply flat-rate rules; subtract actual withholding and
    actual tax payments. Overall reductions are allocated deterministically in
    ``CATEGORY_ORDER``. Presentation performs currency rounding.
    """
    reasons = []
    interest_lines = []
    dividend_lines = []
    capital_lines = []
    payment_lines = []
    breakdowns = {category: CategoryTaxBreakdown(category) for category in CATEGORY_ORDER}
    date_filter = {
        "transaction__transaction_date__gte": tax_year.start_date,
        "transaction__transaction_date__lte": tax_year.end_date,
    }

    interest_entries = TransactionEntry.objects.filter(
        transaction__owner=tax_year.owner,
        transaction__transaction_type=Transaction.Type.INTEREST,
        amount__gt=0,
        **date_filter,
    ).select_related("transaction", "account", "currency")
    for entry in interest_entries:
        converted = _convert(
            entry.amount,
            entry.currency,
            tax_year,
            entry.transaction.transaction_date,
            reasons,
        )
        interest_lines.append(
            InterestTaxLine(
                account=entry.account,
                date=entry.transaction.transaction_date,
                description=entry.transaction.description,
                original_amount=entry.amount,
                currency=entry.currency,
                reporting_amount=converted,
            )
        )
        if converted is not None:
            breakdowns[TaxableCategory.INTEREST].gross_amount += converted

    dividends = InvestmentTransaction.objects.filter(
        account__owner=tax_year.owner,
        transaction__transaction_type=Transaction.Type.DIVIDEND,
        transaction__transaction_date__range=(tax_year.start_date, tax_year.end_date),
    ).select_related("transaction", "account__currency", "security", "currency")
    for item in dividends:
        net = item.gross_amount - item.taxes - item.fees
        gross_reporting = _convert_investment(item.gross_amount, item, tax_year, reasons)
        tax_reporting = _convert_investment(item.taxes, item, tax_year, reasons)
        net_reporting = _convert_investment(net, item, tax_year, reasons)
        dividend_lines.append(
            DividendTaxLine(
                investment_transaction=item,
                gross_original=item.gross_amount,
                withholding_original=item.taxes,
                net_original=net,
                gross_reporting=gross_reporting,
                withholding_reporting=tax_reporting,
                net_reporting=net_reporting,
            )
        )
        if gross_reporting is not None:
            breakdowns[TaxableCategory.DIVIDEND].gross_amount += gross_reporting
        if tax_reporting is not None:
            breakdowns[TaxableCategory.DIVIDEND].withholding += tax_reporting

    accounts = FinancialAccount.objects.filter(
        owner=tax_year.owner, account_type=FinancialAccount.Type.BROKERAGE
    ).select_related("currency")
    for account in accounts:
        try:
            events = calculate_realized_gain_events(account, tax_year.end_date)
        except ValidationError as exc:
            reasons.extend(exc.messages)
            continue
        for event in events:
            item = event.investment_transaction
            trade_date = item.transaction.transaction_date
            if trade_date < tax_year.start_date:
                continue
            proceeds = _convert(
                event.net_proceeds_base, account.currency, tax_year, trade_date, reasons
            )
            cost = _convert(
                event.allocated_cost_basis_base,
                account.currency,
                tax_year,
                trade_date,
                reasons,
            )
            gain = _convert(event.gain_base, account.currency, tax_year, trade_date, reasons)
            capital_lines.append(CapitalGainTaxLine(event, proceeds, cost, gain))
            if gain is not None:
                if gain >= ZERO:
                    breakdowns[TaxableCategory.CAPITAL_GAIN].gross_amount += gain
                else:
                    breakdowns[TaxableCategory.CAPITAL_GAIN].losses += gain

    tax_paid = ZERO
    tax_entries = TransactionEntry.objects.filter(
        transaction__owner=tax_year.owner,
        transaction__transaction_type=Transaction.Type.TAX,
        amount__lt=0,
        **date_filter,
    ).select_related("transaction", "account", "currency")
    for entry in tax_entries:
        converted = _convert(
            -entry.amount,
            entry.currency,
            tax_year,
            entry.transaction.transaction_date,
            reasons,
        )
        if converted is not None:
            tax_paid += converted
        payment_lines.append(
            TaxPaymentLine(
                account=entry.account,
                date=entry.transaction.transaction_date,
                description=entry.transaction.description,
                original_amount=-entry.amount,
                currency=entry.currency,
                reporting_amount=converted,
            )
        )

    allowances = list(
        TaxAllowance.objects.filter(
            owner=tax_year.owner, tax_year=tax_year, active=True
        ).select_related("currency")
    )
    deductions = list(
        TaxDeduction.objects.filter(
            owner=tax_year.owner, tax_year=tax_year, active=True
        ).select_related("currency")
    )
    adjustments = list(
        TaxAdjustment.objects.filter(
            owner=tax_year.owner, tax_year=tax_year, active=True
        ).select_related("currency")
    )
    manual_allowances = {category: ZERO for category in (*CATEGORY_ORDER, TaxableCategory.OVERALL)}
    manual_deductions = {category: ZERO for category in (*CATEGORY_ORDER, TaxableCategory.OVERALL)}
    manual_withholding = ZERO
    for item in allowances:
        converted = _convert(item.amount, item.currency, tax_year, tax_year.start_date, reasons)
        if converted is not None:
            manual_allowances[item.category] += converted
    for item in deductions:
        converted = _convert(item.amount, item.currency, tax_year, item.date, reasons)
        if converted is not None:
            manual_deductions[item.category] += converted
    for item in adjustments:
        converted = _convert(item.amount, item.currency, tax_year, item.date, reasons)
        if converted is None:
            continue
        if item.category in breakdowns:
            breakdowns[item.category].gross_amount += converted
        elif item.category == TaxCategory.CAPITAL_LOSS:
            breakdowns[TaxableCategory.CAPITAL_GAIN].losses -= abs(converted)
        elif item.category == TaxCategory.ALLOWANCE:
            manual_allowances[item.applies_to or TaxableCategory.OVERALL] += abs(converted)
        elif item.category == TaxCategory.DEDUCTION:
            manual_deductions[item.applies_to or TaxableCategory.OVERALL] += abs(converted)
        elif item.category == TaxCategory.WITHHOLDING_TAX:
            if item.applies_to in breakdowns:
                breakdowns[item.applies_to].withholding += abs(converted)
            else:
                manual_withholding += abs(converted)
        elif item.category == TaxCategory.TAX_PAYMENT:
            tax_paid += abs(converted)

    for category, row in breakdowns.items():
        row.taxable_amount = max(ZERO, row.gross_amount + row.losses)
        allowance = min(row.taxable_amount, manual_allowances[category])
        row.allowances += allowance
        row.taxable_amount -= allowance
        deduction = min(row.taxable_amount, manual_deductions[category])
        row.deductions += deduction
        row.taxable_amount -= deduction
    _apply_overall_reduction(breakdowns, manual_allowances[TaxableCategory.OVERALL], "allowances")
    _apply_overall_reduction(breakdowns, manual_deductions[TaxableCategory.OVERALL], "deductions")

    rules = TaxRule.objects.filter(owner=tax_year.owner, tax_year=tax_year, active=True).order_by(
        "priority", "pk"
    )
    for rule in rules.exclude(rule_type=TaxRule.Type.FLAT_RATE):
        targets = CATEGORY_ORDER if rule.category == TaxableCategory.OVERALL else (rule.category,)
        for category in targets:
            row = breakdowns[category]
            before = row.taxable_amount
            reduction_limit = (
                rule.threshold if rule.rule_type == TaxRule.Type.THRESHOLD else rule.fixed_amount
            )
            reduction = min(before, reduction_limit or ZERO)
            row.taxable_amount -= reduction
            if rule.rule_type == TaxRule.Type.ALLOWANCE:
                row.allowances += reduction
            else:
                row.deductions += reduction
            row.applied_rules.append(RuleTrace(rule, before, -reduction, row.taxable_amount, ZERO))
    for rule in rules.filter(rule_type=TaxRule.Type.FLAT_RATE):
        targets = CATEGORY_ORDER if rule.category == TaxableCategory.OVERALL else (rule.category,)
        for category in targets:
            row = breakdowns[category]
            tax = row.taxable_amount * rule.rate / Decimal(100)
            row.estimated_tax += tax
            row.applied_rules.append(
                RuleTrace(rule, row.taxable_amount, ZERO, row.taxable_amount, tax)
            )

    unclassified = tuple(
        Transaction.objects.filter(
            owner=tax_year.owner,
            transaction_date__range=(tax_year.start_date, tax_year.end_date),
            transaction_type__in=[Transaction.Type.INCOME, Transaction.Type.ADJUSTMENT],
        ).order_by("transaction_date", "pk")
    )
    generic_dividends = Transaction.objects.filter(
        owner=tax_year.owner,
        transaction_date__range=(tax_year.start_date, tax_year.end_date),
        transaction_type=Transaction.Type.DIVIDEND,
        investment_detail__isnull=True,
    )
    unclassified += tuple(generic_dividends)
    review_reasons = [
        f'Unclassified transaction "{item.description}" on {item.transaction_date}.'
        for item in unclassified
    ]
    for row in breakdowns.values():
        if row.taxable_amount > ZERO and not any(
            trace.rule.rule_type == TaxRule.Type.FLAT_RATE for trace in row.applied_rules
        ):
            review_reasons.append(f"No active flat-rate tax rule covers {row.label}.")

    tax_withheld = sum((row.withholding for row in breakdowns.values()), ZERO) + manual_withholding
    estimated_tax = sum((row.estimated_tax for row in breakdowns.values()), ZERO)
    due = estimated_tax - tax_withheld - tax_paid
    completeness = "INCOMPLETE" if reasons else "NEEDS_REVIEW" if review_reasons else "COMPLETE"
    all_reasons = tuple(dict.fromkeys([*reasons, *review_reasons]))
    capital = breakdowns[TaxableCategory.CAPITAL_GAIN]
    return TaxYearSummary(
        tax_year=tax_year,
        categories=tuple(breakdowns[category] for category in CATEGORY_ORDER),
        interest_lines=tuple(interest_lines),
        dividend_lines=tuple(dividend_lines),
        capital_gain_lines=tuple(capital_lines),
        tax_payment_lines=tuple(payment_lines),
        gross_interest=breakdowns[TaxableCategory.INTEREST].gross_amount,
        gross_dividends=breakdowns[TaxableCategory.DIVIDEND].gross_amount,
        realized_capital_gains=capital.gross_amount,
        realized_capital_losses=capital.losses,
        net_realized_gain=capital.gross_amount + capital.losses,
        deductions=sum((row.deductions for row in breakdowns.values()), ZERO),
        allowances=sum((row.allowances for row in breakdowns.values()), ZERO),
        tax_withheld=tax_withheld,
        tax_paid=tax_paid,
        gross_taxable_income=sum(
            (
                breakdowns[category].gross_amount
                for category in CATEGORY_ORDER
                if category != TaxableCategory.CAPITAL_GAIN
            ),
            ZERO,
        ),
        estimated_tax_liability=estimated_tax,
        estimated_tax_due=max(ZERO, due),
        estimated_refund_credit=max(ZERO, -due),
        completeness=completeness,
        reasons=all_reasons,
        unclassified_transactions=unclassified,
    )
