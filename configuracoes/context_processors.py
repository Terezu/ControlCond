from .services import obter_configuracao


def configuracao_global(request):
    configuracao = obter_configuracao(request=request)
    return {
        "nome_sistema": configuracao.nome or "ControlCond",
    }
