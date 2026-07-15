from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from .services import buscar_leitura_anterior


MARGEM_ESQUERDA = 50
ESPACO_PADRAO = 20


def formatar_decimal(valor):
    if valor is None:
        return "Não informado"

    return str(valor).replace(".", ",")


def formatar_valor_monetario(valor):
    return f"{valor:.2f}".replace(".", ",")


def obter_leituras_fatura(fatura):
    leitura_atual = fatura.leitura

    if leitura_atual is None:
        return {
            "agua_anterior": None,
            "agua_atual": None,
            "gas_anterior": None,
            "gas_atual": None,
        }

    leitura_anterior = buscar_leitura_anterior(leitura_atual)

    if leitura_anterior is not None:
        agua_anterior = leitura_anterior.leitura_agua
        gas_anterior = leitura_anterior.leitura_gas
    else:
        agua_anterior = fatura.apartamento.leitura_base_agua
        gas_anterior = fatura.apartamento.leitura_base_gas

    return {
        "agua_anterior": agua_anterior,
        "agua_atual": leitura_atual.leitura_agua,
        "gas_anterior": gas_anterior,
        "gas_atual": leitura_atual.leitura_gas,
    }


def desenhar_cabecalho(pdf, fatura, y):
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(
        MARGEM_ESQUERDA,
        y,
        "CONTROLCOND",
    )

    y -= 35

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(
        MARGEM_ESQUERDA,
        y,
        "Fatura de consumo",
    )

    y -= 25

    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(
        MARGEM_ESQUERDA,
        y,
        f"FATURA Nº {fatura.id:06d}",
    )

    return y - 35


def desenhar_dados_apartamento(pdf, fatura, y):
    pdf.setFont("Helvetica", 11)

    pdf.drawString(
        MARGEM_ESQUERDA,
        y,
        f"Apartamento: {fatura.apartamento.numero}",
    )

    y -= ESPACO_PADRAO

    bloco = fatura.apartamento.bloco or "Não informado"

    pdf.drawString(
        MARGEM_ESQUERDA,
        y,
        f"Bloco: {bloco}",
    )

    y -= ESPACO_PADRAO

    pdf.drawString(
        MARGEM_ESQUERDA,
        y,
        f"Referência: {fatura.mes:02d}/{fatura.ano}",
    )

    y -= ESPACO_PADRAO

    data_emissao = fatura.data_emissao.strftime("%d/%m/%Y")

    pdf.drawString(
        MARGEM_ESQUERDA,
        y,
        f"Data de emissão: {data_emissao}",
    )

    y -= ESPACO_PADRAO

    pdf.drawString(
        MARGEM_ESQUERDA,
        y,
        f"Status: {fatura.get_status_display()}",
    )

    return y - 35


def desenhar_linha_divisoria(pdf, largura, y):
    pdf.line(
        MARGEM_ESQUERDA,
        y,
        largura - MARGEM_ESQUERDA,
        y,
    )

    return y - 30


def desenhar_consumo_agua(pdf, fatura, leituras, y):
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(
        MARGEM_ESQUERDA,
        y,
        "Água",
    )

    y -= 25

    pdf.setFont("Helvetica", 11)

    pdf.drawString(
        MARGEM_ESQUERDA,
        y,
        (
            "Leitura anterior: "
            f"{formatar_decimal(leituras['agua_anterior'])}"
        ),
    )

    y -= ESPACO_PADRAO

    pdf.drawString(
        MARGEM_ESQUERDA,
        y,
        (
            "Leitura atual: "
            f"{formatar_decimal(leituras['agua_atual'])}"
        ),
    )

    y -= ESPACO_PADRAO

    pdf.drawString(
        MARGEM_ESQUERDA,
        y,
        f"Consumo: {formatar_decimal(fatura.consumo_agua)} m³",
    )

    y -= ESPACO_PADRAO

    pdf.drawString(
        MARGEM_ESQUERDA,
        y,
        (
            "Valor: R$ "
            f"{formatar_valor_monetario(fatura.valor_agua)}"
        ),
    )

    return y - 35


def desenhar_consumo_gas(pdf, fatura, leituras, y):
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(
        MARGEM_ESQUERDA,
        y,
        "Gás",
    )

    y -= 25

    pdf.setFont("Helvetica", 11)

    pdf.drawString(
        MARGEM_ESQUERDA,
        y,
        (
            "Leitura anterior: "
            f"{formatar_decimal(leituras['gas_anterior'])}"
        ),
    )

    y -= ESPACO_PADRAO

    pdf.drawString(
        MARGEM_ESQUERDA,
        y,
        (
            "Leitura atual: "
            f"{formatar_decimal(leituras['gas_atual'])}"
        ),
    )

    y -= ESPACO_PADRAO

    pdf.drawString(
        MARGEM_ESQUERDA,
        y,
        f"Consumo: {formatar_decimal(fatura.consumo_gas)} m³",
    )

    y -= ESPACO_PADRAO

    pdf.drawString(
        MARGEM_ESQUERDA,
        y,
        (
            "Valor: R$ "
            f"{formatar_valor_monetario(fatura.valor_gas)}"
        ),
    )

    return y - 35


def desenhar_total(pdf, fatura, y):
    pdf.setFont("Helvetica-Bold", 16)

    pdf.drawString(
        MARGEM_ESQUERDA,
        y,
        (
            "Total: R$ "
            f"{formatar_valor_monetario(fatura.valor_total)}"
        ),
    )

    return y - 45


def desenhar_rodape(pdf, largura, y):
    pdf.line(
        MARGEM_ESQUERDA,
        y,
        largura - MARGEM_ESQUERDA,
        y,
    )

    y -= 25

    pdf.setFont("Helvetica", 9)

    pdf.drawString(
        MARGEM_ESQUERDA,
        y,
        "Documento gerado automaticamente pelo ControlCond.",
    )

    y -= 15

    pdf.drawString(
        MARGEM_ESQUERDA,
        y,
        (
            "Em caso de dúvidas, entre em contato com "
            "a administração do condomínio."
        ),
    )


def gerar_pdf_fatura(fatura):
    buffer = BytesIO()

    pdf = canvas.Canvas(
        buffer,
        pagesize=A4,
    )

    largura, altura = A4
    y = altura - 60

    pdf.setTitle(
        f"Fatura {fatura.mes:02d}-{fatura.ano} "
        f"Apartamento {fatura.apartamento.numero}"
    )

    leituras = obter_leituras_fatura(fatura)

    y = desenhar_cabecalho(pdf, fatura, y)
    y = desenhar_dados_apartamento(pdf, fatura, y)
    y = desenhar_linha_divisoria(pdf, largura, y)
    y = desenhar_consumo_agua(pdf, fatura, leituras, y)
    y = desenhar_consumo_gas(pdf, fatura, leituras, y)
    y = desenhar_linha_divisoria(pdf, largura, y)
    y = desenhar_total(pdf, fatura, y)

    desenhar_rodape(pdf, largura, y)

    pdf.showPage()
    pdf.save()

    buffer.seek(0)

    return buffer
