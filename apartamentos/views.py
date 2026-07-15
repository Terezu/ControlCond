from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from leituras.services import listar_leituras, obter_ultima_leitura

from .forms import ApartamentoForm
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
        "leitura_base_agua": dados["leitura_base_agua"],
        "leitura_base_gas": dados["leitura_base_gas"],
    }

    if apartamento_id is None:
        return cadastrar_apartamento(**argumentos)

    return editar_apartamento(
        apartamento_id,
        **argumentos,
    )


def _redirecionar_para_next(request):
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
        return redirect(proxima_pagina)

    return None


def novo_apartamento(request):
    form = ApartamentoForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        apartamento = _salvar_formulario(form)

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
            "next": request.GET.get("next") or request.POST.get("next"),
        },
    )


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
        apartamento = _salvar_formulario(
            form,
            apartamento_id,
        )

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
            "next": request.GET.get("next") or request.POST.get("next"),
        },
    )


def lista_apartamentos(request):
    return render(
        request,
        "apartamentos/lista.html",
        {
            "apartamentos": listar_apartamentos(),
        },
    )


def detalhes_apartamento(request, apartamento_id):
    try:
        apartamento = consultar_detalhes_apartamento(
            apartamento_id
        )
    except ValueError as exc:
        raise Http404(str(exc)) from exc

    return render(
        request,
        "apartamentos/detalhes.html",
        {
            "apartamento": apartamento,
            "ultima_leitura": obter_ultima_leitura(apartamento),
            "leituras": listar_leituras(apartamento),
            "faturas": apartamento.faturas.all(),
        },
    )
