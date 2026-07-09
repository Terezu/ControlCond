from apartamentos.apartamentos import buscar_apartamento_por_id
from leituras.leituras import (
    buscar_ultimas_leituras,
    cadastrar_leitura,
    listar_leituras,
)


def registrar_leitura(apartamento_id, mes, ano, leitura_agua=None, leitura_gas=None):
    apartamento = buscar_apartamento_por_id(apartamento_id)

    if apartamento is None:
        raise ValueError("Apartamento não encontrado.")

    return cadastrar_leitura(
        apartamento_id=apartamento_id,
        mes=mes,
        ano=ano,
        leitura_agua=leitura_agua,
        leitura_gas=leitura_gas,
    )


def consultar_ultimas_leituras(apartamento_id):
    return buscar_ultimas_leituras(apartamento_id)


def listar_todas_leituras():
    return listar_leituras()
