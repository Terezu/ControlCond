from django.shortcuts import render

from .services import listar_faturas


def lista_faturas(request):
    return render(request, "faturas/lista.html", {"faturas": listar_faturas()})

