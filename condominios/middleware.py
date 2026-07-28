from urllib.parse import urlencode

from django.shortcuts import redirect
from django.urls import reverse

from .services import obter_condominio_ativo
from .permissions import Permissao, usuario_possui_permissao
from django.core.exceptions import PermissionDenied


class CondominioAtivoMiddleware:
    CAMINHOS_LIVRES = (
        "/admin/",
        "/condominios/",
        "/conta/",
        "/static/",
        "/media/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            not getattr(request.user, "is_authenticated", False)
            or request.path.startswith(self.CAMINHOS_LIVRES)
        ):
            return self.get_response(request)
        condominio = obter_condominio_ativo(request)
        if condominio is None:
            destino = reverse("condominios:selecionar")
            query = urlencode({"next": request.get_full_path()})
            return redirect(f"{destino}?{query}")
        if request.path.startswith("/configuracoes/") and not (
            usuario_possui_permissao(
                request.user, condominio, Permissao.ALTERAR_CONFIGURACOES
            )
        ):
            raise PermissionDenied(
                "Você não possui permissão para alterar configurações."
            )
        caminho = request.path.lower()
        segmentos_exclusao = ("/excluir/",)
        segmentos_escrita = (
            "/novo/",
            "/nova/",
            "/editar/",
            "/gerar/",
            "/fechamento-mensal/",
            "/encerrar/",
            "/valores/",
        )
        segmentos_criticos = (
            "/marcar-como-paga/",
            "/cancelar/",
            "/estornar-pagamento/",
            "/reabrir/",
        )
        permissao_caminho = None
        if any(segmento in caminho for segmento in segmentos_criticos):
            permissao_caminho = Permissao.GERENCIAR_FINANCEIRO
        elif any(segmento in caminho for segmento in segmentos_exclusao):
            permissao_caminho = Permissao.EXCLUIR
        elif (
            request.method in {"GET", "HEAD", "OPTIONS"}
            and any(segmento in caminho for segmento in segmentos_escrita)
        ):
            permissao_caminho = Permissao.CRIAR_OPERACIONAL
        if permissao_caminho and not usuario_possui_permissao(
            request.user, condominio, permissao_caminho
        ):
            raise PermissionDenied(
                "Você não possui permissão para acessar esta ação."
            )
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not (
            usuario_possui_permissao(
                request.user, condominio, Permissao.CRIAR_OPERACIONAL
            )
        ):
            raise PermissionDenied(
                "Seu perfil permite somente consulta."
            )
        return self.get_response(request)
