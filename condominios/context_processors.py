from .services import (
    listar_condominios_do_request,
    obter_condominio_ativo,
)


def contexto_condominio(request):
    if not getattr(request.user, "is_authenticated", False):
        return {}
    disponiveis = listar_condominios_do_request(request)
    ativo = obter_condominio_ativo(request)
    return {
        "condominio_ativo": ativo,
        "condominios_disponiveis": disponiveis,
        "possui_multiplos_condominios": len(disponiveis) > 1,
    }
