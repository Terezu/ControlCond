from calculos.agua import calcular_agua
from calculos.gas import calcular_gas
from faturas.faturas import buscar_fatura_por_id, cadastrar_fatura
from leituras.leituras import cadastrar_leitura


def gerar_fatura(
    apartamento_id,
    leitura_id,
    mes,
    ano,
    leitura_agua_anterior,
    leitura_agua_atual,
    leitura_gas_anterior,
    leitura_gas_atual
):
    resultado_agua = calcular_agua(
        leitura_agua_anterior,
        leitura_agua_atual
    )

    resultado_gas = calcular_gas(
        leitura_gas_anterior,
        leitura_gas_atual
    )

    fatura_id = cadastrar_fatura(
        apartamento_id=apartamento_id,
        leitura_id=leitura_id,
        mes=mes,
        ano=ano,
        consumo_agua=resultado_agua["consumo"],
        consumo_gas=resultado_gas["consumo"],
        valor_agua=resultado_agua["valor"],
        valor_gas=resultado_gas["valor"],
    )

    return {
        "fatura_id": fatura_id,
        "apartamento_id": apartamento_id,
        "leitura_id": leitura_id,
        "mes": mes,
        "ano": ano,
        "agua": resultado_agua,
        "gas": resultado_gas,
        "valor_total": resultado_agua["valor"] + resultado_gas["valor"],
        "status": "pendente",
    }


def consultar_fatura(fatura_id):
    fatura = buscar_fatura_por_id(fatura_id)

    if fatura is None:
        raise ValueError("Fatura não encontrada.")

    return fatura


def gerar_fatura_mensal(
    apartamento_id,
    mes,
    ano,
    leitura_agua,
    leitura_gas,
    consumo_agua,
    consumo_gas,
    valor_agua=0,
    valor_gas=0
):
    leitura_id = cadastrar_leitura(
        apartamento_id=apartamento_id,
        mes=mes,
        ano=ano,
        leitura_agua=leitura_agua,
        leitura_gas=leitura_gas
    )

    return cadastrar_fatura(
        apartamento_id=apartamento_id,
        leitura_id=leitura_id,
        mes=mes,
        ano=ano,
        consumo_agua=consumo_agua,
        consumo_gas=consumo_gas,
        valor_agua=valor_agua,
        valor_gas=valor_gas
    )
