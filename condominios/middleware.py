from urllib.parse import urlencode

from django.shortcuts import redirect
from django.urls import reverse

from .services import obter_condominio_ativo


class CondominioAtivoMiddleware:
    CAMINHOS_LIVRES = (
        "/admin/",
        "/condominios/",
        "/static/",
        "/media/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            not getattr(request.user, "is_authenticated", False)
            or not getattr(request.user, "is_staff", False)
            or request.path.startswith(self.CAMINHOS_LIVRES)
        ):
            return self.get_response(request)
        if obter_condominio_ativo(request) is None:
            destino = reverse("condominios:selecionar")
            query = urlencode({"next": request.get_full_path()})
            return redirect(f"{destino}?{query}")
        return self.get_response(request)
