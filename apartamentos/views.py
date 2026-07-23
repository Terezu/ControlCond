from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import Http404
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from .forms import ApartamentoForm, FiltrarApartamentosForm
from .services import (
    cadastrar_apartamento,
    consultar_apartamento,
    consultar_detalhes_apartamento,
    editar_apartamento,
    listar_apartamentos,
)


def _salvar_formulario(form, apartamento_id=None):
    dados = form.cleaned_data

    argumentos = {
        "numero": dados["numero"],
        "bloco": dados["bloco"],
        "observacoes": dados["observacoes"],
        "valor_aluguel": dados["valor_aluguel"],
        "leitura_base_agua": dados["leitura_base_agua"],
        "leitura_base_gas": dados["leitura_base_gas"],
    }

    if apartamento_id is None:
        return cadastrar_apartamento(**argumentos)

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
    form = ApartamentoForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            apartamento = _salvar_formulario(form)
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
    try:
        apartamento = consultar_apartamento(apartamento_id)
    except ValueError as exc:
        raise Http404(str(exc)) from exc

    form = ApartamentoForm(
        request.POST or None,
        instance=apartamento,
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

    paginator = Paginator(listar_apartamentos(**filtros), 10)
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
        apartamento = consultar_detalhes_apartamento(
            apartamento_id
        )
    except ValueError as exc:
        raise Http404(str(exc)) from exc

    leituras = list(apartamento.leituras.all())
    faturas = list(apartamento.faturas.all())

    return render(
        request,
        "apartamentos/detalhes.html",
        {
            "apartamento": apartamento,
            "ultima_leitura": leituras[0] if leituras else None,
            "leituras": leituras,
            "faturas": faturas,
        },
    )
