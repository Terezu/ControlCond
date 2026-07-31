from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from .financial_services import obter_dashboard_financeiro
from .forms import (
    FiltroCompetenciaDashboardForm,
    FiltroDashboardFinanceiroForm,
)
from .services import obter_resumo_dashboard
from condominios.services import obter_condominio_ativo


CHAVE_SESSAO_COMPETENCIA = "dashboard_competencia"


@login_required
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
        "contratos": reverse("contratos:lista"),
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


@login_required
@never_cache
@require_safe
def dashboard_financeiro(request):
    condominio = obter_condominio_ativo(request)
    padrao = FiltroCompetenciaDashboardForm.competencia_atual()
    form = FiltroDashboardFinanceiroForm(
        request.GET or None,
        condominio=condominio,
        initial=padrao,
    )
    filtros = {**padrao, "apartamento": None, "status": ""}
    if form.is_valid():
        filtros.update(form.cleaned_data)
    resumo = obter_dashboard_financeiro(condominio, **filtros)

    parametros = {"mes": resumo.mes, "ano": resumo.ano}
    if filtros["apartamento"] is not None:
        parametros["apartamento"] = filtros["apartamento"].pk
    base_faturas = reverse("faturas:lista")

    def link_faturas(status=None):
        query = dict(parametros)
        if status:
            query["status"] = status
        return f"{base_faturas}?{urlencode(query)}"

    return render(
        request,
        "dashboard/financeiro.html",
        {
            "form_filtros": form,
            "resumo": resumo,
            "links": {
                "todas": link_faturas(),
                "pagas": link_faturas("paga"),
                "pendentes": link_faturas("pendente"),
                "vencidas": link_faturas("pendente"),
                "canceladas": link_faturas("cancelada"),
                "limpar": reverse("dashboard:financeiro"),
            },
        },
    )
