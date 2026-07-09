VALOR_M3_GAS = 21.02


def calcular_consumo_gas(leitura_anterior, leitura_atual):
    if leitura_anterior is None:
        return 0

    consumo = leitura_atual - leitura_anterior

    if consumo < 0:
        raise ValueError(
            "A leitura atual do gás não pode ser menor que a leitura anterior."
        )

    return consumo


def calcular_valor_gas(consumo_gas):
    return round(consumo_gas * VALOR_M3_GAS, 2)


def calcular_gas(leitura_anterior, leitura_atual):
    consumo = calcular_consumo_gas(leitura_anterior, leitura_atual)
    valor = calcular_valor_gas(consumo)

    return {
        "leitura_anterior": leitura_anterior,
        "leitura_atual": leitura_atual,
        "consumo": consumo,
        "valor": valor,
    }
