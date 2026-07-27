from .services import obter_configuracao
from .models import (
    COR_DESTAQUE_PADRAO,
    COR_PRIMARIA_PADRAO,
    COR_SECUNDARIA_PADRAO,
)
from condominios.services import obter_condominio_ativo


CORES_PADRAO = {
    "cor_primaria": COR_PRIMARIA_PADRAO,
    "cor_secundaria": COR_SECUNDARIA_PADRAO,
    "cor_destaque": COR_DESTAQUE_PADRAO,
}


def _componentes_rgb(cor):
    cor = cor.lstrip("#")
    return ", ".join(
        str(int(cor[indice:indice + 2], 16))
        for indice in (0, 2, 4)
    )


def _cor_texto_contraste(cor):
    vermelho, verde, azul = (
        int(cor[indice:indice + 2], 16) / 255
        for indice in (1, 3, 5)
    )
    luminancia = (
        (0.2126 * vermelho)
        + (0.7152 * verde)
        + (0.0722 * azul)
    )
    return "#212529" if luminancia > 0.58 else "#FFFFFF"


def _contexto_tema(**cores):
    valores = {
        nome: cores.get(nome) or padrao
        for nome, padrao in CORES_PADRAO.items()
    }
    return {
        **valores,
        "cor_primaria_padrao": COR_PRIMARIA_PADRAO,
        "cor_secundaria_padrao": COR_SECUNDARIA_PADRAO,
        "cor_destaque_padrao": COR_DESTAQUE_PADRAO,
        "cor_primaria_rgb": _componentes_rgb(valores["cor_primaria"]),
        "cor_secundaria_rgb": _componentes_rgb(valores["cor_secundaria"]),
        "cor_destaque_rgb": _componentes_rgb(valores["cor_destaque"]),
        "cor_texto_primaria": _cor_texto_contraste(
            valores["cor_primaria"]
        ),
        "cor_texto_secundaria": _cor_texto_contraste(
            valores["cor_secundaria"]
        ),
    }


def configuracao_global(request):
    if not getattr(request.user, "is_authenticated", False):
        return {
            "nome_sistema": "ControlCond",
            **_contexto_tema(),
        }
    condominio = obter_condominio_ativo(request)
    if condominio is None:
        return {
            "nome_sistema": "ControlCond",
            **_contexto_tema(),
        }
    configuracao = obter_configuracao(condominio)
    return {
        "nome_sistema": configuracao.nome or "ControlCond",
        **_contexto_tema(
            cor_primaria=configuracao.cor_primaria,
            cor_secundaria=configuracao.cor_secundaria,
            cor_destaque=configuracao.cor_destaque,
        ),
    }
