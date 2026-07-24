from decimal import (
    Decimal,
    DecimalException,
    InvalidOperation,
    ROUND_DOWN,
    ROUND_HALF_UP,
)


# Tarifa residencial normal de água e esgoto de Curitiba, vigente desde
# 17/05/2026. Fonte: https://www.sanepar.com.br/tarifas. O primeiro valor é a
# cobrança total até 5 m³; os seguintes são valores por m³ em cada faixa.
# Os números 5, 5, 5 e 10 não são os limites finais.
# Eles representam quantos metros cúbicos cabem em cada faixa. None significa “sem limite”.
TARIFA_AGUA_ATE_5_M3 = Decimal("101.91")
FAIXAS_TARIFA_AGUA = (
    (5, Decimal("3.15")),
    (5, Decimal("17.56")),
    (5, Decimal("17.65")),
    (10, Decimal("17.80")),
    (None, Decimal("30.12")),
)
# Padrão legado para chamadas matemáticas isoladas. No fluxo operacional,
# faturas.services sempre informa a tarifa obtida de ConfiguracaoCondominio.
VALOR_M3_GAS_PADRAO = Decimal("21.02")


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
    if consumo_decimal != consumo_decimal.to_integral_value():
        raise ValueError("O consumo de água deve ser um número inteiro.")

    consumo = int(consumo_decimal)
    if consumo <= 5:
        return TARIFA_AGUA_ATE_5_M3

    valor = TARIFA_AGUA_ATE_5_M3
    restante = consumo - 5
    try:
        for largura, tarifa_m3 in FAIXAS_TARIFA_AGUA:
            quantidade = restante if largura is None else min(restante, largura)
            valor += tarifa_m3 * quantidade
            restante -= quantidade
            if restante == 0:
                break
        return valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except DecimalException as exc:
        raise ValueError(
            "O consumo de água excede o limite calculável."
        ) from exc


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


def calcular_valor_gas(consumo_gas, valor_m3_gas=VALOR_M3_GAS_PADRAO):
    consumo = _decimal_finito(consumo_gas, "O consumo de gás")
    if consumo < 0:
        raise ValueError("O consumo de gás não pode ser negativo.")
    valor_m3_gas = _decimal_finito(
        valor_m3_gas,
        "O valor do m³ do gás",
    )
    if valor_m3_gas < 0:
        raise ValueError("O valor do m³ do gás não pode ser negativo.")

    try:
        return (consumo * valor_m3_gas).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    except InvalidOperation as exc:
        raise ValueError("O consumo de gás excede o limite calculável.") from exc


def calcular_gas(
    leitura_anterior,
    leitura_atual,
    valor_m3_gas=VALOR_M3_GAS_PADRAO,
):
    consumo = calcular_consumo_gas(leitura_anterior, leitura_atual)
    return {
        "leitura_anterior": leitura_anterior,
        "leitura_atual": leitura_atual,
        "consumo": consumo,
        "valor": calcular_valor_gas(consumo, valor_m3_gas),
    }
