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
