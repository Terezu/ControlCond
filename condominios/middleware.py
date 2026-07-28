from urllib.parse import urlencode

from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse

from .permissions import Permissao, usuario_possui_permissao
from .services import obter_condominio_ativo


class CondominioAtivoMiddleware:
    CAMINHOS_LIVRES = (
        "/admin/", "/condominios/", "/conta/", "/static/", "/media/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _permissao_da_rota(caminho):
        if caminho.startswith("/configuracoes/globais/"):
            return Permissao.VISUALIZAR_CONFIGURACOES_GLOBAIS
        if caminho.startswith("/configuracoes/institucionais/"):
            return (
                Permissao.ALTERAR_CONFIGURACOES_INSTITUCIONAIS
                if "/editar/" in caminho
                else Permissao.VISUALIZAR_CONFIGURACOES_INSTITUCIONAIS
            )
        if caminho.startswith("/configuracoes/operacionais/"):
            return (
                Permissao.ALTERAR_CONFIGURACOES_OPERACIONAIS
                if "/editar/" in caminho
                else Permissao.VISUALIZAR_CONFIGURACOES_OPERACIONAIS
            )
        if caminho.startswith("/usuarios/perfil/"):
            return None
        if (
            caminho.startswith("/faturas/")
            and "/excluir/" in caminho
        ):
            return Permissao.CANCELAR_FATURA
        regras = (
            ("/usuarios/", Permissao.GERENCIAR_USUARIOS),
            ("/rescindir/", Permissao.RESCINDIR_CONTRATO),
            ("/marcar-como-paga/", Permissao.MARCAR_FATURA_PAGA),
            ("/cancelar/", Permissao.CANCELAR_FATURA),
            ("/estornar-pagamento/", Permissao.ESTORNAR_FATURA),
            ("/reabrir/", Permissao.REABRIR_FATURA),
            ("/faturas/gerar/", Permissao.GERAR_FATURA),
            ("/faturas/fechamento-mensal/", Permissao.GERAR_FATURA),
            ("/valores/", Permissao.EDITAR_VALORES_FINANCEIROS),
        )
        for trecho, permissao in regras:
            if trecho in caminho:
                return permissao
        if caminho.startswith("/apartamentos/"):
            if "/excluir/" in caminho:
                return Permissao.ARQUIVAR_APARTAMENTO
            if "/novo/" in caminho or "/editar/" in caminho:
                return Permissao.GERENCIAR_APARTAMENTOS
        if caminho.startswith("/contratos/") and (
            "/novo/" in caminho or "/editar/" in caminho
        ):
            return Permissao.GERENCIAR_CONTRATOS
        if caminho.startswith("/leituras/") and (
            "/nova/" in caminho or "/excluir/" in caminho
        ):
            return Permissao.GERENCIAR_LEITURAS
        if caminho.startswith("/pessoas/") and any(
            trecho in caminho
            for trecho in ("/nova/", "/editar/", "/vinculos/")
        ):
            return Permissao.GERENCIAR_VINCULOS
        return None

    def __call__(self, request):
        if (
            not getattr(request.user, "is_authenticated", False)
            or request.path.startswith(self.CAMINHOS_LIVRES)
        ):
            return self.get_response(request)
        if request.path.lower().startswith("/configuracoes/globais/"):
            if not getattr(request.user, "is_superuser", False):
                raise PermissionDenied(
                    "Somente Administradores Globais acessam esta área."
                )
            return self.get_response(request)
        condominio = obter_condominio_ativo(request)
        if condominio is None:
            destino = reverse("condominios:selecionar")
            query = urlencode({"next": request.get_full_path()})
            return redirect(f"{destino}?{query}")
        permissao = self._permissao_da_rota(request.path.lower())
        if permissao and not usuario_possui_permissao(
            request.user, condominio, permissao
        ):
            raise PermissionDenied(
                "Você não possui permissão para acessar esta ação."
            )
        if (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and permissao is None
            and not usuario_possui_permissao(
                request.user, condominio, Permissao.CRIAR_OPERACIONAL
            )
        ):
            raise PermissionDenied("Seu cargo não permite esta operação.")
        return self.get_response(request)
