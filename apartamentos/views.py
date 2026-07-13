from django.http import Http404
from django.shortcuts import render

from .services import (
    consultar_detalhes_apartamento,
    listar_apartamentos,
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
            "ultima_leitura": ultima_leitura,
        }
    )
