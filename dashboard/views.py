from urllib.parse import urlencode

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from .forms import FiltroCompetenciaDashboardForm
from .services import obter_resumo_dashboard
from condominios.services import obter_condominio_ativo


CHAVE_SESSAO_COMPETENCIA = "dashboard_competencia"


@staff_member_required
@never_cache
@require_safe
def dashboard(request):
    competencia_padrao = (
        FiltroCompetenciaDashboardForm.competencia_atual()
    )
    competencia_salva = request.session.get(
        CHAVE_SESSAO_COMPETENCIA,
        competencia_padrao,
    )
    if request.GET:
        form = FiltroCompetenciaDashboardForm(request.GET)
        if form.is_valid():
            competencia = form.cleaned_data
            request.session[CHAVE_SESSAO_COMPETENCIA] = competencia
        else:
            competencia = competencia_salva
    else:
        form = FiltroCompetenciaDashboardForm(
            initial=competencia_salva
        )
        competencia = competencia_salva

    resumo = obter_resumo_dashboard(
        obter_condominio_ativo(request),
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
