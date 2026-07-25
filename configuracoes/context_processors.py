from .services import obter_configuracao
from condominios.services import obter_condominio_ativo


def configuracao_global(request):
    if not getattr(request.user, "is_authenticated", False):
        return {"nome_sistema": "ControlCond"}
    condominio = obter_condominio_ativo(request)
    if condominio is None:
        return {"nome_sistema": "ControlCond"}
    configuracao = obter_configuracao(condominio)
    return {
        "nome_sistema": configuracao.nome or "ControlCond",
    }
