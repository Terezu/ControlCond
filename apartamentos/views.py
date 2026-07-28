import logging

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import Http404
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from .forms import ApartamentoForm, FiltrarApartamentosForm
from .services import (
    cadastrar_apartamento,
    consultar_apartamento,
    consultar_apartamento_no_condominio,
    consultar_detalhes_apartamento,
    consultar_detalhes_apartamento_no_condominio,
    editar_apartamento,
    excluir_apartamento,
    ExclusaoApartamentoBloqueadaError,
    listar_apartamentos,
    listar_apartamentos_por_condominio,
)
from condominios.services import obter_condominio_ativo

logger = logging.getLogger(__name__)


def _salvar_formulario(form, apartamento_id=None, condominio=None):
    dados = form.cleaned_data

    argumentos = {
        "numero": dados["numero"],
        "bloco": dados["bloco"],
        "observacoes": dados["observacoes"],
        "valor_aluguel": dados["valor_aluguel"],
        "valor_condominio": dados["valor_condominio"],
        "valor_iptu": dados["valor_iptu"],
        "valor_bonificacao": dados["valor_bonificacao"],
        "dia_limite_bonificacao": dados["dia_limite_bonificacao"],
        "leitura_base_agua": dados["leitura_base_agua"],
        "leitura_base_gas": dados["leitura_base_gas"],
    }

    if apartamento_id is None:
        return cadastrar_apartamento(condominio=condominio, **argumentos)

    return editar_apartamento(
        apartamento_id,
        **argumentos,
    )


def _obter_next_seguro(request):
    proxima_pagina = (
        request.POST.get("next")
        or request.GET.get("next")
    )

    if (
        proxima_pagina
        and url_has_allowed_host_and_scheme(
            url=proxima_pagina,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        )
    ):
        return proxima_pagina

    return None


def _redirecionar_para_next(request):
    proxima_pagina = _obter_next_seguro(request)
    return redirect(proxima_pagina) if proxima_pagina else None


@staff_member_required
@never_cache
@require_http_methods(["GET", "POST"])
def novo_apartamento(request):
    condominio = obter_condominio_ativo(request)
    form = ApartamentoForm(
        request.POST or None, condominio=condominio
    )

    if request.method == "POST" and form.is_valid():
        try:
            apartamento = _salvar_formulario(
                form, condominio=condominio
            )
        except ValueError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(
                request,
                "Apartamento cadastrado com sucesso.",
            )

            redirecionamento = _redirecionar_para_next(request)

            if redirecionamento:
                return redirecionamento

            return redirect(
                "apartamentos:detalhes",
                apartamento_id=apartamento.id,
            )

    return render(
        request,
        "apartamentos/formulario.html",
        {
            "form": form,
            "titulo": "Cadastrar apartamento",
            "next": _obter_next_seguro(request),
        },
    )


@staff_member_required
@never_cache
@require_http_methods(["GET", "POST"])
def editar_dados_apartamento(request, apartamento_id):
    condominio = obter_condominio_ativo(request)
    try:
        apartamento = consultar_apartamento_no_condominio(
            condominio, apartamento_id
        )
    except ValueError as exc:
        raise Http404(str(exc)) from exc

    form = ApartamentoForm(
        request.POST or None,
        instance=apartamento,
        condominio=condominio,
    )

    if request.method == "POST" and form.is_valid():
        try:
            apartamento = _salvar_formulario(
                form,
                apartamento_id,
            )
        except ValueError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(
                request,
                "Apartamento atualizado com sucesso.",
            )

            redirecionamento = _redirecionar_para_next(request)

            if redirecionamento:
                return redirecionamento

            return redirect(
                "apartamentos:detalhes",
                apartamento_id=apartamento.id,
            )

    return render(
        request,
        "apartamentos/formulario.html",
        {
            "form": form,
            "titulo": "Editar apartamento",
            "apartamento": apartamento,
            "next": _obter_next_seguro(request),
        },
    )


@staff_member_required
@never_cache
@require_safe
def lista_apartamentos(request):
    form_filtros = FiltrarApartamentosForm(request.GET or None)
    filtros = {}

    if form_filtros.is_valid():
        filtros = {
            "numero": form_filtros.cleaned_data["numero"],
            "bloco": form_filtros.cleaned_data["bloco"],
        }

    paginator = Paginator(
        listar_apartamentos_por_condominio(
            obter_condominio_ativo(request), **filtros
        ),
        10,
    )
    pagina_apartamentos = paginator.get_page(request.GET.get("page"))
    parametros_filtros = request.GET.copy()
    parametros_filtros.pop("page", None)

    return render(
        request,
        "apartamentos/lista.html",
        {
            "apartamentos": pagina_apartamentos,
            "pagina_apartamentos": pagina_apartamentos,
            "form_filtros": form_filtros,
            "parametros_filtros": parametros_filtros.urlencode(),
        },
    )


@staff_member_required
@never_cache
@require_safe
def detalhes_apartamento(request, apartamento_id):
    try:
        apartamento = consultar_detalhes_apartamento_no_condominio(
            obter_condominio_ativo(request), apartamento_id
        )
    except ValueError as exc:
        raise Http404(str(exc)) from exc

    leituras = list(apartamento.leituras.all())
    faturas = list(apartamento.faturas.all())
    gerenciador_vinculos = getattr(apartamento, "vinculos_pessoas", None)
    vinculos_pessoas = (
        list(gerenciador_vinculos.all())
        if gerenciador_vinculos is not None
        else []
    )

    return render(
        request,
        "apartamentos/detalhes.html",
        {
            "apartamento": apartamento,
            "ultima_leitura": leituras[0] if leituras else None,
            "leituras": leituras,
            "faturas": faturas,
            "vinculos_pessoas": vinculos_pessoas,
        },
    )


@staff_member_required
@never_cache
@require_http_methods(["GET", "POST"])
def confirmar_exclusao_apartamento(request, apartamento_id):
    try:
        apartamento = consultar_detalhes_apartamento_no_condominio(
            obter_condominio_ativo(request), apartamento_id
        )
    except ValueError as exc:
        raise Http404(str(exc)) from exc

    quantidade_leituras = apartamento.leituras.count()
    quantidade_faturas = apartamento.faturas.count()
    bloqueada = bool(quantidade_leituras or quantidade_faturas)

    if request.method == "POST":
        try:
            identificacao = excluir_apartamento(apartamento_id)
        except ExclusaoApartamentoBloqueadaError as exc:
            bloqueada = True
            messages.error(request, str(exc))
            logger.warning(
                "Exclusão de apartamento bloqueada",
                extra={
                    "apartamento_id": apartamento_id,
                    "usuario_id": request.user.id,
                },
            )
        except ValueError as exc:
            raise Http404(str(exc)) from exc
        else:
            messages.success(
                request,
                f"{identificacao} excluído permanentemente.",
            )
            logger.info(
                "Apartamento excluído permanentemente",
                extra={
                    "apartamento_id": apartamento_id,
                    "usuario_id": request.user.id,
                },
            )
            return redirect("apartamentos:lista")

    return render(
        request,
        "components/confirmar_exclusao.html",
        {
            "titulo": "Excluir apartamento",
            "identificacao": str(apartamento),
            "registros": (
                ("Número", apartamento.numero),
                ("Bloco", apartamento.bloco or "Não informado"),
                ("Leituras cadastradas", quantidade_leituras),
                ("Faturas cadastradas", quantidade_faturas),
            ),
            "bloqueada": bloqueada,
            "mensagem_bloqueio": (
                "Este apartamento não pode ser excluído enquanto possuir "
                "leituras ou faturas cadastradas. Exclua primeiro os "
                "registros vinculados."
            ),
            "aviso": "Tem certeza de que deseja excluir permanentemente este apartamento?",
            "consequencia": "Esta ação é irreversível.",
            "url_cancelar": reverse(
                "apartamentos:detalhes",
                args=[apartamento.id],
            ),
        },
    )
