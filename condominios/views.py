from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .services import (
    definir_condominio_ativo,
    listar_condominios_do_request,
)


def _next_seguro(request):
    destino = request.POST.get("next") or request.GET.get("next")
    if destino and url_has_allowed_host_and_scheme(
        destino,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return destino
    return reverse("dashboard:inicio")


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def selecionar_condominio(request):
    condominios = listar_condominios_do_request(request)
    if request.method == "POST":
        condominio_id = request.POST.get("condominio")
        condominio = next(
            (
                item for item in condominios
                if str(item.pk) == str(condominio_id)
            ),
            None,
        )
        if condominio is None:
            raise PermissionDenied("Condomínio indisponível.")
        definir_condominio_ativo(request, condominio)
        request._condominio_ativo = condominio
        return redirect(_next_seguro(request))

    return render(
        request,
        "condominios/selecionar.html",
        {
            "condominios": condominios,
            "next": _next_seguro(request),
        },
    )
