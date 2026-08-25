from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView, UpdateView

from .forms import ReturnTaxTreatmentForm
from .models import ReturnTaxTreatment


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
