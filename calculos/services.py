from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP


VALORES_AGUA = {
    0: Decimal("101.99"),
    1: Decimal("101.99"),
    2: Decimal("101.99"),
    3: Decimal("101.99"),
    4: Decimal("101.99"),
    5: Decimal("101.99"),
    6: Decimal("105.05"),
    7: Decimal("108.20"),
    8: Decimal("111.34"),
    9: Decimal("114.49"),
    10: Decimal("117.63"),
    11: Decimal("135.18"),
    12: Decimal("152.74"),
    13: Decimal("170.29"),
    14: None,
    15: Decimal("205.41"),
    16: None,
    17: Decimal("240.70"),
}
VALOR_M3_GAS = Decimal("21.02")


def _decimal_finito(valor, descricao):
    try:
        decimal = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{descricao} deve ser um número válido.") from exc

    if not decimal.is_finite():
        raise ValueError(f"{descricao} deve ser um número finito.")

    return decimal


def _calcular_consumo(leitura_anterior, leitura_atual, nome_recurso):
    if leitura_anterior is None:
        raise ValueError(
            f"Informe a leitura anterior de {nome_recurso}, inclusive para "
            "a primeira medição do apartamento."
        )
    if leitura_atual is None:
        raise ValueError(f"Informe a leitura atual de {nome_recurso}.")

    consumo = (
        _decimal_finito(
            leitura_atual,
            f"A leitura atual de {nome_recurso}",
        )
        - _decimal_finito(
            leitura_anterior,
            f"A leitura anterior de {nome_recurso}",
        )
    )

    if consumo < 0:
        raise ValueError(
            f"A leitura atual de {nome_recurso} não pode ser menor que a anterior."
        )

    try:
        return int(
            consumo.quantize(
                Decimal("1"),
                rounding=ROUND_DOWN,
            )
        )
    except (InvalidOperation, OverflowError) as exc:
        raise ValueError(
            f"O consumo de {nome_recurso} excede o limite calculável."
        ) from exc


def calcular_consumo_agua(leitura_anterior, leitura_atual):
    return _calcular_consumo(leitura_anterior, leitura_atual, "água")


def calcular_valor_agua(consumo):
    consumo_decimal = _decimal_finito(consumo, "O consumo de água")
    if consumo_decimal < 0:
        raise ValueError("O consumo de água não pode ser negativo.")
    if consumo_decimal > 17:
        raise ValueError(
            "O consumo informado é superior ao limite cadastrado (17 m³). "
            "Atualize a tabela tarifária da SANEPAR."
        )
    if consumo_decimal != consumo_decimal.to_integral_value():
        raise ValueError("O consumo de água deve ser um número inteiro.")

    consumo = int(consumo_decimal)
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
    return _calcular_consumo(leitura_anterior, leitura_atual, "gás")


def calcular_valor_gas(consumo_gas):
    consumo = _decimal_finito(consumo_gas, "O consumo de gás")
    if consumo < 0:
        raise ValueError("O consumo de gás não pode ser negativo.")

    try:
        return (consumo * VALOR_M3_GAS).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    except InvalidOperation as exc:
        raise ValueError("O consumo de gás excede o limite calculável.") from exc


def calcular_gas(leitura_anterior, leitura_atual):
    consumo = calcular_consumo_gas(leitura_anterior, leitura_atual)
    return {
        "leitura_anterior": leitura_anterior,
        "leitura_atual": leitura_atual,
        "consumo": consumo,
        "valor": calcular_valor_gas(consumo),
    }
