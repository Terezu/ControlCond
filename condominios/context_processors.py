from .services import (
    listar_condominios_do_request,
    obter_condominio_ativo,
)
from .permissions import Permissao, usuario_possui_permissao


def contexto_condominio(request):
    if not getattr(request.user, "is_authenticated", False):
        return {}
    disponiveis = listar_condominios_do_request(request)
    ativo = obter_condominio_ativo(request)
    permissoes = {
        nome: usuario_possui_permissao(request.user, ativo, valor)
        for nome, valor in {
            "pode_visualizar": Permissao.VISUALIZAR,
            "pode_criar": Permissao.CRIAR_OPERACIONAL,
            "pode_editar": Permissao.EDITAR_OPERACIONAL,
            "pode_excluir": Permissao.EXCLUIR,
            "pode_gerenciar_contratos": Permissao.GERENCIAR_CONTRATOS,
            "pode_gerenciar_apartamentos": Permissao.GERENCIAR_APARTAMENTOS,
            "pode_arquivar_apartamento": Permissao.ARQUIVAR_APARTAMENTO,
            "pode_gerenciar_vinculos": Permissao.GERENCIAR_VINCULOS,
            "pode_gerenciar_leituras": Permissao.GERENCIAR_LEITURAS,
            "pode_gerar_fatura": Permissao.GERAR_FATURA,
            "pode_marcar_fatura_paga": Permissao.MARCAR_FATURA_PAGA,
            "pode_cancelar_fatura": Permissao.CANCELAR_FATURA,
            "pode_estornar_fatura": Permissao.ESTORNAR_FATURA,
            "pode_reabrir_fatura": Permissao.REABRIR_FATURA,
            "pode_editar_valores_financeiros":
                Permissao.EDITAR_VALORES_FINANCEIROS,
            "pode_visualizar_dados_sensiveis":
                Permissao.VISUALIZAR_DADOS_PESSOAIS_SENSIVEIS,
            "pode_gerenciar_usuarios": Permissao.GERENCIAR_USUARIOS,
            "pode_alterar_configuracoes": Permissao.ALTERAR_CONFIGURACOES,
            "pode_gerenciar_financeiro": Permissao.GERENCIAR_FINANCEIRO,
            "pode_executar_acao_critica": Permissao.ACAO_CRITICA,
        }.items()
    } if ativo else {}
    return {
        "condominio_ativo": ativo,
        "condominios_disponiveis": disponiveis,
        "possui_multiplos_condominios": len(disponiveis) > 1,
        **permissoes,
    }
