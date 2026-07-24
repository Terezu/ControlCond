from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from apartamentos.models import Apartamento
from calculos.services import calcular_agua, calcular_gas
from configuracoes.services import obter_configuracao
from leituras.models import Leitura

from .models import ANO_MAXIMO, Fatura, HistoricoStatusFatura


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


def _calcular_dados_da_leitura(leitura_atual, valor_m3_gas):
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
    )
    resultado_gas = calcular_gas(
        leitura_gas_anterior,
        leitura_atual.leitura_gas,
        valor_m3_gas,
    )
    return {
        "consumo_agua": resultado_agua["consumo"],
        "consumo_gas": resultado_gas["consumo"],
        "valor_agua": resultado_agua["valor"],
        "valor_gas": resultado_gas["valor"],
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
):
    apartamento = _consultar_apartamento_para_atualizacao(apartamento_id)
    valor_m3_gas = obter_configuracao().valor_m3_gas
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
    consumo_gas = _normalizar_consumo(
        consumo_gas,
        "gás",
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
        dados_calculados = _calcular_dados_da_leitura(
            leitura,
            valor_m3_gas,
        )
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
    else:
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
        mes=mes,
        ano=ano,
        consumo_agua=consumo_agua,
        consumo_gas=consumo_gas,
        valor_agua=valor_agua,
        valor_gas=valor_gas,
        valor_aluguel=valor_aluguel,
        desconto=desconto,
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
    except ValidationError as exc:
        raise ValueError(" ".join(exc.messages)) from exc
    try:
        fatura.full_clean(
            validate_unique=False,
            validate_constraints=False,
        )
        with transaction.atomic():
            fatura.save(force_insert=True)
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
            )
            .get(id=fatura_id)
        )
    except Fatura.DoesNotExist as erro:
        raise ValueError("Fatura não encontrada.") from erro


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


def _consultar_fatura_para_atualizacao(fatura_id):
    try:
        return (
            Fatura.objects
            .select_for_update()
            .select_related("apartamento", "leitura")
            .get(pk=fatura_id)
        )
    except Fatura.DoesNotExist as exc:
        raise ValueError("Fatura não encontrada.") from exc


def _normalizar_motivo(motivo, acao):
    motivo = (motivo or "").strip()
    rotulo = (
        "estorno"
        if acao == HistoricoStatusFatura.Acao.PAGAMENTO_ESTORNADO
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
    status_anterior = fatura.status
    agora = timezone.now()
    campos_atualizados = ["status"]
    fatura.status = novo_status

    if novo_status == Fatura.Status.PAGA:
        fatura.data_pagamento = agora
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
        campos_atualizados.append("data_pagamento")
    elif status_anterior == Fatura.Status.CANCELADA:
        fatura.data_cancelamento = None
        campos_atualizados.append("data_cancelamento")

    fatura.save(update_fields=campos_atualizados)
    if usuario is not None and not getattr(
        usuario,
        "is_authenticated",
        False,
    ):
        usuario = None
    HistoricoStatusFatura.objects.create(
        fatura=fatura,
        status_anterior=status_anterior,
        novo_status=novo_status,
        acao=acao,
        motivo=motivo,
        usuario=usuario,
    )
    return fatura, True


def marcar_fatura_como_paga(fatura_id, usuario=None):
    return _executar_acao_status(
        fatura_id,
        status_origem=Fatura.Status.PENDENTE,
        novo_status=Fatura.Status.PAGA,
        acao=HistoricoStatusFatura.Acao.PAGAMENTO_CONFIRMADO,
        usuario=usuario,
    )


def cancelar_fatura(fatura_id, usuario=None):
    return _executar_acao_status(
        fatura_id,
        status_origem=Fatura.Status.PENDENTE,
        novo_status=Fatura.Status.CANCELADA,
        acao=HistoricoStatusFatura.Acao.FATURA_CANCELADA,
        usuario=usuario,
    )


def estornar_pagamento(fatura_id, motivo, usuario=None):
    return _executar_acao_status(
        fatura_id,
        status_origem=Fatura.Status.PAGA,
        novo_status=Fatura.Status.PENDENTE,
        acao=HistoricoStatusFatura.Acao.PAGAMENTO_ESTORNADO,
        motivo=motivo,
        usuario=usuario,
        exige_motivo=True,
    )


def reabrir_fatura(fatura_id, motivo, usuario=None):
    return _executar_acao_status(
        fatura_id,
        status_origem=Fatura.Status.CANCELADA,
        novo_status=Fatura.Status.PENDENTE,
        acao=HistoricoStatusFatura.Acao.FATURA_REABERTA,
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
):
    fatura = _consultar_fatura_para_atualizacao(fatura_id)

    campos_atualizados = []
    if valor_aluguel is not None or desconto is not None:
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
        try:
            fatura.recalcular_valor_total()
        except ValidationError as exc:
            raise ValueError(" ".join(exc.messages)) from exc
        campos_atualizados.append("valor_total")

    if campos_atualizados:
        try:
            fatura.full_clean(
                validate_unique=False,
                validate_constraints=False,
            )
            fatura.save(update_fields=campos_atualizados)
        except ValidationError as exc:
            raise ValueError(" ".join(exc.messages)) from exc
        except IntegrityError as exc:
            raise ValueError(
                "Os valores da fatura violam uma regra de integridade."
            ) from exc
    return fatura


def excluir_fatura(fatura_id):
    fatura = consultar_fatura(fatura_id)
    fatura.delete()


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


def consultar_valor_aluguel_leitura(leitura_id):
    try:
        return (
            Leitura.objects
            .select_related("apartamento")
            .get(pk=leitura_id)
            .apartamento
            .valor_aluguel
        )
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
):
    leitura_atual = _consultar_contexto_leitura_para_atualizacao(leitura_id)

    return cadastrar_fatura(
        apartamento_id=leitura_atual.apartamento_id,
        leitura_id=leitura_atual.id,
        mes=leitura_atual.mes,
        ano=leitura_atual.ano,
        valor_aluguel=valor_aluguel,
        desconto=desconto,
    )
