from functools import wraps

from django.core.exceptions import PermissionDenied

from .models import VinculoUsuarioCondominio
from .services import obter_condominio_ativo, obter_vinculo_usuario_condominio


class Permissao:
    VISUALIZAR = "visualizar"
    GERENCIAR_CONTRATOS = "gerenciar_contratos"
    GERENCIAR_APARTAMENTOS = "gerenciar_apartamentos"
    ARQUIVAR_APARTAMENTO = "arquivar_apartamento"
    GERENCIAR_VINCULOS = "gerenciar_vinculos"
    GERENCIAR_LEITURAS = "gerenciar_leituras"
    GERAR_FATURA = "gerar_fatura"
    MARCAR_FATURA_PAGA = "marcar_fatura_paga"
    CANCELAR_FATURA = "cancelar_fatura"
    ESTORNAR_FATURA = "estornar_fatura"
    REABRIR_FATURA = "reabrir_fatura"
    EDITAR_VALORES_FINANCEIROS = "editar_valores_financeiros"
    VISUALIZAR_CONFIGURACOES_INSTITUCIONAIS = (
        "visualizar_configuracoes_institucionais"
    )
    ALTERAR_CONFIGURACOES_INSTITUCIONAIS = (
        "alterar_configuracoes_institucionais"
    )
    VISUALIZAR_CONFIGURACOES_OPERACIONAIS = (
        "visualizar_configuracoes_operacionais"
    )
    ALTERAR_CONFIGURACOES_OPERACIONAIS = (
        "alterar_configuracoes_operacionais"
    )
    VISUALIZAR_CONFIGURACOES_GLOBAIS = "visualizar_configuracoes_globais"
    ALTERAR_CONFIGURACOES_GLOBAIS = "alterar_configuracoes_globais"
    # Alias legado: equivale somente à edição operacional.
    ALTERAR_CONFIGURACOES = ALTERAR_CONFIGURACOES_OPERACIONAIS
    GERENCIAR_USUARIOS = "gerenciar_usuarios"
    VISUALIZAR_DADOS_PESSOAIS_SENSIVEIS = (
        "visualizar_dados_pessoais_sensiveis"
    )
    VISUALIZAR_AUDITORIA = "visualizar_auditoria"
    ACAO_CRITICA = "acao_critica"
    RESCINDIR_CONTRATO = "rescindir_contrato"
    ACESSAR_ARQUIVADOS = "acessar_arquivados"
    RESTAURAR_ARQUIVADO = "restaurar_arquivado"
    MANUTENCAO_GLOBAL = "manutencao_global"
    EXCLUIR_USUARIO_PERMANENTEMENTE = (
        "excluir_usuario_permanentemente"
    )

    # Compatibilidade temporária para chamadas existentes.
    CRIAR_OPERACIONAL = "criar_operacional"
    EDITAR_OPERACIONAL = "editar_operacional"
    EXCLUIR = "excluir"
    GERENCIAR_FINANCEIRO = "gerenciar_financeiro"


P = VinculoUsuarioCondominio.Papel

PERMISSOES_PROPRIETARIO = frozenset({
    Permissao.VISUALIZAR,
    Permissao.GERENCIAR_USUARIOS,
    Permissao.VISUALIZAR_DADOS_PESSOAIS_SENSIVEIS,
    Permissao.VISUALIZAR_AUDITORIA,
    Permissao.RESCINDIR_CONTRATO,
    Permissao.VISUALIZAR_CONFIGURACOES_INSTITUCIONAIS,
    Permissao.ALTERAR_CONFIGURACOES_INSTITUCIONAIS,
    Permissao.VISUALIZAR_CONFIGURACOES_OPERACIONAIS,
})

PERMISSOES_ADMINISTRADOR = frozenset({
    Permissao.VISUALIZAR,
    Permissao.GERENCIAR_CONTRATOS,
    Permissao.GERENCIAR_APARTAMENTOS,
    Permissao.ARQUIVAR_APARTAMENTO,
    Permissao.GERENCIAR_VINCULOS,
    Permissao.GERENCIAR_LEITURAS,
    Permissao.GERAR_FATURA,
    Permissao.MARCAR_FATURA_PAGA,
    Permissao.CANCELAR_FATURA,
    Permissao.ESTORNAR_FATURA,
    Permissao.REABRIR_FATURA,
    Permissao.EDITAR_VALORES_FINANCEIROS,
    Permissao.VISUALIZAR_CONFIGURACOES_OPERACIONAIS,
    Permissao.ALTERAR_CONFIGURACOES_OPERACIONAIS,
    Permissao.GERENCIAR_USUARIOS,
    Permissao.VISUALIZAR_DADOS_PESSOAIS_SENSIVEIS,
    Permissao.VISUALIZAR_AUDITORIA,
    Permissao.CRIAR_OPERACIONAL,
    Permissao.EDITAR_OPERACIONAL,
    Permissao.EXCLUIR,
    Permissao.GERENCIAR_FINANCEIRO,
})

PERMISSOES_PROPRIETARIO_ADMINISTRATIVO = (
    PERMISSOES_PROPRIETARIO | PERMISSOES_ADMINISTRADOR
)

PERMISSOES_OPERADOR = frozenset({
    Permissao.VISUALIZAR,
    Permissao.GERENCIAR_LEITURAS,
    Permissao.GERAR_FATURA,
    Permissao.MARCAR_FATURA_PAGA,
})

PERMISSOES_CONSULTA = frozenset({Permissao.VISUALIZAR})

TODAS_PERMISSOES = frozenset(
    valor for nome, valor in vars(Permissao).items()
    if nome.isupper() and isinstance(valor, str)
)

PERMISSOES_NEGADAS_AO_GLOBAL = frozenset({
    Permissao.ALTERAR_CONFIGURACOES_INSTITUCIONAIS,
    Permissao.ALTERAR_CONFIGURACOES_OPERACIONAIS,
})

MATRIZ_PERMISSOES = {
    P.PROPRIETARIO: PERMISSOES_PROPRIETARIO,
    P.PROPRIETARIO_ADMINISTRATIVO:
        PERMISSOES_PROPRIETARIO_ADMINISTRATIVO,
    P.ADMINISTRADOR: PERMISSOES_ADMINISTRADOR,
    P.OPERADOR: PERMISSOES_OPERADOR,
    P.CONSULTA: PERMISSOES_CONSULTA,
}


def papel_atual(usuario, condominio):
    vinculo = obter_vinculo_usuario_condominio(usuario, condominio)
    return vinculo.papel if vinculo else None


def usuario_possui_permissao(usuario, condominio, permissao):
    return permissao in permissoes_do_usuario(usuario, condominio)


def exigir_permissao(usuario, condominio, permissao):
    if not usuario_possui_permissao(usuario, condominio, permissao):
        raise PermissionDenied("Você não possui permissão para esta ação.")


def permissoes_do_usuario(usuario, condominio):
    if not getattr(usuario, "is_authenticated", False):
        return frozenset()
    if getattr(usuario, "is_superuser", False):
        return TODAS_PERMISSOES - PERMISSOES_NEGADAS_AO_GLOBAL
    return MATRIZ_PERMISSOES.get(papel_atual(usuario, condominio), frozenset())


def permissao_condominio_required(permissao):
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login
                return redirect_to_login(request.get_full_path())
            condominio = obter_condominio_ativo(request)
            exigir_permissao(request.user, condominio, permissao)
            return view(request, *args, **kwargs)
        return wrapper
    return decorator
