from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction

from apartamentos.services import consultar_apartamento
from calculos.services import calcular_agua, calcular_gas
from leituras.models import Leitura
from leituras.services import consultar_leitura

from .models import ANO_MAXIMO, Fatura


def cadastrar_fatura(
    apartamento_id,
    mes,
    ano,
    consumo_agua,
    consumo_gas,
    valor_agua=0,
    valor_gas=0,
    leitura_id=None,
    status="pendente",
    leitura_agua_anterior=None,
    leitura_agua_atual=None,
    leitura_gas_anterior=None,
    leitura_gas_atual=None,
):
    apartamento = consultar_apartamento(apartamento_id)

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
    if (
        isinstance(consumo_agua, bool)
        or not isinstance(consumo_agua, int)
        or consumo_agua < 0
    ):
        raise ValueError(
            "O consumo de água deve ser um número inteiro não negativo."
        )
    if (
        isinstance(consumo_gas, bool)
        or not isinstance(consumo_gas, int)
        or consumo_gas < 0
    ):
        raise ValueError(
            "O consumo de gás deve ser um número inteiro não negativo."
        )

    fatura_existente = Fatura.objects.filter(
        apartamento=apartamento,
        mes=mes,
        ano=ano,
    ).exists()

    if fatura_existente:
        raise ValueError("Já existe uma fatura para este apartamento neste mês e ano.")

    leitura = consultar_leitura(leitura_id) if leitura_id is not None else None

    if leitura is not None and (
        leitura.apartamento_id != apartamento.id
        or leitura.mes != mes
        or leitura.ano != ano
    ):
        raise ValueError(
            "A leitura deve pertencer ao mesmo apartamento, mês e ano da fatura."
        )

    try:
        valor_agua = Decimal(str(valor_agua))
        valor_gas = Decimal(str(valor_gas))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Os valores da fatura são inválidos.") from exc

    if (
        not valor_agua.is_finite()
        or not valor_gas.is_finite()
        or valor_agua < 0
        or valor_gas < 0
    ):
        raise ValueError("Os valores da fatura não podem ser negativos ou inválidos.")

    if leitura is not None:
        if leitura_agua_atual is None:
            leitura_agua_atual = leitura.leitura_agua
        if leitura_gas_atual is None:
            leitura_gas_atual = leitura.leitura_gas
        if leitura_agua_anterior is None:
            anterior_agua = buscar_leitura_anterior(leitura, "leitura_agua")
            leitura_agua_anterior = (
                anterior_agua.leitura_agua
                if anterior_agua is not None
                else apartamento.leitura_base_agua
            )
        if leitura_gas_anterior is None:
            anterior_gas = buscar_leitura_anterior(leitura, "leitura_gas")
            leitura_gas_anterior = (
                anterior_gas.leitura_gas
                if anterior_gas is not None
                else apartamento.leitura_base_gas
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


def listar_faturas():
    return Fatura.objects.select_related("apartamento", "leitura").order_by(
        "-ano", "-mes", "-id"
    )


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
    leitura_atual = consultar_leitura(leitura_id)

    if Fatura.objects.filter(
        apartamento=leitura_atual.apartamento,
        mes=leitura_atual.mes,
        ano=leitura_atual.ano,
    ).exists():
        raise ValueError(
            "Já existe uma fatura para este apartamento neste mês e ano."
        )

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

    return cadastrar_fatura(
        apartamento_id=leitura_atual.apartamento_id,
        leitura_id=leitura_atual.id,
        mes=leitura_atual.mes,
        ano=leitura_atual.ano,
        consumo_agua=resultado_agua["consumo"],
        consumo_gas=resultado_gas["consumo"],
        valor_agua=resultado_agua["valor"],
        valor_gas=resultado_gas["valor"],
        leitura_agua_anterior=leitura_agua_anterior,
        leitura_agua_atual=leitura_atual.leitura_agua,
        leitura_gas_anterior=leitura_gas_anterior,
        leitura_gas_atual=leitura_atual.leitura_gas,
    )


def gerar_pdf_fatura(fatura_id, pasta_pdfs=Path("faturas_geradas")):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    fatura = consultar_fatura(fatura_id)
    pasta_pdfs.mkdir(parents=True, exist_ok=True)
    caminho_pdf = pasta_pdfs / (
        f"fatura_{fatura.id}_{fatura.mes}_{fatura.ano}.pdf"
    )
    pdf = canvas.Canvas(str(caminho_pdf), pagesize=A4)
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(50, 760, "ControlCond - Fatura Condominial")
    pdf.setFont("Helvetica", 12)
    linhas = [
        f"Fatura ID: {fatura.id}",
        f"Apartamento: {fatura.apartamento_numero_emissao}",
        f"Bloco: {fatura.apartamento_bloco_emissao or '-'}",
        f"Referência: {fatura.mes}/{fatura.ano}",
        f"Consumo de água: {fatura.consumo_agua} m³",
        f"Consumo de gás: {fatura.consumo_gas} m³",
        f"Valor total: R$ {fatura.valor_total:.2f}".replace(".", ","),
        f"Status: {fatura.status}",
    ]
    for indice, linha in enumerate(linhas):
        pdf.drawString(50, 710 - indice * 28, linha)
    pdf.save()
    return caminho_pdf
