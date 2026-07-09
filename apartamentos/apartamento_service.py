from apartamentos.apartamentos import (
    buscar_apartamento_por_id,
    cadastrar_apartamento,
    listar_apartamentos,
)


def criar_apartamento(numero, bloco=None, observacoes=None):
    if not numero:
        raise ValueError("O número do apartamento é obrigatório.")

    return cadastrar_apartamento(
        numero=numero,
        bloco=bloco,
        observacoes=observacoes,
    )


def consultar_apartamento(apartamento_id):
    apartamento = buscar_apartamento_por_id(apartamento_id)

    if apartamento is None:
        raise ValueError("Apartamento não encontrado.")

    return apartamento


def listar_todos_apartamentos():
    return listar_apartamentos()
