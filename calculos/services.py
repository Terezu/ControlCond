from decimal import (
    Decimal,
    DecimalException,
    InvalidOperation,
    ROUND_DOWN,
    ROUND_HALF_UP,
)
from datetime import date

from configuracoes.services import (
    ConsumoSemFaixaError,
    obter_faixas_agua_ativas,
    obter_tabela_agua_vigente,
    obter_tarifa_gas_vigente,
)

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


def calcular_valor_agua(
    consumo, mes=None, ano=None, *, tabela=None, condominio=None
):
    if condominio is None and tabela is None:
        from condominios.models import Condominio
        condominio = Condominio.objects.order_by("id").first()
    consumo_decimal = _decimal_finito(consumo, "O consumo de água")
    if consumo_decimal < 0:
        raise ValueError("O consumo de água não pode ser negativo.")
    if consumo_decimal != consumo_decimal.to_integral_value():
        raise ValueError("O consumo de água deve ser um número inteiro.")

    consumo = int(consumo_decimal)
    if tabela is None:
        if mes is None or ano is None:
            faixas = obter_faixas_agua_ativas(condominio)
        else:
            tabela = obter_tabela_agua_vigente(condominio, mes, ano)
            faixas = tuple(
                tabela.faixas.filter(ativa=True).order_by("ordem", "id")
            )
    else:
        faixas = tuple(
            tabela.faixas.filter(ativa=True).order_by("ordem", "id")
        )
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
            raise ConsumoSemFaixaError(
                "A tabela de água não cobre o consumo informado."
            )
        return valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except DecimalException as exc:
        raise ValueError(
            "O consumo de água excede o limite calculável."
        ) from exc


def calcular_agua(
    leitura_anterior, leitura_atual, mes=None, ano=None, *, condominio=None
):
    consumo = calcular_consumo_agua(leitura_anterior, leitura_atual)
    tabela = (
        obter_tabela_agua_vigente(condominio, mes, ano)
        if mes is not None and ano is not None
        else None
    )
    faixas = (
        tuple(tabela.faixas.filter(ativa=True).order_by("ordem", "id"))
        if tabela is not None
        else obter_faixas_agua_ativas(condominio)
    )
    faixa_aplicada = next(
        (
            faixa for faixa in faixas
            if faixa.consumo_final is None or consumo <= faixa.consumo_final
        ),
        None,
    )
    if faixa_aplicada is None:
        raise ConsumoSemFaixaError(
            "A tabela de água não cobre o consumo informado."
        )
    return {
        "leitura_anterior": leitura_anterior,
        "leitura_atual": leitura_atual,
        "consumo": consumo,
        "valor": calcular_valor_agua(consumo, tabela=tabela),
        "tabela": tabela or faixa_aplicada.tabela,
        "faixa": faixa_aplicada,
    }


def calcular_consumo_gas(leitura_anterior, leitura_atual):
    return _calcular_consumo(leitura_anterior, leitura_atual, "gás")


def calcular_valor_gas(
    consumo_gas,
    valor_m3_gas=None,
    *,
    mes=None,
    ano=None,
    condominio=None,
):
    if condominio is None and valor_m3_gas is None:
        from condominios.models import Condominio
        condominio = Condominio.objects.order_by("id").first()
    consumo = _decimal_finito(consumo_gas, "O consumo de gás")
    if consumo < 0:
        raise ValueError("O consumo de gás não pode ser negativo.")
    if valor_m3_gas is None:
        if mes is None or ano is None:
            hoje = date.today()
            mes, ano = hoje.month, hoje.year
        valor_m3_gas = obter_tarifa_gas_vigente(
            condominio, mes, ano
        ).valor_por_m3
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
    mes=None,
    ano=None,
    condominio=None,
):
    if condominio is None and valor_m3_gas is None:
        from condominios.models import Condominio
        condominio = Condominio.objects.order_by("id").first()
    consumo = calcular_consumo_gas(leitura_anterior, leitura_atual)
    if valor_m3_gas is None:
        if mes is None or ano is None:
            hoje = date.today()
            mes, ano = hoje.month, hoje.year
        tarifa = obter_tarifa_gas_vigente(condominio, mes, ano)
    else:
        tarifa = None
    valor_unitario = tarifa.valor_por_m3 if tarifa else valor_m3_gas
    return {
        "leitura_anterior": leitura_anterior,
        "leitura_atual": leitura_atual,
        "consumo": consumo,
        "valor": calcular_valor_gas(consumo, valor_unitario),
        "tarifa": tarifa,
        "valor_por_m3": valor_unitario,
    }
