import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.db.models import Prefetch
from django.utils import timezone
from condominios.permissions import Permissao, exigir_permissao

from apartamentos.models import Apartamento
from calculos.services import calcular_agua, calcular_gas
from configuracoes.services import (
    ConsumoSemFaixaError,
    TarifaNaoConfiguradaError,
    obter_configuracao,
)
from leituras.models import Leitura

from .models import (
    ANO_MAXIMO,
    LIMITE_VALOR_FINANCEIRO,
    Fatura,
    HistoricoFinanceiroFatura,
)


logger = logging.getLogger(__name__)
_NAO_INFORMADO = object()
_CAMPOS_HISTORICO_FINANCEIRO = (
    "status",
    "valor_agua",
    "valor_gas",
    "valor_aluguel",
    "valor_condominio",
    "valor_iptu",
    "valor_outros",
    "desconto",
    "valor_bonificacao",
    "origem_bonificacao_emissao",
    "tipo_bonificacao_emissao",
    "percentual_bonificacao_emissao",
    "valor_bonificacao_fixa_emissao",
    "valor_original",
    "valor_total",
    "valor_multa_aplicada",
    "valor_juros_aplicados",
    "valor_bonificacao_aplicada",
    "valor_final",
    "valor_pago",
    "data_vencimento",
    "data_pagamento",
    "dias_em_atraso",
    "dias_antecipados",
    "forma_pagamento",
)


def _normalizar_usuario_historico(usuario):
    if usuario is not None and not getattr(
        usuario,
        "is_authenticated",
        False,
    ):
        return None
    return usuario


def _serializar_valor_historico(valor):
    if isinstance(valor, Decimal):
        return f"{valor:.2f}"
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    return valor


def _snapshot_financeiro(fatura):
    return {
        campo: _serializar_valor_historico(getattr(fatura, campo))
        for campo in _CAMPOS_HISTORICO_FINANCEIRO
    }


def _registrar_historico_financeiro(
    fatura,
    acao,
    *,
    usuario=None,
    valores_anteriores=None,
    motivo="",
):
    return HistoricoFinanceiroFatura.objects.create(
        fatura=fatura,
        status_anterior=(
            valores_anteriores or {}
        ).get("status", fatura.status),
        novo_status=fatura.status,
        acao=acao,
        motivo=motivo,
        usuario=_normalizar_usuario_historico(usuario),
        valores_anteriores=valores_anteriores or {},
        valores_novos=_snapshot_financeiro(fatura),
    )


def _configurar_bonificacao_fatura(
    fatura,
    *,
    modo=None,
    tipo=None,
    valor=None,
    valor_legado=Decimal("0.00"),
    dia_limite_legado=None,
):
    configuracao = obter_configuracao(fatura.apartamento.condominio)
    fatura.dias_antecedencia_bonificacao_emissao = (
        configuracao.dias_antecedencia_bonificacao
    )

    if modo is None:
        modo = (
            Fatura.OrigemBonificacao.ESPECIFICA
            if valor_legado > 0
            else Fatura.OrigemBonificacao.CONDOMINIO
        )
        if valor_legado > 0:
            tipo = Fatura.TipoBonificacao.VALOR_FIXO
            valor = valor_legado

    if modo not in Fatura.OrigemBonificacao.values:
        raise ValueError("Selecione uma opção de bonificação válida.")

    fatura.valor_bonificacao = Decimal("0.00")
    fatura.dia_limite_bonificacao = None
    fatura.percentual_bonificacao_emissao = Decimal("0.000")
    fatura.valor_bonificacao_fixa_emissao = Decimal("0.00")
    fatura.data_limite_bonificacao = None

    if modo == Fatura.OrigemBonificacao.NENHUMA:
        fatura.origem_bonificacao_emissao = modo
        fatura.tipo_bonificacao_emissao = (
            Fatura.TipoBonificacao.NENHUMA
        )
        return

    if modo == Fatura.OrigemBonificacao.CONDOMINIO:
        percentual = configuracao.percentual_bonificacao_padrao
        if percentual <= 0:
            fatura.origem_bonificacao_emissao = (
                Fatura.OrigemBonificacao.NENHUMA
            )
            fatura.tipo_bonificacao_emissao = (
                Fatura.TipoBonificacao.NENHUMA
            )
            return
        fatura.origem_bonificacao_emissao = modo
        fatura.tipo_bonificacao_emissao = (
            Fatura.TipoBonificacao.PERCENTUAL
        )
        fatura.percentual_bonificacao_emissao = percentual
    else:
        if tipo not in (
            Fatura.TipoBonificacao.PERCENTUAL,
            Fatura.TipoBonificacao.VALOR_FIXO,
        ):
            raise ValueError("Informe o tipo da bonificação específica.")
        if tipo == Fatura.TipoBonificacao.PERCENTUAL:
            valor = _normalizar_decimal(
                valor,
                "A bonificação específica",
            ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        else:
            valor = _normalizar_valor_financeiro(
                valor,
                "A bonificação específica",
            )
        if valor <= 0:
            raise ValueError(
                "A bonificação específica deve ser maior que zero."
            )
        fatura.origem_bonificacao_emissao = modo
        fatura.tipo_bonificacao_emissao = tipo
        if tipo == Fatura.TipoBonificacao.PERCENTUAL:
            if valor > Decimal("100"):
                raise ValueError(
                    "O percentual da bonificação deve estar entre 0 e 100."
                )
            fatura.percentual_bonificacao_emissao = valor
        else:
            fatura.valor_bonificacao_fixa_emissao = valor
            # Mantém a representação antiga preenchida para documentos
            # emitidos por integrações que ainda consultem esse campo.
            fatura.valor_bonificacao = valor
            if dia_limite_legado:
                fatura.dia_limite_bonificacao = dia_limite_legado

    if fatura.data_vencimento:
        if fatura.dia_limite_bonificacao:
            fatura.data_limite_bonificacao = (
                fatura.calcular_data_limite_bonificacao_legada()
            )
        else:
            fatura.data_limite_bonificacao = (
                fatura.data_vencimento
                - timedelta(
                    days=fatura.dias_antecedencia_bonificacao_emissao
                )
            )


@dataclass(frozen=True)
class ResultadoFechamento:
    apartamentos_analisados: int
    faturas_geradas: int
    faturas_existentes: int
    apartamentos_sem_leitura: tuple
    falhas_tarifarias: tuple = ()

    @property
    def total_sem_leitura(self):
        return len(self.apartamentos_sem_leitura)

    @property
    def total_falhas_tarifarias(self):
        return len(self.falhas_tarifarias)


@dataclass(frozen=True)
class ResultadoPagamento:
    valor_original: Decimal
    desconto: Decimal
    bonificacao: Decimal
    multa: Decimal
    juros: Decimal
    valor_final: Decimal
    dias_em_atraso: int
    dias_antecipados: int


class RegraNegocioFaturaError(ValidationError):
    """Indica uma operação incompatível com o estado atual da fatura."""


TRANSICOES_STATUS_PERMITIDAS = {
    Fatura.Status.PENDENTE: {
        Fatura.Status.PAGA,
        Fatura.Status.CANCELADA,
    },
    Fatura.Status.PAGA: {Fatura.Status.PENDENTE},
    Fatura.Status.CANCELADA: {Fatura.Status.PENDENTE},
}


def validar_transicao_status(status_atual, novo_status):
    if novo_status not in Fatura.Status.values:
        raise RegraNegocioFaturaError("Status de fatura inválido.")
    if status_atual == novo_status:
        return False
    if novo_status not in TRANSICOES_STATUS_PERMITIDAS.get(
        status_atual,
        set(),
    ):
        atual = dict(Fatura.Status.choices).get(status_atual, status_atual)
        novo = dict(Fatura.Status.choices)[novo_status]
        raise RegraNegocioFaturaError(
            f"A transição de {atual.lower()} para {novo.lower()} "
            "não é permitida."
        )
    return True


def validar_edicao_financeira(fatura):
    if fatura.status != Fatura.Status.PENDENTE:
        status = fatura.get_status_display().lower()
        raise RegraNegocioFaturaError(
            f"Não é possível editar valores de uma fatura {status}."
        )


def _consultar_apartamento_para_atualizacao(apartamento_id):
    try:
        return (
            Apartamento.objects
            .select_for_update()
            .get(pk=apartamento_id)
        )
    except Apartamento.DoesNotExist as exc:
        raise ValueError("Apartamento não encontrado.") from exc


def _bloquear_historico_leituras(apartamento_id):
    # A avaliação imediata mantém estáveis as medições usadas no cálculo até
    # a conclusão da transação.
    list(
        Leitura.objects
        .select_for_update()
        .filter(apartamento_id=apartamento_id)
        .values_list("pk", flat=True)
    )


def _consultar_contexto_leitura_para_atualizacao(leitura_id):
    apartamento_id = (
        Leitura.objects
        .filter(pk=leitura_id)
        .values_list("apartamento_id", flat=True)
        .first()
    )
    if apartamento_id is None:
        raise ValueError("Leitura não encontrada.")

    apartamento = _consultar_apartamento_para_atualizacao(apartamento_id)
    _bloquear_historico_leituras(apartamento.id)

    try:
        leitura = (
            Leitura.objects
            .select_related("apartamento")
            .get(pk=leitura_id, apartamento_id=apartamento.id)
        )
    except Leitura.DoesNotExist as exc:
        raise ValueError("Leitura não encontrada.") from exc

    leitura.apartamento = apartamento
    return leitura


def _normalizar_consumo(consumo, recurso, *, permitir_ausente=False):
    if consumo is None and permitir_ausente:
        return None
    if (
        isinstance(consumo, bool)
        or not isinstance(consumo, int)
        or consumo < 0
    ):
        raise ValueError(
            f"O consumo de {recurso} deve ser um número inteiro não negativo."
        )
    return consumo


def _normalizar_consumo_gas(consumo, *, permitir_ausente=False):
    if consumo is None and permitir_ausente:
        return None
    consumo = _normalizar_decimal(consumo, "O consumo de gás")
    try:
        return consumo.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError("O consumo de gás excede o limite permitido.") from exc


def _normalizar_decimal(
    valor,
    descricao,
    *,
    permitir_ausente=False,
):
    if valor is None and permitir_ausente:
        return None
    if isinstance(valor, bool):
        raise ValueError(f"{descricao} deve ser um número válido.")
    try:
        valor = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{descricao} deve ser um número válido.") from exc

    if not valor.is_finite() or valor < 0:
        raise ValueError(
            f"{descricao} não pode ser negativo ou inválido."
        )
    return valor


def _normalizar_valor_financeiro(valor, descricao, *, padrao=None):
    if valor in (None, ""):
        if padrao is None:
            raise ValueError(f"{descricao} é obrigatório.")
        valor = padrao
    valor = _normalizar_decimal(valor, descricao)
    try:
        return valor.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
    except InvalidOperation as exc:
        raise ValueError(
            f"{descricao} excede o limite permitido."
        ) from exc


def _normalizar_valor_outros(valor):
    if valor in (None, ""):
        valor = Decimal("0.00")
    if isinstance(valor, bool):
        raise ValueError("O valor de Outros deve ser um número válido.")
    try:
        valor = Decimal(str(valor))
        if not valor.is_finite():
            raise InvalidOperation
        valor = valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("O valor de Outros deve ser um número válido.") from exc
    if abs(valor) > LIMITE_VALOR_FINANCEIRO:
        raise ValueError("O valor de Outros excede o limite permitido.")
    return valor


def _calcular_dados_da_leitura(leitura_atual):
    if (
        leitura_atual.leitura_agua is None
        or leitura_atual.leitura_gas is None
    ):
        raise ValueError(
            "A leitura precisa possuir valores de água e gás "
            "para gerar uma fatura."
        )

    leitura_anterior_agua = buscar_leitura_anterior(
        leitura_atual,
        "leitura_agua",
    )
    leitura_anterior_gas = buscar_leitura_anterior(
        leitura_atual,
        "leitura_gas",
    )
    apartamento = leitura_atual.apartamento

    leitura_agua_anterior = (
        leitura_anterior_agua.leitura_agua
        if leitura_anterior_agua is not None
        else apartamento.leitura_base_agua
    )
    leitura_gas_anterior = (
        leitura_anterior_gas.leitura_gas
        if leitura_anterior_gas is not None
        else apartamento.leitura_base_gas
    )

    if leitura_agua_anterior is None or leitura_gas_anterior is None:
        raise ValueError(
            "O apartamento não possui leituras-base configuradas. "
            "Informe as medições anteriores de água e gás antes de gerar "
            "a primeira fatura."
        )

    resultado_agua = calcular_agua(
        leitura_agua_anterior,
        leitura_atual.leitura_agua,
        leitura_atual.mes,
        leitura_atual.ano,
        condominio=apartamento.condominio,
    )
    resultado_gas = calcular_gas(
        leitura_gas_anterior,
        leitura_atual.leitura_gas,
        mes=leitura_atual.mes,
        ano=leitura_atual.ano,
        condominio=apartamento.condominio,
    )
    return {
        "consumo_agua": resultado_agua["consumo"],
        "consumo_gas": resultado_gas["consumo"],
        "valor_agua": resultado_agua["valor"],
        "valor_gas": resultado_gas["valor"],
        "tabela_agua": resultado_agua["tabela"],
        "faixa_agua": resultado_agua["faixa"],
        "tarifa_gas": resultado_gas["tarifa"],
        "valor_m3_gas": resultado_gas["valor_por_m3"],
        "leitura_agua_anterior": leitura_agua_anterior,
        "leitura_agua_atual": leitura_atual.leitura_agua,
        "leitura_gas_anterior": leitura_gas_anterior,
        "leitura_gas_atual": leitura_atual.leitura_gas,
    }


def _validar_dados_da_leitura_informados(dados_informados):
    divergencias = [
        descricao
        for descricao, informado, calculado in dados_informados
        if informado is not None and informado != calculado
    ]
    if divergencias:
        raise ValueError(
            "Os dados informados não correspondem à leitura vinculada: "
            f"{', '.join(divergencias)}."
        )


@transaction.atomic
def cadastrar_fatura(
    apartamento_id,
    mes,
    ano,
    consumo_agua=None,
    consumo_gas=None,
    valor_agua=None,
    valor_gas=None,
    leitura_id=None,
    status="pendente",
    leitura_agua_anterior=None,
    leitura_agua_atual=None,
    leitura_gas_anterior=None,
    leitura_gas_atual=None,
    valor_aluguel=None,
    desconto=None,
    valor_condominio=None,
    valor_iptu=None,
    valor_bonificacao=None,
    dia_limite_bonificacao=_NAO_INFORMADO,
    modo_bonificacao=None,
    tipo_bonificacao=None,
    bonificacao_especifica=None,
    valor_outros=None,
    observacao_outros=None,
    usuario=None,
):
    apartamento = _consultar_apartamento_para_atualizacao(apartamento_id)
    valor_aluguel = _normalizar_valor_financeiro(
        valor_aluguel,
        "O valor do aluguel",
        padrao=apartamento.valor_aluguel,
    )
    desconto = _normalizar_valor_financeiro(
        desconto,
        "O desconto",
        padrao=Decimal("0.00"),
    )
    valor_condominio = _normalizar_valor_financeiro(
        valor_condominio,
        "O valor do condomínio",
        padrao=apartamento.valor_condominio,
    )
    valor_iptu = _normalizar_valor_financeiro(
        valor_iptu,
        "O valor do IPTU",
        padrao=apartamento.valor_iptu,
    )
    valor_bonificacao = _normalizar_valor_financeiro(
        valor_bonificacao,
        "O valor da bonificação",
        padrao=Decimal("0.00"),
    )
    if dia_limite_bonificacao is _NAO_INFORMADO:
        dia_limite_bonificacao = (
            apartamento.dia_limite_bonificacao
            if modo_bonificacao is None and valor_bonificacao > 0
            else None
        )
    elif dia_limite_bonificacao == "":
        dia_limite_bonificacao = None
    if (
        dia_limite_bonificacao is not None
        and (
            isinstance(dia_limite_bonificacao, bool)
            or not isinstance(dia_limite_bonificacao, int)
            or not 1 <= dia_limite_bonificacao <= 31
        )
    ):
        raise ValueError("O dia limite da bonificação deve estar entre 1 e 31.")
    valor_outros = _normalizar_valor_outros(valor_outros)
    observacao_outros = (observacao_outros or "").strip()
    if valor_outros != 0 and not observacao_outros:
        raise ValueError(
            "Informe a observação quando Outros for diferente de zero."
        )
    if valor_bonificacao > 0 and dia_limite_bonificacao is None:
        raise ValueError("Informe o dia limite quando houver bonificação.")

    if (
        isinstance(mes, bool)
        or not isinstance(mes, int)
        or mes < 1
        or mes > 12
    ):
        raise ValueError("O mês deve estar entre 1 e 12.")
    if (
        isinstance(ano, bool)
        or not isinstance(ano, int)
        or ano < 2000
        or ano > ANO_MAXIMO
    ):
        raise ValueError("Informe um ano válido.")
    if status not in Fatura.Status.values:
        raise ValueError("Status de fatura inválido.")

    fatura_existente = Fatura.objects.filter(
        apartamento=apartamento,
        mes=mes,
        ano=ano,
    ).exists()

    if fatura_existente:
        raise ValueError("Já existe uma fatura para este apartamento neste mês e ano.")

    leitura = None
    if leitura_id is not None:
        _bloquear_historico_leituras(apartamento.id)
        try:
            leitura = (
                Leitura.objects
                .select_related("apartamento")
                .get(pk=leitura_id, apartamento_id=apartamento.id)
            )
        except Leitura.DoesNotExist as exc:
            if not Leitura.objects.filter(pk=leitura_id).exists():
                raise ValueError("Leitura não encontrada.") from exc
            raise ValueError(
                "A leitura deve pertencer ao mesmo apartamento, mês e ano "
                "da fatura."
            ) from exc

    if leitura is not None and (
        leitura.apartamento_id != apartamento.id
        or leitura.mes != mes
        or leitura.ano != ano
    ):
        raise ValueError(
            "A leitura deve pertencer ao mesmo apartamento, mês e ano da fatura."
        )

    permite_dados_ausentes = leitura is not None
    consumo_agua = _normalizar_consumo(
        consumo_agua,
        "água",
        permitir_ausente=permite_dados_ausentes,
    )
    consumo_gas = _normalizar_consumo_gas(
        consumo_gas,
        permitir_ausente=permite_dados_ausentes,
    )
    valor_agua = _normalizar_decimal(
        0 if leitura is None and valor_agua is None else valor_agua,
        "O valor da água",
        permitir_ausente=permite_dados_ausentes,
    )
    valor_gas = _normalizar_decimal(
        0 if leitura is None and valor_gas is None else valor_gas,
        "O valor do gás",
        permitir_ausente=permite_dados_ausentes,
    )

    if leitura is not None:
        dados_calculados = _calcular_dados_da_leitura(leitura)
        retratos_informados = {
            "leitura_agua_anterior": _normalizar_decimal(
                leitura_agua_anterior,
                "A leitura anterior de água",
                permitir_ausente=True,
            ),
            "leitura_agua_atual": _normalizar_decimal(
                leitura_agua_atual,
                "A leitura atual de água",
                permitir_ausente=True,
            ),
            "leitura_gas_anterior": _normalizar_decimal(
                leitura_gas_anterior,
                "A leitura anterior de gás",
                permitir_ausente=True,
            ),
            "leitura_gas_atual": _normalizar_decimal(
                leitura_gas_atual,
                "A leitura atual de gás",
                permitir_ausente=True,
            ),
        }
        _validar_dados_da_leitura_informados(
            [
                (
                    "consumo de água",
                    consumo_agua,
                    dados_calculados["consumo_agua"],
                ),
                (
                    "consumo de gás",
                    consumo_gas,
                    dados_calculados["consumo_gas"],
                ),
                (
                    "valor da água",
                    valor_agua,
                    dados_calculados["valor_agua"],
                ),
                (
                    "valor do gás",
                    valor_gas,
                    dados_calculados["valor_gas"],
                ),
                (
                    "leitura anterior de água",
                    retratos_informados["leitura_agua_anterior"],
                    dados_calculados["leitura_agua_anterior"],
                ),
                (
                    "leitura atual de água",
                    retratos_informados["leitura_agua_atual"],
                    dados_calculados["leitura_agua_atual"],
                ),
                (
                    "leitura anterior de gás",
                    retratos_informados["leitura_gas_anterior"],
                    dados_calculados["leitura_gas_anterior"],
                ),
                (
                    "leitura atual de gás",
                    retratos_informados["leitura_gas_atual"],
                    dados_calculados["leitura_gas_atual"],
                ),
            ]
        )
        consumo_agua = dados_calculados["consumo_agua"]
        consumo_gas = dados_calculados["consumo_gas"]
        valor_agua = dados_calculados["valor_agua"]
        valor_gas = dados_calculados["valor_gas"]
        leitura_agua_anterior = dados_calculados["leitura_agua_anterior"]
        leitura_agua_atual = dados_calculados["leitura_agua_atual"]
        leitura_gas_anterior = dados_calculados["leitura_gas_anterior"]
        leitura_gas_atual = dados_calculados["leitura_gas_atual"]
        tabela_agua = dados_calculados["tabela_agua"]
        faixa_agua = dados_calculados["faixa_agua"]
        tarifa_gas = dados_calculados["tarifa_gas"]
        valor_m3_gas = dados_calculados["valor_m3_gas"]
    else:
        tabela_agua = faixa_agua = tarifa_gas = None
        valor_m3_gas = Decimal("0.00")
        leitura_agua_anterior = _normalizar_decimal(
            leitura_agua_anterior,
            "A leitura anterior de água",
            permitir_ausente=True,
        )
        leitura_agua_atual = _normalizar_decimal(
            leitura_agua_atual,
            "A leitura atual de água",
            permitir_ausente=True,
        )
        leitura_gas_anterior = _normalizar_decimal(
            leitura_gas_anterior,
            "A leitura anterior de gás",
            permitir_ausente=True,
        )
        leitura_gas_atual = _normalizar_decimal(
            leitura_gas_atual,
            "A leitura atual de gás",
            permitir_ausente=True,
        )

    fatura = Fatura(
        apartamento=apartamento,
        leitura=leitura,
        tabela_agua_utilizada=tabela_agua,
        faixa_agua_utilizada=faixa_agua,
        tarifa_gas_utilizada=tarifa_gas,
        mes=mes,
        ano=ano,
        consumo_agua=consumo_agua,
        consumo_gas=consumo_gas,
        valor_agua=valor_agua,
        valor_gas=valor_gas,
        valor_aluguel=valor_aluguel,
        desconto=desconto,
        valor_condominio=valor_condominio,
        valor_iptu=valor_iptu,
        valor_bonificacao=valor_bonificacao,
        dia_limite_bonificacao=dia_limite_bonificacao,
        valor_outros=valor_outros,
        observacao_outros=observacao_outros,
        valor_total=Decimal("0.00"),
        valor_m3_gas_emissao=valor_m3_gas,
        status=status,
        apartamento_numero_emissao=apartamento.numero,
        apartamento_bloco_emissao=apartamento.bloco,
        leitura_agua_anterior=leitura_agua_anterior,
        leitura_agua_atual=leitura_agua_atual,
        leitura_gas_anterior=leitura_gas_anterior,
        leitura_gas_atual=leitura_gas_atual,
    )
    try:
        fatura.recalcular_valor_total()
        _configurar_bonificacao_fatura(
            fatura,
            modo=modo_bonificacao,
            tipo=tipo_bonificacao,
            valor=bonificacao_especifica,
            valor_legado=valor_bonificacao,
            dia_limite_legado=dia_limite_bonificacao,
        )
        if (
            fatura.tipo_bonificacao_emissao
            == Fatura.TipoBonificacao.VALOR_FIXO
            and fatura.valor_bonificacao_fixa_emissao
            > fatura.valor_total
        ):
            raise ValueError(
                "A bonificação não pode superar o valor elegível da cobrança."
            )
        fatura._preencher_snapshots_emissao()
    except ValidationError as exc:
        raise ValueError(" ".join(exc.messages)) from exc
    try:
        fatura.full_clean(
            validate_unique=False,
            validate_constraints=False,
        )
        with transaction.atomic():
            fatura.save(force_insert=True)
            _registrar_historico_financeiro(
                fatura,
                HistoricoFinanceiroFatura.Acao.FATURA_CRIADA,
                usuario=usuario,
            )
    except ValidationError as exc:
        raise ValueError(" ".join(exc.messages)) from exc
    except IntegrityError as exc:
        if Fatura.objects.filter(
            apartamento=apartamento,
            mes=mes,
            ano=ano,
        ).exists():
            raise ValueError(
                "Já existe uma fatura para este apartamento neste mês e ano."
            ) from exc
        raise ValueError("Os dados da fatura violam uma regra de integridade.") from exc
    return fatura


def consultar_fatura(fatura_id):
    try:
        return (
            Fatura.objects
            .select_related(
                "apartamento",
                "leitura",
                "tabela_agua_utilizada",
                "faixa_agua_utilizada",
                "tarifa_gas_utilizada",
            )
            .get(id=fatura_id)
        )
    except Fatura.DoesNotExist as erro:
        raise ValueError("Fatura não encontrada.") from erro


def consultar_fatura_no_condominio(condominio, fatura_id):
    try:
        return (
            Fatura.objects
            .select_related(
                "apartamento", "leitura", "tabela_agua_utilizada",
                "faixa_agua_utilizada", "tarifa_gas_utilizada",
            )
            .get(
                id=fatura_id,
                apartamento__condominio=condominio,
            )
        )
    except Fatura.DoesNotExist as exc:
        raise ValueError("Fatura não encontrada.") from exc


def listar_faturas(
    *,
    apartamento_id=None,
    bloco=None,
    mes=None,
    ano=None,
    status=None,
):
    queryset = Fatura.objects.select_related(
        "apartamento",
        "leitura",
    )

    if apartamento_id is not None:
        queryset = queryset.filter(
            apartamento_id=apartamento_id,
        )

    if bloco:
        queryset = queryset.filter(
            apartamento_bloco_emissao__iexact=bloco.strip(),
        )

    if mes is not None:
        queryset = queryset.filter(mes=mes)

    if ano is not None:
        queryset = queryset.filter(ano=ano)

    if status:
        queryset = queryset.filter(status=status)

    return queryset.order_by("-ano", "-mes", "-id")


def listar_faturas_por_condominio(condominio, **filtros):
    return listar_faturas(**filtros).filter(
        apartamento__condominio=condominio
    )


def _consultar_fatura_para_atualizacao(fatura_id):
    try:
        return (
            Fatura.objects
            .select_for_update(of=("self",))
            .select_related("apartamento", "leitura")
            .get(pk=fatura_id)
        )
    except Fatura.DoesNotExist as exc:
        raise ValueError("Fatura não encontrada.") from exc


def _normalizar_motivo(motivo, acao):
    motivo = (motivo or "").strip()
    rotulo = (
        "estorno"
        if acao == HistoricoFinanceiroFatura.Acao.PAGAMENTO_ESTORNADO
        else "reabertura"
    )
    if not motivo:
        raise RegraNegocioFaturaError(
            f"Informe o motivo d{'o' if rotulo == 'estorno' else 'a'} "
            f"{rotulo}."
        )
    if len(motivo) < 5:
        raise RegraNegocioFaturaError(
            "O motivo deve ter pelo menos 5 caracteres."
        )
    if len(motivo) > 500:
        raise RegraNegocioFaturaError(
            "O motivo deve ter no máximo 500 caracteres."
        )
    return motivo


def calcular_pagamento_fatura(fatura, data_pagamento):
    if not all(
        hasattr(data_pagamento, atributo)
        for atributo in ("year", "month", "day")
    ):
        raise RegraNegocioFaturaError("Informe uma data de pagamento válida.")

    diferenca_vencimento = data_pagamento - fatura.data_vencimento
    dias_em_atraso = max(diferenca_vencimento.days, 0)
    dias_antecipados = max(-diferenca_vencimento.days, 0)
    dias_com_encargos = max(
        dias_em_atraso - fatura.dias_tolerancia_emissao,
        0,
    )
    fator_percentual = Decimal("100")
    valor_original = fatura.valor_original
    base_calculo = valor_original - fatura.desconto
    multa = (
        (
            base_calculo
            * fatura.percentual_multa_emissao
            / fator_percentual
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if dias_com_encargos
        else Decimal("0.00")
    )
    if dias_com_encargos:
        multiplicador_juros = Decimal(dias_com_encargos)
        if fatura.tipo_juros_emissao == Fatura.TipoJuros.MENSAL:
            multiplicador_juros /= Decimal("30")
        juros = (
            base_calculo
            * fatura.percentual_juros_emissao
            / fator_percentual
            * multiplicador_juros
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        juros = Decimal("0.00")

    aplica_bonificacao = bool(
        fatura.possui_bonificacao
        and fatura.data_limite_bonificacao
        and data_pagamento <= fatura.data_limite_bonificacao
    )
    if (
        aplica_bonificacao
        and fatura.tipo_bonificacao_emissao
        == Fatura.TipoBonificacao.PERCENTUAL
    ):
        bonificacao = (
            base_calculo
            * fatura.percentual_bonificacao_emissao
            / fator_percentual
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    elif (
        aplica_bonificacao
        and fatura.tipo_bonificacao_emissao
        == Fatura.TipoBonificacao.VALOR_FIXO
    ):
        bonificacao = fatura.valor_bonificacao_fixa_emissao
    else:
        bonificacao = Decimal("0.00")
    bonificacao = min(bonificacao, base_calculo)
    valor_final = (
        base_calculo + multa + juros - bonificacao
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return ResultadoPagamento(
        valor_original=valor_original,
        desconto=fatura.desconto,
        bonificacao=bonificacao,
        multa=multa,
        juros=juros,
        valor_final=valor_final,
        dias_em_atraso=dias_em_atraso,
        dias_antecipados=dias_antecipados,
    )


@transaction.atomic
def _executar_acao_status(
    fatura_id,
    *,
    status_origem,
    novo_status,
    acao,
    usuario=None,
    motivo="",
    exige_motivo=False,
):
    fatura = _consultar_fatura_para_atualizacao(fatura_id)
    if fatura.status == novo_status:
        return fatura, False
    validar_transicao_status(fatura.status, novo_status)
    if fatura.status != status_origem:
        raise RegraNegocioFaturaError(
            "A ação solicitada não corresponde ao status atual da fatura."
        )
    motivo = (
        _normalizar_motivo(motivo, acao)
        if exige_motivo
        else ""
    )
    valores_anteriores = _snapshot_financeiro(fatura)
    status_anterior = fatura.status
    agora = timezone.now()
    campos_atualizados = ["status"]
    fatura.status = novo_status

    if novo_status == Fatura.Status.PAGA:
        fatura.data_pagamento = agora.date()
        fatura.data_cancelamento = None
        campos_atualizados.extend(
            ["data_pagamento", "data_cancelamento"]
        )
    elif novo_status == Fatura.Status.CANCELADA:
        fatura.data_cancelamento = agora
        fatura.data_pagamento = None
        campos_atualizados.extend(
            ["data_cancelamento", "data_pagamento"]
        )
    elif status_anterior == Fatura.Status.PAGA:
        fatura.data_pagamento = None
        fatura.valor_pago = None
        fatura.bonificacao_aplicada = False
        fatura.dias_em_atraso = 0
        fatura.dias_antecipados = 0
        fatura.valor_multa_aplicada = Decimal("0.00")
        fatura.valor_juros_aplicados = Decimal("0.00")
        fatura.valor_bonificacao_aplicada = Decimal("0.00")
        fatura.valor_final = None
        fatura.forma_pagamento = ""
        fatura.observacoes_pagamento = ""
        campos_atualizados.extend(
            [
                "data_pagamento",
                "valor_pago",
                "bonificacao_aplicada",
                "dias_em_atraso",
                "dias_antecipados",
                "valor_multa_aplicada",
                "valor_juros_aplicados",
                "valor_bonificacao_aplicada",
                "valor_final",
                "forma_pagamento",
                "observacoes_pagamento",
            ]
        )
    elif status_anterior == Fatura.Status.CANCELADA:
        fatura.data_cancelamento = None
        campos_atualizados.append("data_cancelamento")

    fatura.save(update_fields=campos_atualizados)
    _registrar_historico_financeiro(
        fatura,
        acao,
        usuario=usuario,
        valores_anteriores=valores_anteriores,
        motivo=motivo,
    )
    return fatura, True


def _validar_permissao_financeira(objeto, usuario, permissao):
    if usuario is not None:
        apartamento = getattr(objeto, "apartamento", objeto)
        exigir_permissao(
            usuario, apartamento.condominio, permissao
        )


@transaction.atomic
def marcar_fatura_como_paga(
    fatura_id,
    usuario=None,
    data_pagamento=None,
    forma_pagamento=Fatura.FormaPagamento.NAO_INFORMADA,
    observacoes_pagamento="",
):
    if data_pagamento is None:
        data_pagamento = timezone.localdate()
    if forma_pagamento not in Fatura.FormaPagamento.values:
        raise RegraNegocioFaturaError("Informe uma forma de pagamento válida.")
    observacoes_pagamento = (observacoes_pagamento or "").strip()
    if len(observacoes_pagamento) > 500:
        raise RegraNegocioFaturaError(
            "As observações do pagamento devem ter no máximo 500 caracteres."
        )
    fatura = _consultar_fatura_para_atualizacao(fatura_id)
    _validar_permissao_financeira(
        fatura, usuario, Permissao.MARCAR_FATURA_PAGA
    )
    resultado = calcular_pagamento_fatura(fatura, data_pagamento)
    fatura, alterada = _executar_acao_status(
        fatura_id,
        status_origem=Fatura.Status.PENDENTE,
        novo_status=Fatura.Status.PAGA,
        acao=HistoricoFinanceiroFatura.Acao.PAGAMENTO_CONFIRMADO,
        usuario=usuario,
    )
    if alterada:
        fatura.data_pagamento = data_pagamento
        fatura.dias_em_atraso = resultado.dias_em_atraso
        fatura.dias_antecipados = resultado.dias_antecipados
        fatura.valor_original = resultado.valor_original
        fatura.valor_multa_aplicada = resultado.multa
        fatura.valor_juros_aplicados = resultado.juros
        fatura.valor_bonificacao_aplicada = resultado.bonificacao
        fatura.bonificacao_aplicada = resultado.bonificacao > 0
        fatura.valor_final = resultado.valor_final
        fatura.valor_pago = fatura.valor_final
        fatura.forma_pagamento = forma_pagamento
        fatura.observacoes_pagamento = observacoes_pagamento
        fatura.save(
            update_fields=[
                "data_pagamento",
                "dias_em_atraso",
                "dias_antecipados",
                "valor_multa_aplicada",
                "valor_juros_aplicados",
                "bonificacao_aplicada",
                "valor_bonificacao_aplicada",
                "valor_original",
                "valor_final",
                "valor_pago",
                "forma_pagamento",
                "observacoes_pagamento",
            ]
        )
        evento = fatura.historico_financeiro.order_by("-id").first()
        evento.valores_novos = _snapshot_financeiro(fatura)
        evento.save(update_fields=["valores_novos"])
    return fatura, alterada


def cancelar_fatura(fatura_id, usuario=None):
    fatura = _consultar_fatura_para_atualizacao(fatura_id)
    _validar_permissao_financeira(
        fatura, usuario, Permissao.CANCELAR_FATURA
    )
    return _executar_acao_status(
        fatura_id,
        status_origem=Fatura.Status.PENDENTE,
        novo_status=Fatura.Status.CANCELADA,
        acao=HistoricoFinanceiroFatura.Acao.FATURA_CANCELADA,
        usuario=usuario,
    )


def estornar_pagamento(fatura_id, motivo, usuario=None):
    fatura = _consultar_fatura_para_atualizacao(fatura_id)
    _validar_permissao_financeira(
        fatura, usuario, Permissao.ESTORNAR_FATURA
    )
    return _executar_acao_status(
        fatura_id,
        status_origem=Fatura.Status.PAGA,
        novo_status=Fatura.Status.PENDENTE,
        acao=HistoricoFinanceiroFatura.Acao.PAGAMENTO_ESTORNADO,
        motivo=motivo,
        usuario=usuario,
        exige_motivo=True,
    )


def reabrir_fatura(fatura_id, motivo, usuario=None):
    fatura = _consultar_fatura_para_atualizacao(fatura_id)
    _validar_permissao_financeira(
        fatura, usuario, Permissao.REABRIR_FATURA
    )
    return _executar_acao_status(
        fatura_id,
        status_origem=Fatura.Status.CANCELADA,
        novo_status=Fatura.Status.PENDENTE,
        acao=HistoricoFinanceiroFatura.Acao.FATURA_REABERTA,
        motivo=motivo,
        usuario=usuario,
        exige_motivo=True,
    )


@transaction.atomic
def editar_fatura(
    fatura_id,
    *,
    valor_aluguel=None,
    desconto=None,
    valor_condominio=None,
    valor_iptu=None,
    valor_bonificacao=None,
    dia_limite_bonificacao=_NAO_INFORMADO,
    modo_bonificacao=None,
    tipo_bonificacao=None,
    bonificacao_especifica=None,
    valor_outros=None,
    observacao_outros=None,
    usuario=None,
):
    fatura = _consultar_fatura_para_atualizacao(fatura_id)
    _validar_permissao_financeira(
        fatura, usuario, Permissao.EDITAR_VALORES_FINANCEIROS
    )
    valores_anteriores = _snapshot_financeiro(fatura)
    edita_bonificacao = (
        modo_bonificacao is not None
        or valor_bonificacao is not None
    )

    campos_atualizados = []
    if edita_bonificacao or any(
        valor is not None
        for valor in (
            valor_aluguel,
            desconto,
            valor_condominio,
            valor_iptu,
            valor_outros,
            observacao_outros,
        )
    ):
        validar_edicao_financeira(fatura)
        if valor_aluguel is not None:
            fatura.valor_aluguel = _normalizar_valor_financeiro(
                valor_aluguel,
                "O valor do aluguel",
            )
            campos_atualizados.append("valor_aluguel")
        if desconto is not None:
            fatura.desconto = _normalizar_valor_financeiro(
                desconto,
                "O desconto",
            )
            campos_atualizados.append("desconto")
        for campo, valor, descricao in (
            ("valor_condominio", valor_condominio, "O valor do condomínio"),
            ("valor_iptu", valor_iptu, "O valor do IPTU"),
        ):
            if valor is not None:
                setattr(
                    fatura,
                    campo,
                    _normalizar_valor_financeiro(valor, descricao),
                )
                campos_atualizados.append(campo)
        if edita_bonificacao:
            _configurar_bonificacao_fatura(
                fatura,
                modo=modo_bonificacao,
                tipo=tipo_bonificacao,
                valor=bonificacao_especifica,
                valor_legado=valor_bonificacao or Decimal("0.00"),
                dia_limite_legado=(
                    None
                    if dia_limite_bonificacao is _NAO_INFORMADO
                    else dia_limite_bonificacao
                ),
            )
            campos_atualizados.extend(
                [
                    "valor_bonificacao",
                    "dia_limite_bonificacao",
                    "origem_bonificacao_emissao",
                    "tipo_bonificacao_emissao",
                    "percentual_bonificacao_emissao",
                    "valor_bonificacao_fixa_emissao",
                    "dias_antecedencia_bonificacao_emissao",
                    "data_limite_bonificacao",
                ]
            )
        if valor_outros is not None:
            fatura.valor_outros = _normalizar_valor_outros(valor_outros)
            campos_atualizados.append("valor_outros")
        if observacao_outros is not None:
            fatura.observacao_outros = observacao_outros.strip()
            campos_atualizados.append("observacao_outros")
        try:
            fatura.recalcular_valor_total()
            if (
                fatura.tipo_bonificacao_emissao
                == Fatura.TipoBonificacao.VALOR_FIXO
                and fatura.valor_bonificacao_fixa_emissao
                > fatura.valor_total
            ):
                raise ValueError(
                    "A bonificação não pode superar o valor elegível "
                    "da cobrança."
                )
        except ValidationError as exc:
            raise ValueError(" ".join(exc.messages)) from exc
        fatura.valor_original = fatura.subtotal
        campos_atualizados.extend(["valor_total", "valor_original"])

    if campos_atualizados:
        try:
            fatura.full_clean(
                validate_unique=False,
                validate_constraints=False,
            )
            fatura.save(update_fields=campos_atualizados)
            valores_novos = _snapshot_financeiro(fatura)
            if valores_novos != valores_anteriores:
                _registrar_historico_financeiro(
                    fatura,
                    HistoricoFinanceiroFatura.Acao.VALORES_FINANCEIROS_ALTERADOS,
                    usuario=usuario,
                    valores_anteriores=valores_anteriores,
                )
        except ValidationError as exc:
            raise ValueError(" ".join(exc.messages)) from exc
        except IntegrityError as exc:
            raise ValueError(
                "Os valores da fatura violam uma regra de integridade."
            ) from exc
    return fatura


@transaction.atomic
def excluir_fatura(fatura_id):
    try:
        fatura = (
            Fatura.objects
            .select_for_update(of=("self",))
            .select_related("apartamento", "leitura")
            .get(pk=fatura_id)
        )
    except Fatura.DoesNotExist as exc:
        raise ValueError("Fatura não encontrada.") from exc

    identificacao = (
        f"Fatura do apartamento {fatura.apartamento_numero_emissao or fatura.apartamento.numero}, "
        f"mês {fatura.mes:02d}/{fatura.ano}"
    )
    fatura.delete()
    return identificacao


def buscar_leitura_anterior(leitura_atual, campo=None):
    if campo not in {None, "leitura_agua", "leitura_gas"}:
        raise ValueError("Campo de leitura inválido.")

    queryset = (
        Leitura.objects
        .filter(
            apartamento_id=leitura_atual.apartamento_id,
        )
        .exclude(pk=leitura_atual.pk)
        .filter(
            models.Q(ano__lt=leitura_atual.ano)
            | models.Q(
                ano=leitura_atual.ano,
                mes__lt=leitura_atual.mes,
            )
        )
    )
    if campo is not None:
        queryset = queryset.filter(**{f"{campo}__isnull": False})
    return queryset.order_by("-ano", "-mes", "-id").first()


def consultar_valores_padrao_leitura(leitura_id):
    try:
        apartamento = (
            Leitura.objects
            .select_related("apartamento")
            .get(pk=leitura_id)
            .apartamento
        )
        return {
            "valor_aluguel": apartamento.valor_aluguel,
            "valor_condominio": apartamento.valor_condominio,
            "valor_iptu": apartamento.valor_iptu,
            "valor_bonificacao": apartamento.valor_bonificacao,
            "dia_limite_bonificacao": apartamento.dia_limite_bonificacao,
        }
    except Leitura.DoesNotExist as exc:
        raise ValueError("Leitura não encontrada.") from exc


def obter_contexto_geracao_fatura(leitura_id):
    """
    Retorna a leitura solicitada e, quando houver, a fatura da competência.

    A competência é a referência oficial para detectar duplicidade. O vínculo
    direto com a leitura permanece disponível na fatura retornada para que
    inconsistências históricas possam ser identificadas sem criar outra fatura.
    """
    try:
        leitura = (
            Leitura.objects
            .select_related("apartamento")
            .get(pk=leitura_id)
        )
    except (Leitura.DoesNotExist, TypeError, ValueError) as exc:
        raise ValueError("Leitura não encontrada.") from exc

    fatura = (
        Fatura.objects
        .select_related("apartamento", "leitura")
        .filter(
            apartamento_id=leitura.apartamento_id,
            mes=leitura.mes,
            ano=leitura.ano,
        )
        .first()
    )
    return leitura, fatura


@transaction.atomic
def gerar_fatura_mensal(
    leitura_id,
    *,
    valor_aluguel=None,
    desconto=None,
    valor_condominio=None,
    valor_iptu=None,
    valor_bonificacao=None,
    dia_limite_bonificacao=_NAO_INFORMADO,
    modo_bonificacao=None,
    tipo_bonificacao=None,
    bonificacao_especifica=None,
    valor_outros=None,
    observacao_outros=None,
    usuario=None,
):
    leitura_atual = _consultar_contexto_leitura_para_atualizacao(leitura_id)
    _validar_permissao_financeira(
        leitura_atual.apartamento, usuario, Permissao.GERAR_FATURA
    )
    if (
        not leitura_atual.apartamento.ativo
        or leitura_atual.apartamento.arquivado
    ):
        raise ValueError(
            "Não é possível gerar fatura para apartamento arquivado."
        )

    return cadastrar_fatura(
        apartamento_id=leitura_atual.apartamento_id,
        leitura_id=leitura_atual.id,
        mes=leitura_atual.mes,
        ano=leitura_atual.ano,
        valor_aluguel=valor_aluguel,
        desconto=desconto,
        valor_condominio=valor_condominio,
        valor_iptu=valor_iptu,
        valor_bonificacao=valor_bonificacao,
        dia_limite_bonificacao=dia_limite_bonificacao,
        modo_bonificacao=modo_bonificacao,
        tipo_bonificacao=tipo_bonificacao,
        bonificacao_especifica=bonificacao_especifica,
        valor_outros=valor_outros,
        observacao_outros=observacao_outros,
        usuario=usuario,
    )


@transaction.atomic
def executar_fechamento_mensal(mes, ano):
    if isinstance(mes, bool) or not isinstance(mes, int) or not 1 <= mes <= 12:
        raise ValueError("O mês deve estar entre 1 e 12.")
    if (
        isinstance(ano, bool)
        or not isinstance(ano, int)
        or ano < 2000
        or ano > ANO_MAXIMO
    ):
        raise ValueError("Informe um ano válido.")

    logger.info(
        "Fechamento mensal iniciado para %02d/%d.",
        mes,
        ano,
    )
    leituras_competencia = Leitura.objects.filter(
        mes=mes,
        ano=ano,
    ).select_related("apartamento")
    faturas_competencia = Fatura.objects.filter(
        mes=mes,
        ano=ano,
    )
    apartamentos = list(
        Apartamento.objects
        .select_for_update()
        .order_by("id")
        .prefetch_related(
            Prefetch(
                "leituras",
                queryset=leituras_competencia,
                to_attr="leituras_fechamento",
            ),
            Prefetch(
                "faturas",
                queryset=faturas_competencia,
                to_attr="faturas_fechamento",
            ),
        )
    )

    geradas = 0
    existentes = 0
    sem_leitura = []
    falhas_tarifarias = []
    try:
        for apartamento in apartamentos:
            if not apartamento.leituras_fechamento:
                sem_leitura.append(apartamento)
                continue
            if apartamento.faturas_fechamento:
                existentes += 1
                continue
            try:
                gerar_fatura_mensal(
                    apartamento.leituras_fechamento[0].id
                )
                geradas += 1
            except (TarifaNaoConfiguradaError, ConsumoSemFaixaError) as exc:
                falhas_tarifarias.append((apartamento, str(exc)))
                logger.warning(
                    "Fatura não gerada para apartamento %s em %02d/%d: %s",
                    apartamento.pk, mes, ano, exc,
                )
    except Exception:
        logger.exception(
            "Fechamento mensal falhou para %02d/%d; "
            "a transação será revertida.",
            mes,
            ano,
        )
        raise

    resultado = ResultadoFechamento(
        apartamentos_analisados=len(apartamentos),
        faturas_geradas=geradas,
        faturas_existentes=existentes,
        apartamentos_sem_leitura=tuple(sem_leitura),
        falhas_tarifarias=tuple(falhas_tarifarias),
    )
    logger.info(
        "Fechamento mensal concluído para %02d/%d: "
        "%d faturas geradas, %d já existentes e %d pendências.",
        mes,
        ano,
        resultado.faturas_geradas,
        resultado.faturas_existentes,
        resultado.total_sem_leitura,
    )
    return resultado


@transaction.atomic
def executar_fechamento_mensal_por_condominio(condominio, mes, ano):
    """Executa o fechamento somente no condomínio informado."""
    if isinstance(mes, bool) or not isinstance(mes, int) or not 1 <= mes <= 12:
        raise ValueError("O mês deve estar entre 1 e 12.")
    if isinstance(ano, bool) or not isinstance(ano, int) or not 2000 <= ano <= ANO_MAXIMO:
        raise ValueError("Informe um ano válido.")
    leituras_competencia = (
        Leitura.objects
        .filter(mes=mes, ano=ano)
        .select_related("apartamento")
        .order_by("id")
    )
    faturas_competencia = Fatura.objects.filter(mes=mes, ano=ano)
    apartamentos = list(
        Apartamento.objects
        .select_for_update()
        .filter(condominio=condominio)
        .order_by("id")
        .prefetch_related(
            Prefetch(
                "leituras",
                queryset=leituras_competencia,
                to_attr="leituras_fechamento",
            ),
            Prefetch(
                "faturas",
                queryset=faturas_competencia,
                to_attr="faturas_fechamento",
            ),
        )
    )
    geradas = existentes = 0
    sem_leitura = []
    falhas = []
    for apartamento in apartamentos:
        if not apartamento.leituras_fechamento:
            sem_leitura.append(apartamento)
            continue
        if apartamento.faturas_fechamento:
            existentes += 1
            continue
        try:
            gerar_fatura_mensal(apartamento.leituras_fechamento[0].id)
            geradas += 1
        except (TarifaNaoConfiguradaError, ConsumoSemFaixaError) as exc:
            falhas.append((apartamento, str(exc)))
    return ResultadoFechamento(
        apartamentos_analisados=len(apartamentos),
        faturas_geradas=geradas,
        faturas_existentes=existentes,
        apartamentos_sem_leitura=tuple(sem_leitura),
        falhas_tarifarias=tuple(falhas),
    )


def listar_faturas_para_download_mensal(mes, ano):
    if isinstance(mes, bool) or not isinstance(mes, int) or not 1 <= mes <= 12:
        raise ValueError("O mês deve estar entre 1 e 12.")
    if (
        isinstance(ano, bool)
        or not isinstance(ano, int)
        or ano < 2000
        or ano > ANO_MAXIMO
    ):
        raise ValueError("Informe um ano válido.")

    return (
        Fatura.objects
        .select_related("apartamento", "leitura")
        .filter(mes=mes, ano=ano)
        .exclude(status=Fatura.Status.CANCELADA)
        .order_by(
            "apartamento_bloco_emissao",
            "apartamento_numero_emissao",
            "id",
        )
    )


def listar_faturas_download_por_condominio(condominio, mes, ano):
    return listar_faturas_para_download_mensal(mes, ano).filter(
        apartamento__condominio=condominio
    )
