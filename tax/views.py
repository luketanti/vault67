import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.text import slugify
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import (
    ReturnTaxTreatmentForm,
    TaxAdjustmentForm,
    TaxAllowanceForm,
    TaxDeductionForm,
    TaxRuleForm,
    TaxYearForm,
)
from .models import (
    ReturnTaxTreatment,
    TaxAdjustment,
    TaxAllowance,
    TaxDeduction,
    TaxRule,
    TaxYear,
)
from .services.aggregation import build_tax_year_summary


class TaxTreatmentListView(LoginRequiredMixin, ListView):
    template_name = "tax/treatment_list.html"
    context_object_name = "treatments"

    def get_queryset(self):
        return ReturnTaxTreatment.objects.filter(owner=self.request.user, active=True)


class TaxTreatmentCreateView(LoginRequiredMixin, CreateView):
    template_name = "tax/treatment_form.html"
    form_class = ReturnTaxTreatmentForm
    success_url = reverse_lazy("tax:treatment_list")

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)


class TaxTreatmentUpdateView(LoginRequiredMixin, UpdateView):
    template_name = "tax/treatment_form.html"
    form_class = ReturnTaxTreatmentForm
    success_url = reverse_lazy("tax:treatment_list")

    def get_queryset(self):
        return ReturnTaxTreatment.objects.filter(owner=self.request.user, active=True)


@login_required
@require_POST
def archive_tax_treatment(request, pk):
    treatment = get_object_or_404(ReturnTaxTreatment, pk=pk, owner=request.user)
    treatment.active = False
    treatment.save(update_fields=["active", "updated_at"])
    return redirect("tax:treatment_list")


class TaxYearListView(LoginRequiredMixin, ListView):
    template_name = "tax/year_list.html"
    context_object_name = "tax_years"

    def get_queryset(self):
        return TaxYear.objects.filter(owner=self.request.user).select_related("reporting_currency")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["year_summaries"] = [
            (tax_year, build_tax_year_summary(tax_year)) for tax_year in context["tax_years"]
        ]
        return context


class TaxYearCreateView(LoginRequiredMixin, CreateView):
    template_name = "tax/entity_form.html"
    form_class = TaxYearForm

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "user": self.request.user}

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            title="Create tax year", cancel_url=reverse_lazy("tax:year_list"), **kwargs
        )

    def get_success_url(self):
        return reverse_lazy("tax:year_detail", args=[self.object.pk])


class TaxYearUpdateView(LoginRequiredMixin, UpdateView):
    template_name = "tax/entity_form.html"
    form_class = TaxYearForm

    def get_queryset(self):
        return TaxYear.objects.filter(owner=self.request.user)

    def dispatch(self, request, *args, **kwargs):
        if self.get_object().status == TaxYear.Status.FILED:
            return HttpResponseForbidden(
                "This tax year cannot be edited because it is marked as Filed."
            )
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "user": self.request.user}

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            title="Edit tax year",
            cancel_url=reverse_lazy("tax:year_detail", args=[self.object.pk]),
            **kwargs,
        )

    def get_success_url(self):
        return reverse_lazy("tax:year_detail", args=[self.object.pk])


class TaxYearDetailView(LoginRequiredMixin, DetailView):
    template_name = "tax/year_detail.html"
    context_object_name = "tax_year"

    def get_queryset(self):
        return TaxYear.objects.filter(owner=self.request.user).select_related("reporting_currency")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["summary"] = build_tax_year_summary(self.object)
        context["deductions"] = self.object.taxdeduction_set.filter(active=True).select_related(
            "currency"
        )
        context["allowances"] = self.object.taxallowance_set.filter(active=True).select_related(
            "currency"
        )
        context["adjustments"] = self.object.taxadjustment_set.filter(active=True).select_related(
            "currency"
        )
        context["rules"] = self.object.rules.filter(owner=self.request.user, active=True)
        return context


class TaxYearOwnedMixin(LoginRequiredMixin):
    def get_tax_year(self):
        if not hasattr(self, "tax_year"):
            self.tax_year = get_object_or_404(
                TaxYear, pk=self.kwargs["tax_year_pk"], owner=self.request.user
            )
        return self.tax_year

    def dispatch(self, request, *args, **kwargs):
        if self.get_tax_year().status == TaxYear.Status.FILED:
            return HttpResponseForbidden(
                "This tax year cannot be edited because it is marked as Filed."
            )
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        return {
            **super().get_form_kwargs(),
            "user": self.request.user,
            "tax_year": self.get_tax_year(),
        }

    def get_success_url(self):
        return reverse_lazy("tax:year_detail", args=[self.get_tax_year().pk])

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            tax_year=self.get_tax_year(),
            cancel_url=reverse_lazy("tax:year_detail", args=[self.get_tax_year().pk]),
            **kwargs,
        )


class TaxItemCreateView(TaxYearOwnedMixin, CreateView):
    template_name = "tax/entity_form.html"


class TaxItemUpdateView(TaxYearOwnedMixin, UpdateView):
    template_name = "tax/entity_form.html"

    def get_queryset(self):
        return self.model.objects.filter(
            owner=self.request.user, tax_year=self.get_tax_year(), active=True
        )


class TaxDeductionCreateView(TaxItemCreateView):
    model = TaxDeduction
    form_class = TaxDeductionForm

    def get_context_data(self, **kwargs):
        return super().get_context_data(title="Add deduction", **kwargs)


class TaxDeductionUpdateView(TaxItemUpdateView):
    model = TaxDeduction
    form_class = TaxDeductionForm

    def get_context_data(self, **kwargs):
        return super().get_context_data(title="Edit deduction", **kwargs)


class TaxAllowanceCreateView(TaxItemCreateView):
    model = TaxAllowance
    form_class = TaxAllowanceForm

    def get_context_data(self, **kwargs):
        return super().get_context_data(title="Add allowance", **kwargs)


class TaxAllowanceUpdateView(TaxItemUpdateView):
    model = TaxAllowance
    form_class = TaxAllowanceForm

    def get_context_data(self, **kwargs):
        return super().get_context_data(title="Edit allowance", **kwargs)


class TaxAdjustmentCreateView(TaxItemCreateView):
    model = TaxAdjustment
    form_class = TaxAdjustmentForm

    def get_context_data(self, **kwargs):
        return super().get_context_data(title="Add manual adjustment", **kwargs)


class TaxAdjustmentUpdateView(TaxItemUpdateView):
    model = TaxAdjustment
    form_class = TaxAdjustmentForm

    def get_context_data(self, **kwargs):
        return super().get_context_data(title="Edit manual adjustment", **kwargs)


class TaxRuleCreateView(TaxItemCreateView):
    model = TaxRule
    form_class = TaxRuleForm

    def get_context_data(self, **kwargs):
        return super().get_context_data(title="Add tax rule", **kwargs)


class TaxRuleUpdateView(TaxItemUpdateView):
    model = TaxRule
    form_class = TaxRuleForm

    def get_context_data(self, **kwargs):
        return super().get_context_data(title="Edit tax rule", **kwargs)


@login_required
@require_POST
def archive_tax_item(request, tax_year_pk, kind, pk):
    tax_year = get_object_or_404(TaxYear, pk=tax_year_pk, owner=request.user)
    if tax_year.status == TaxYear.Status.FILED:
        return HttpResponseForbidden(
            "This tax year cannot be edited because it is marked as Filed."
        )
    model = {
        "deduction": TaxDeduction,
        "allowance": TaxAllowance,
        "adjustment": TaxAdjustment,
        "rule": TaxRule,
    }.get(kind)
    if model is None:
        return HttpResponse(status=404)
    item = get_object_or_404(model, pk=pk, owner=request.user, tax_year=tax_year)
    item.active = False
    item.save()
    messages.success(request, "Tax item archived.")
    return redirect("tax:year_detail", pk=tax_year.pk)


def _csv_safe(value):
    text = str(value)
    return f"'{text}" if text.startswith(("=", "+", "-", "@")) else text


def _csv_amount(value):
    return "" if value is None else value


@login_required
def export_tax_year_csv(request, pk):
    tax_year = get_object_or_404(TaxYear, pk=pk, owner=request.user)
    summary = build_tax_year_summary(tax_year)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    safe_name = slugify(tax_year.name) or f"year-{tax_year.pk}"
    response["Content-Disposition"] = f'attachment; filename="tax-{safe_name}.csv"'
    writer = csv.writer(response)
    writer.writerow(
        ["section", "date", "source", "category", "original_amount", "currency", "reporting_amount"]
    )
    for line in summary.interest_lines:
        writer.writerow(
            [
                "interest",
                line.date,
                _csv_safe(line.description),
                "INTEREST",
                line.original_amount,
                line.currency.code,
                _csv_amount(line.reporting_amount),
            ]
        )
    for line in summary.dividend_lines:
        item = line.investment_transaction
        writer.writerow(
            [
                "dividend",
                item.trade_date,
                _csv_safe(item.security.symbol),
                "DIVIDEND",
                line.gross_original,
                item.currency.code,
                _csv_amount(line.gross_reporting),
            ]
        )
    for line in summary.capital_gain_lines:
        item = line.event.investment_transaction
        writer.writerow(
            [
                "capital_gain",
                item.trade_date,
                _csv_safe(item.security.symbol),
                "CAPITAL_GAIN",
                line.event.gain,
                item.currency.code,
                _csv_amount(line.gain_reporting),
            ]
        )
    for line in summary.tax_payment_lines:
        writer.writerow(
            [
                "tax_payment",
                line.date,
                _csv_safe(line.description),
                "TAX_PAYMENT",
                line.original_amount,
                line.currency.code,
                _csv_amount(line.reporting_amount),
            ]
        )
    for item in tax_year.taxdeduction_set.filter(owner=request.user, active=True).select_related(
        "currency"
    ):
        writer.writerow(
            [
                "deduction",
                item.date,
                _csv_safe(item.name),
                item.category,
                item.amount,
                item.currency.code,
                "",
            ]
        )
    writer.writerow(
        [
            "summary",
            "",
            "Estimated tax liability",
            "",
            "",
            tax_year.reporting_currency.code,
            summary.estimated_tax_liability,
        ]
    )
    writer.writerow(
        [
            "summary",
            "",
            "Tax withheld",
            "",
            "",
            tax_year.reporting_currency.code,
            summary.tax_withheld,
        ]
    )
    writer.writerow(
        ["summary", "", "Tax paid", "", "", tax_year.reporting_currency.code, summary.tax_paid]
    )
    writer.writerow(
        [
            "summary",
            "",
            "Estimated due",
            "",
            "",
            tax_year.reporting_currency.code,
            summary.estimated_tax_due,
        ]
    )
    writer.writerow(
        [
            "summary",
            "",
            "Estimated refund or credit",
            "",
            "",
            tax_year.reporting_currency.code,
            summary.estimated_refund_credit,
        ]
    )
    return response
