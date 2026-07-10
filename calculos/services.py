from decimal import Decimal, ROUND_HALF_UP


VALORES_AGUA = {
    0: Decimal("101.99"), 1: Decimal("101.99"), 2: Decimal("101.99"),
    3: Decimal("101.99"), 4: Decimal("101.99"), 5: Decimal("101.99"),
    6: Decimal("105.05"), 7: Decimal("108.20"), 8: Decimal("111.34"),
    9: Decimal("114.49"), 10: Decimal("117.63"), 11: Decimal("135.18"),
    12: Decimal("152.74"), 13: Decimal("170.29"), 14: None,
    15: Decimal("205.41"), 16: None, 17: Decimal("240.70"),
}
VALOR_M3_GAS = Decimal("21.02")


def _calcular_consumo(leitura_anterior, leitura_atual, recurso):
    if leitura_anterior is None:
        return 0
    consumo = leitura_atual - leitura_anterior
    if consumo < 0:
        raise ValueError(
            f"A leitura atual d{recurso} não pode ser menor que a leitura anterior."
        )
    return consumo


def calcular_consumo_agua(leitura_anterior, leitura_atual):
    return _calcular_consumo(leitura_anterior, leitura_atual, "a água")


def calcular_valor_agua(consumo):
    if consumo > 17:
        raise ValueError(
            "O consumo informado é superior ao limite cadastrado (17 m³). "
            "Atualize a tabela tarifária da SANEPAR."
        )
    if consumo not in VALORES_AGUA or VALORES_AGUA[consumo] is None:
        raise ValueError(f"Não existe tarifa cadastrada para {consumo} m³.")
    return VALORES_AGUA[consumo]


def calcular_agua(leitura_anterior, leitura_atual):
    consumo = calcular_consumo_agua(leitura_anterior, leitura_atual)
    return {
        "leitura_anterior": leitura_anterior,
        "leitura_atual": leitura_atual,
        "consumo": consumo,
        "valor": calcular_valor_agua(consumo),
    }


def calcular_consumo_gas(leitura_anterior, leitura_atual):
    return _calcular_consumo(leitura_anterior, leitura_atual, "o gás")


def calcular_valor_gas(consumo_gas):
    return (Decimal(str(consumo_gas)) * VALOR_M3_GAS).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def calcular_gas(leitura_anterior, leitura_atual):
    consumo = calcular_consumo_gas(leitura_anterior, leitura_atual)
    return {
        "leitura_anterior": leitura_anterior,
        "leitura_atual": leitura_atual,
        "consumo": consumo,
        "valor": calcular_valor_gas(consumo),
    }
