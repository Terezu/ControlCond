from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from faturas.fatura_service import consultar_fatura


PASTA_PDFS = Path("faturas_geradas")


def formatar_moeda(valor):
    return f"R$ {valor:.2f}".replace(".", ",")


def gerar_pdf_fatura(fatura_id):
    fatura = consultar_fatura(fatura_id)

    (
        id_fatura,
        numero_apartamento,
        bloco,
        mes,
        ano,
        consumo_agua,
        consumo_gas,
        valor_agua,
        valor_gas,
        valor_total,
        status
    ) = fatura

    PASTA_PDFS.mkdir(exist_ok=True)

    nome_arquivo = f"fatura_{id_fatura}_apto_{numero_apartamento}_{mes}_{ano}.pdf"
    caminho_pdf = PASTA_PDFS / nome_arquivo

    pdf = canvas.Canvas(str(caminho_pdf), pagesize=A4)
    largura, altura = A4

    y = altura - 80

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(50, y, "ControlCond - Fatura Condominial")

    y -= 50
    pdf.setFont("Helvetica", 12)
    pdf.drawString(50, y, f"Fatura ID: {id_fatura}")

    y -= 25
    pdf.drawString(50, y, f"Apartamento: {numero_apartamento}")

    y -= 25
    pdf.drawString(50, y, f"Bloco: {bloco}")

    y -= 25
    pdf.drawString(50, y, f"Referencia: {mes}/{ano}")

    y -= 25
    pdf.drawString(50, y, f"Status: {status}")

    y -= 45
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(50, y, "Consumos")

    y -= 30
    pdf.setFont("Helvetica", 12)
    pdf.drawString(50, y, f"Consumo de agua: {consumo_agua} m³")

    y -= 25
    pdf.drawString(50, y, f"Consumo de gas: {consumo_gas} m³")

    y -= 45
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(50, y, "Valores")

    y -= 30
    pdf.setFont("Helvetica", 12)
    pdf.drawString(50, y, f"Valor da agua: {formatar_moeda(valor_agua)}")

    y -= 25
    pdf.drawString(50, y, f"Valor do gas: {formatar_moeda(valor_gas)}")

    y -= 35
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(50, y, f"Valor total: {formatar_moeda(valor_total)}")

    pdf.save()

    return caminho_pdf
