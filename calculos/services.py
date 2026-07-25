from decimal import (
    Decimal,
    DecimalException,
    InvalidOperation,
    ROUND_DOWN,
    ROUND_HALF_UP,
)

from configuracoes.services import obter_configuracao, obter_faixas_agua_ativas

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
    faixas = obter_faixas_agua_ativas()
    primeira = faixas[0]
    if (
        primeira.consumo_final is None
        or consumo <= primeira.consumo_final
    ):
        return primeira.valor.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    valor = primeira.valor
    try:
        for faixa in faixas[1:]:
            if consumo < faixa.consumo_inicial:
                break
            final_aplicado = (
                consumo
                if faixa.consumo_final is None
                else min(consumo, faixa.consumo_final)
            )
            quantidade = final_aplicado - faixa.consumo_inicial + 1
            valor += faixa.valor * quantidade
            if (
                faixa.consumo_final is None
                or consumo <= faixa.consumo_final
            ):
                break
        else:
            raise ValueError(
                "A tabela de água não cobre o consumo informado."
            )
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


def calcular_valor_gas(consumo_gas, valor_m3_gas=None):
    consumo = _decimal_finito(consumo_gas, "O consumo de gás")
    if consumo < 0:
        raise ValueError("O consumo de gás não pode ser negativo.")
    if valor_m3_gas is None:
        valor_m3_gas = obter_configuracao().valor_m3_gas
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
    valor_m3_gas=None,
):
    consumo = calcular_consumo_gas(leitura_anterior, leitura_atual)
    return {
        "leitura_anterior": leitura_anterior,
        "leitura_atual": leitura_atual,
        "consumo": consumo,
        "valor": calcular_valor_gas(consumo, valor_m3_gas),
    }
