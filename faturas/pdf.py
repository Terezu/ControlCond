from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from configuracoes.services import obter_configuracao

MARGEM_ESQUERDA = 50
ESPACO_PADRAO = 20


def formatar_decimal(valor):
    if valor is None:
        return "Não informado"

    return str(valor).replace(".", ",")


def formatar_valor_monetario(valor):
    return f"{valor:.2f}".replace(".", ",")


def obter_leituras_fatura(fatura):
    return {
        "agua_anterior": fatura.leitura_agua_anterior,
        "agua_atual": fatura.leitura_agua_atual,
        "gas_anterior": fatura.leitura_gas_anterior,
        "gas_atual": fatura.leitura_gas_atual,
    }


def _juntar_partes(*partes, separador=" · "):
    return separador.join(
        str(parte).strip()
        for parte in partes
        if parte is not None and str(parte).strip()
    )


def _quebrar_texto(pdf, texto, largura_maxima, fonte, tamanho):
    linhas = []
    for paragrafo in str(texto).splitlines() or [""]:
        palavras = paragrafo.split()
        if not palavras:
            linhas.append("")
            continue
        linha = palavras.pop(0)
        for palavra in palavras:
            candidata = f"{linha} {palavra}"
            if pdf.stringWidth(candidata, fonte, tamanho) <= largura_maxima:
                linha = candidata
            else:
                linhas.append(linha)
                linha = palavra
        linhas.append(linha)
    return linhas


def _desenhar_logo(pdf, configuracao, largura, y):
    if not configuracao.logo:
        return
    try:
        caminho = Path(configuracao.logo.path)
        if not caminho.is_file():
            return
        imagem = ImageReader(str(caminho))
        pdf.drawImage(
            imagem,
            largura - MARGEM_ESQUERDA - 110,
            y - 55,
            width=110,
            height=55,
            preserveAspectRatio=True,
            anchor="c",
            mask="auto",
        )
    except Exception:
        # O documento deve continuar disponível mesmo se o arquivo tiver sido
        # removido ou não puder ser interpretado pelo ReportLab.
        return


def desenhar_cabecalho(pdf, fatura, configuracao, largura, y):
    _desenhar_logo(pdf, configuracao, largura, y)

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(
        MARGEM_ESQUERDA,
        y,
        configuracao.nome or "CONTROLCOND",
    )

    dados_condominio = [
        _juntar_partes(
            f"CNPJ: {configuracao.cnpj}" if configuracao.cnpj else "",
            configuracao.telefone,
            configuracao.email,
        ),
        _juntar_partes(configuracao.endereco, configuracao.cep),
        _juntar_partes(
            configuracao.cidade,
            configuracao.estado,
            separador=" - ",
        ),
    ]
    pdf.setFont("Helvetica", 8)
    for linha in dados_condominio:
        if linha:
            y -= 12
            pdf.drawString(MARGEM_ESQUERDA, y, linha)

    y -= 30

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
        f"Apartamento: {fatura.apartamento_numero_emissao}",
    )

    y -= ESPACO_PADRAO

    bloco = fatura.apartamento_bloco_emissao or "Não informado"

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
        "Água e esgoto",
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


def desenhar_observacoes(pdf, configuracao, largura, altura, y):
    if not configuracao.observacoes_padrao:
        return y

    fonte = "Helvetica"
    tamanho = 9
    largura_texto = largura - (2 * MARGEM_ESQUERDA)
    linhas = _quebrar_texto(
        pdf,
        configuracao.observacoes_padrao,
        largura_texto,
        fonte,
        tamanho,
    )

    if y < 105:
        pdf.showPage()
        y = altura - 60

    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(MARGEM_ESQUERDA, y, "Observações")
    y -= 15
    pdf.setFont(fonte, tamanho)

    for linha in linhas:
        if y < 105:
            pdf.showPage()
            y = altura - 60
            pdf.setFont(fonte, tamanho)
        pdf.drawString(MARGEM_ESQUERDA, y, linha)
        y -= 13

    return y - 10


def desenhar_rodape(pdf, configuracao, largura, y):
    y = max(y, 75)
    pdf.line(
        MARGEM_ESQUERDA,
        y,
        largura - MARGEM_ESQUERDA,
        y,
    )

    y -= 25

    pdf.setFont("Helvetica", 9)

    linhas = []
    if configuracao.texto_rodape:
        linhas.extend(
            _quebrar_texto(
                pdf,
                configuracao.texto_rodape,
                largura - (2 * MARGEM_ESQUERDA),
                "Helvetica",
                9,
            )
        )
    else:
        linhas.append("Documento gerado automaticamente pelo ControlCond.")

    administradora = _juntar_partes(
        configuracao.administradora_nome,
        (
            f"Responsável: {configuracao.administradora_responsavel}"
            if configuracao.administradora_responsavel
            else ""
        ),
        configuracao.administradora_telefone,
        configuracao.administradora_email,
    )
    if administradora:
        linhas.append(administradora)
    elif not configuracao.texto_rodape:
        linhas.append(
            "Em caso de dúvidas, entre em contato com a administração "
            "do condomínio."
        )

    for linha in linhas[:3]:
        pdf.drawString(MARGEM_ESQUERDA, y, linha)
        y -= 13


def gerar_pdf_fatura(fatura, configuracao=None):
    buffer = BytesIO()
    configuracao = configuracao or obter_configuracao()

    pdf = canvas.Canvas(
        buffer,
        pagesize=A4,
    )

    largura, altura = A4
    y = altura - 60

    pdf.setTitle(
        f"Fatura {fatura.mes:02d}-{fatura.ano} "
        f"Apartamento {fatura.apartamento_numero_emissao}"
    )

    leituras = obter_leituras_fatura(fatura)

    y = desenhar_cabecalho(pdf, fatura, configuracao, largura, y)
    y = desenhar_dados_apartamento(pdf, fatura, y)
    y = desenhar_linha_divisoria(pdf, largura, y)
    y = desenhar_consumo_agua(pdf, fatura, leituras, y)
    y = desenhar_consumo_gas(pdf, fatura, leituras, y)
    y = desenhar_linha_divisoria(pdf, largura, y)
    y = desenhar_total(pdf, fatura, y)
    y = desenhar_observacoes(
        pdf,
        configuracao,
        largura,
        altura,
        y,
    )

    desenhar_rodape(pdf, configuracao, largura, y)

    pdf.showPage()
    pdf.save()

    buffer.seek(0)

    return buffer
