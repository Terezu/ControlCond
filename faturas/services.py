from pathlib import Path
from decimal import Decimal

from django.db import transaction

from apartamentos.services import consultar_apartamento
from calculos.services import calcular_agua, calcular_gas
from leituras.services import cadastrar_leitura, consultar_leitura

from .models import Fatura


def cadastrar_fatura(apartamento_id, mes, ano, consumo_agua, consumo_gas,
                     valor_agua=0, valor_gas=0, leitura_id=None, status="pendente"):
    apartamento = consultar_apartamento(apartamento_id)

    fatura_existente = Fatura.objects.filter(
        apartamento=apartamento,
        mes=mes,
        ano=ano
    ).exists()

    if fatura_existente:
        raise ValueError("Já existe uma fatura para este apartamento neste mês e ano.")

    leitura = consultar_leitura(leitura_id) if leitura_id is not None else None

    valor_agua = Decimal(str(valor_agua))
    valor_gas = Decimal(str(valor_gas))

    return Fatura.objects.create(
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
    )

def consultar_fatura(fatura_id):
    try:
        return Fatura.objects.select_related("apartamento", "leitura").get(pk=fatura_id)
    except Fatura.DoesNotExist as exc:
        raise ValueError("Fatura não encontrada.") from exc


def listar_faturas():
    return Fatura.objects.select_related("apartamento", "leitura").order_by("-ano", "-mes", "-id")


def editar_fatura(fatura_id, *, status=None):
    fatura = consultar_fatura(fatura_id)
    if status is not None:
        fatura.status = status
        fatura.save(update_fields=["status"])
    return fatura


def excluir_fatura(fatura_id):
    fatura = consultar_fatura(fatura_id)
    fatura.delete()


@transaction.atomic
def gerar_fatura_mensal(apartamento_id, mes, ano, leitura_agua_anterior,
                        leitura_agua_atual, leitura_gas_anterior, leitura_gas_atual):
    if leitura_agua_atual < leitura_agua_anterior:
        raise ValueError(
            "A leitura atual da água não pode ser menor que a leitura anterior."
        )

    if leitura_gas_atual < leitura_gas_anterior:
        raise ValueError(
            "A leitura atual do gás não pode ser menor que a leitura anterior."
        )

    resultado_agua = calcular_agua(leitura_agua_anterior, leitura_agua_atual)
    resultado_gas = calcular_gas(leitura_gas_anterior, leitura_gas_atual)
    leitura = cadastrar_leitura(
        apartamento_id, mes, ano, leitura_agua_atual, leitura_gas_atual
    )
    fatura = cadastrar_fatura(
        apartamento_id=apartamento_id,
        leitura_id=leitura.id,
        mes=mes,
        ano=ano,
        consumo_agua=resultado_agua["consumo"],
        consumo_gas=resultado_gas["consumo"],
        valor_agua=resultado_agua["valor"],
        valor_gas=resultado_gas["valor"],
    )
    return fatura


def gerar_pdf_fatura(fatura_id, pasta_pdfs=Path("faturas_geradas")):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    fatura = consultar_fatura(fatura_id)
    pasta_pdfs.mkdir(exist_ok=True)
    caminho_pdf = pasta_pdfs / (
        f"fatura_{fatura.id}_apto_{fatura.apartamento.numero}_{fatura.mes}_{fatura.ano}.pdf"
    )
    pdf = canvas.Canvas(str(caminho_pdf), pagesize=A4)
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(50, 760, "ControlCond - Fatura Condominial")
    pdf.setFont("Helvetica", 12)
    linhas = [
        f"Fatura ID: {fatura.id}",
        f"Apartamento: {fatura.apartamento.numero}",
        f"Bloco: {fatura.apartamento.bloco or '-'}",
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
