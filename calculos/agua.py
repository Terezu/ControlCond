VALORES_AGUA = {
    0: 101.99,
    1: 101.99,
    2: 101.99,
    3: 101.99,
    4: 101.99,
    5: 101.99,
    6: 105.05,
    7: 108.20,
    8: 111.34,
    9: 114.49,
    10: 117.63,
    11: 135.18,
    12: 152.74,
    13: 170.29,
    14: None,
    15: 205.41,
    16: None,
    17: 240.70,
}


def calcular_consumo_agua(leitura_anterior, leitura_atual):
    if leitura_anterior is None:
        return 0

    consumo = leitura_atual - leitura_anterior

    if consumo < 0:
        raise ValueError(
            "A leitura atual da água não pode ser menor que a leitura anterior."
        )

    return consumo


def calcular_valor_agua(consumo):
    if consumo > 17:
        raise ValueError(
            "O consumo informado é superior ao limite cadastrado (17 m³)."
            "Atualize a tabela tarifária da SANEPAR"
        )
    
    if consumo not in VALORES_AGUA:
        raise ValueError(
            f"Não existe tarifa cadastrada para {consumo}m³."
        )

    valor = VALORES_AGUA[consumo]

    if valor is None:
        raise ValueError(
            f"A tarifa para {consumo}m³ ainda não foi cadastrada."
        )

    return valor


def calcular_agua(leitura_anterior, leitura_atual):
    consumo = calcular_consumo_agua(leitura_anterior, leitura_atual)
    valor = calcular_valor_agua(consumo)

    return {
        "leitura_anterior": leitura_anterior,
        "leitura_atual": leitura_atual,
        "consumo": consumo,
        "valor": valor,
    }
