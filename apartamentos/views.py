from django.shortcuts import render

from .services import listar_apartamentos


def lista_apartamentos(request):
    return render(request, "apartamentos/lista.html", {
        "apartamentos": listar_apartamentos(),
    })

