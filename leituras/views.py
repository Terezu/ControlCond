from django.shortcuts import render

from .services import listar_leituras


def lista_leituras(request):
    return render(request, "leituras/lista.html", {"leituras": listar_leituras()})

