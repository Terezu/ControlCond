from urllib.parse import urlencode

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from .forms import FiltroCompetenciaDashboardForm
from .services import obter_resumo_dashboard


@staff_member_required
@never_cache
@require_safe
def dashboard(request):
    competencia_padrao = (
        FiltroCompetenciaDashboardForm.competencia_atual()
    )
    if request.GET:
        form = FiltroCompetenciaDashboardForm(request.GET)
        competencia = (
            form.cleaned_data
            if form.is_valid()
            else competencia_padrao
        )
    else:
        form = FiltroCompetenciaDashboardForm(
            initial=competencia_padrao
        )
        competencia = competencia_padrao

    resumo = obter_resumo_dashboard(
        competencia["mes"],
        competencia["ano"],
    )
    base_faturas = reverse("faturas:lista")
    parametros = {"mes": resumo.mes, "ano": resumo.ano}
    links = {
        "apartamentos": reverse("apartamentos:lista"),
        "faturas_pendentes": (
            f"{base_faturas}?{urlencode({
                **parametros,
                'status': 'pendente',
            })}"
        ),
        "faturas_pagas": (
            f"{base_faturas}?{urlencode({
                **parametros,
                'status': 'paga',
            })}"
        ),
        "faturas_canceladas": (
            f"{base_faturas}?{urlencode({
                **parametros,
                'status': 'cancelada',
            })}"
        ),
    }
    return render(
        request,
        "dashboard/inicio.html",
        {
            "form_competencia": form,
            "resumo": resumo,
            "links": links,
        },
    )
