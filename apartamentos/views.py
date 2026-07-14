from django.http import Http404
from django.contrib import messages
from django.shortcuts import redirect, render

from .forms import ApartamentoForm

from .services import (
    consultar_detalhes_apartamento,
    cadastrar_apartamento,
    consultar_apartamento,
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
    return editar_apartamento(apartamento_id, **argumentos)


def novo_apartamento(request):
    form = ApartamentoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        apartamento = _salvar_formulario(form)
        messages.success(request, "Apartamento cadastrado com sucesso.")
        return redirect("apartamentos:detalhes", apartamento_id=apartamento.id)
    return render(
        request,
        "apartamentos/formulario.html",
        {"form": form, "titulo": "Cadastrar apartamento"},
    )


def editar_dados_apartamento(request, apartamento_id):
    try:
        apartamento = consultar_apartamento(apartamento_id)
    except ValueError as exc:
        raise Http404(str(exc)) from exc

    form = ApartamentoForm(request.POST or None, instance=apartamento)
    if request.method == "POST" and form.is_valid():
        apartamento = _salvar_formulario(form, apartamento_id)
        messages.success(request, "Apartamento atualizado com sucesso.")
        return redirect("apartamentos:detalhes", apartamento_id=apartamento.id)
    return render(
        request,
        "apartamentos/formulario.html",
        {
            "form": form,
            "titulo": "Editar apartamento",
            "apartamento": apartamento,
        },
    )

from leituras.services import (
    listar_leituras,
    obter_ultima_leitura,
)


def lista_apartamentos(request):
    return render(
        request,
        "apartamentos/lista.html",
        {
            "apartamentos": listar_apartamentos(),
        }
    )


def detalhes_apartamento(request, apartamento_id):
    try:
        apartamento = consultar_detalhes_apartamento(apartamento_id)
    except ValueError as exc:
        raise Http404(str(exc)) from exc

    leituras = list(apartamento.leituras.all())
    faturas = list(apartamento.faturas.all())

    ultima_leitura = leituras[0] if leituras else None

    return render(
        request,
        "apartamentos/detalhes.html",
        {
            "apartamento": apartamento,
            "leituras": leituras,
            "faturas": faturas,
            "apartamento": apartamento,
            "ultima_leitura": obter_ultima_leitura(apartamento),
            "leituras": listar_leituras(apartamento),
        }
    )
