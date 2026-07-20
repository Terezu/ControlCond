from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction

from apartamentos.models import Apartamento
from calculos.services import calcular_agua, calcular_gas
from leituras.models import Leitura

from .models import ANO_MAXIMO, Fatura


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
    )
    resultado_gas = calcular_gas(
        leitura_gas_anterior,
        leitura_atual.leitura_gas,
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
):
    apartamento = _consultar_apartamento_para_atualizacao(apartamento_id)

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
        valor_total=valor_agua + valor_gas,
        status=status,
        apartamento_numero_emissao=apartamento.numero,
        apartamento_bloco_emissao=apartamento.bloco,
        leitura_agua_anterior=leitura_agua_anterior,
        leitura_agua_atual=leitura_agua_atual,
        leitura_gas_anterior=leitura_gas_anterior,
        leitura_gas_atual=leitura_gas_atual,
    )
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


def editar_fatura(fatura_id, *, status=None):
    fatura = consultar_fatura(fatura_id)
    if status is not None:
        if status not in Fatura.Status.values:
            raise ValueError("Status de fatura inválido.")
        fatura.status = status
        fatura.save(update_fields=["status"])
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


@transaction.atomic
def gerar_fatura_mensal(leitura_id):
    leitura_atual = _consultar_contexto_leitura_para_atualizacao(leitura_id)

    return cadastrar_fatura(
        apartamento_id=leitura_atual.apartamento_id,
        leitura_id=leitura_atual.id,
        mes=leitura_atual.mes,
        ano=leitura_atual.ano,
    )


def gerar_pdf_fatura(fatura_id, pasta_pdfs=None):
    """Gera o mesmo PDF da interface web e o salva em uma pasta local."""
    from django.conf import settings

    from .pdf import gerar_pdf_fatura as renderizar_pdf_fatura

    fatura = consultar_fatura(fatura_id)
    if pasta_pdfs is None:
        pasta_pdfs = Path(settings.BASE_DIR) / "faturas_geradas"
    else:
        pasta_pdfs = Path(pasta_pdfs)
    pasta_pdfs.mkdir(parents=True, exist_ok=True)

    caminho_pdf = pasta_pdfs / (
        f"fatura_{fatura.id}_{fatura.mes}_{fatura.ano}.pdf"
    )
    arquivo_pdf = renderizar_pdf_fatura(fatura)
    try:
        with caminho_pdf.open("wb") as destino:
            destino.write(arquivo_pdf.getbuffer())
    finally:
        arquivo_pdf.close()
    return caminho_pdf
