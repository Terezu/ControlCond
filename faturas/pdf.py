from pathlib import Path
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from configuracoes.services import obter_configuracao


# Geometria geral
MARGEM_HORIZONTAL = 50
MARGEM_SUPERIOR = 42
MARGEM_INFERIOR = 42
ESPACO_SECAO = 18
RAIO_CARD = 6

# Identidade visual
LARGURA_MAXIMA_LOGO = 247.5
ALTURA_MAXIMA_LOGO = 123.75
ESPACO_ENTRE_LOGO_E_CABECALHO = 20

# Paleta e tipografia
COR_PRIMARIA = colors.HexColor("#1F4E5F")
COR_TEXTO = colors.HexColor("#263238")
COR_SECUNDARIA = colors.HexColor("#64748B")
COR_BORDA = colors.HexColor("#D9E2E8")
COR_FUNDO_SUAVE = colors.HexColor("#F5F8FA")
COR_TOTAL = colors.HexColor("#E8F1F4")
FONTE_REGULAR = "Helvetica"
FONTE_DESTAQUE = "Helvetica-Bold"

# Alturas dos blocos
ALTURA_CABECALHO = 132
ALTURA_DADOS_FATURA = 72
ALTURA_CARD_CONSUMO = 150
ALTURA_COMPOSICAO = 124
ALTURA_TOTAL = 100
ALTURA_RODAPE = 58


def formatar_decimal(valor):
    if valor is None:
        return "Não informado"
    return str(valor).replace(".", ",")


def formatar_valor_monetario(valor):
    return (
        f"{valor:,.2f}"
        .replace(",", "_")
        .replace(".", ",")
        .replace("_", ".")
    )


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


def _desenhar_logo(pdf, configuracao, largura, topo):
    if not configuracao.logo:
        return
    try:
        caminho = Path(configuracao.logo.path)
        if not caminho.is_file():
            return
        pdf.drawImage(
            ImageReader(str(caminho)),
            largura - MARGEM_HORIZONTAL - LARGURA_MAXIMA_LOGO,
            topo - ALTURA_MAXIMA_LOGO,
            width=LARGURA_MAXIMA_LOGO,
            height=ALTURA_MAXIMA_LOGO,
            preserveAspectRatio=True,
            anchor="ne",
            mask="auto",
        )
    except Exception:
        # Arquivos ausentes ou corrompidos não podem impedir a emissão.
        return


def _desenhar_linhas(
    pdf,
    linhas,
    x,
    y,
    *,
    fonte=FONTE_REGULAR,
    tamanho=8,
    cor=COR_SECUNDARIA,
    entrelinha=10,
):
    pdf.setFont(fonte, tamanho)
    pdf.setFillColor(cor)
    for linha in linhas:
        if linha:
            pdf.drawString(x, y, linha)
        y -= entrelinha
    return y


def desenhar_cabecalho(pdf, fatura, configuracao, largura, topo):
    _desenhar_logo(pdf, configuracao, largura, topo)
    largura_texto = (
        largura
        - (2 * MARGEM_HORIZONTAL)
        - LARGURA_MAXIMA_LOGO
        - ESPACO_ENTRE_LOGO_E_CABECALHO
    )

    nome = configuracao.nome or "CONTROLCOND"
    tamanho_nome = 20
    while (
        tamanho_nome > 11
        and pdf.stringWidth(
            nome,
            FONTE_DESTAQUE,
            tamanho_nome,
        ) > largura_texto
    ):
        tamanho_nome -= 1

    linhas_nome = _quebrar_texto(
        pdf,
        nome,
        largura_texto,
        FONTE_DESTAQUE,
        tamanho_nome,
    )
    y = _desenhar_linhas(
        pdf,
        linhas_nome,
        MARGEM_HORIZONTAL,
        topo - tamanho_nome,
        fonte=FONTE_DESTAQUE,
        tamanho=tamanho_nome,
        cor=COR_PRIMARIA,
        entrelinha=tamanho_nome + 2,
    )

    dados_institucionais = [
        f"CNPJ: {configuracao.cnpj}" if configuracao.cnpj else "",
        _juntar_partes(configuracao.endereco, configuracao.cep),
        _juntar_partes(
            configuracao.cidade,
            configuracao.estado,
            separador=" - ",
        ),
        _juntar_partes(configuracao.telefone, configuracao.email),
    ]
    for dado in dados_institucionais:
        if not dado:
            continue
        linhas = _quebrar_texto(
            pdf,
            dado,
            largura_texto,
            FONTE_REGULAR,
            8,
        )
        y = _desenhar_linhas(
            pdf,
            linhas,
            MARGEM_HORIZONTAL,
            y - 1,
        )

    base = topo - ALTURA_CABECALHO
    pdf.setStrokeColor(COR_BORDA)
    pdf.setLineWidth(0.8)
    pdf.line(
        MARGEM_HORIZONTAL,
        base,
        largura - MARGEM_HORIZONTAL,
        base,
    )
    return base - ESPACO_SECAO


def desenhar_titulo_fatura(pdf, fatura, largura, y):
    pdf.setFillColor(COR_TEXTO)
    pdf.setFont(FONTE_DESTAQUE, 22)
    pdf.drawString(MARGEM_HORIZONTAL, y, "Fatura de consumo")

    pdf.setFillColor(COR_SECUNDARIA)
    pdf.setFont(FONTE_REGULAR, 9)
    pdf.drawRightString(
        largura - MARGEM_HORIZONTAL,
        y + 3,
        f"Fatura nº {fatura.id:06d}",
    )
    return y - 28


def _desenhar_campo_resumo(pdf, rotulo, valor, x, y):
    pdf.setFillColor(COR_SECUNDARIA)
    pdf.setFont(FONTE_REGULAR, 7.5)
    pdf.drawString(x, y, rotulo.upper())
    pdf.setFillColor(COR_TEXTO)
    pdf.setFont(FONTE_DESTAQUE, 10)
    pdf.drawString(x, y - 16, str(valor))


def desenhar_dados_apartamento(pdf, fatura, largura, y):
    largura_util = largura - (2 * MARGEM_HORIZONTAL)
    base = y - ALTURA_DADOS_FATURA

    pdf.setFillColor(COR_FUNDO_SUAVE)
    pdf.setStrokeColor(COR_BORDA)
    pdf.roundRect(
        MARGEM_HORIZONTAL,
        base,
        largura_util,
        ALTURA_DADOS_FATURA,
        RAIO_CARD,
        stroke=1,
        fill=1,
    )

    campos = (
        ("Apartamento", fatura.apartamento_numero_emissao or "Não informado"),
        ("Bloco", fatura.apartamento_bloco_emissao or "Não informado"),
        ("Referência", f"{fatura.mes:02d}/{fatura.ano}"),
        ("Emissão", fatura.data_emissao.strftime("%d/%m/%Y")),
        ("Status", fatura.get_status_display()),
    )
    larguras = (0.23, 0.16, 0.19, 0.21, 0.21)
    x = MARGEM_HORIZONTAL + 14
    for (rotulo, valor), proporcao in zip(campos, larguras, strict=True):
        _desenhar_campo_resumo(pdf, rotulo, valor, x, y - 24)
        x += largura_util * proporcao

    return base - ESPACO_SECAO


def _desenhar_linha_valor(pdf, rotulo, valor, x, y, largura):
    pdf.setFillColor(COR_SECUNDARIA)
    pdf.setFont(FONTE_REGULAR, 8)
    pdf.drawString(x, y, rotulo)
    pdf.setFillColor(COR_TEXTO)
    pdf.setFont(FONTE_DESTAQUE, 10)
    pdf.drawRightString(x + largura, y, valor)


def _desenhar_card_consumo(
    pdf,
    titulo,
    leitura_anterior,
    leitura_atual,
    consumo,
    valor,
    x,
    topo,
    largura,
):
    base = topo - ALTURA_CARD_CONSUMO
    pdf.setFillColor(colors.white)
    pdf.setStrokeColor(COR_BORDA)
    pdf.roundRect(
        x,
        base,
        largura,
        ALTURA_CARD_CONSUMO,
        RAIO_CARD,
        stroke=1,
        fill=1,
    )

    pdf.setFillColor(COR_PRIMARIA)
    pdf.setFont(FONTE_DESTAQUE, 13)
    pdf.drawString(x + 14, topo - 24, titulo)

    largura_linha = largura - 28
    _desenhar_linha_valor(
        pdf,
        "Leitura anterior",
        formatar_decimal(leitura_anterior),
        x + 14,
        topo - 50,
        largura_linha,
    )
    _desenhar_linha_valor(
        pdf,
        "Leitura atual",
        formatar_decimal(leitura_atual),
        x + 14,
        topo - 70,
        largura_linha,
    )

    pdf.setStrokeColor(COR_BORDA)
    pdf.line(x + 14, topo - 84, x + largura - 14, topo - 84)

    pdf.setFillColor(COR_SECUNDARIA)
    pdf.setFont(FONTE_REGULAR, 8)
    pdf.drawString(x + 14, topo - 104, "CONSUMO")
    pdf.drawRightString(x + largura - 14, topo - 104, "VALOR")

    pdf.setFillColor(COR_TEXTO)
    pdf.setFont(FONTE_DESTAQUE, 14)
    pdf.drawString(
        x + 14,
        topo - 126,
        f"{formatar_decimal(consumo)} m³",
    )
    pdf.setFillColor(COR_PRIMARIA)
    pdf.drawRightString(
        x + largura - 14,
        topo - 126,
        f"R$ {formatar_valor_monetario(valor)}",
    )


def desenhar_consumos(pdf, fatura, leituras, largura, y):
    largura_util = largura - (2 * MARGEM_HORIZONTAL)
    espaco = 14
    largura_card = (largura_util - espaco) / 2

    _desenhar_card_consumo(
        pdf,
        "Água e esgoto",
        leituras["agua_anterior"],
        leituras["agua_atual"],
        fatura.consumo_agua,
        fatura.valor_agua,
        MARGEM_HORIZONTAL,
        y,
        largura_card,
    )
    _desenhar_card_consumo(
        pdf,
        "Gás",
        leituras["gas_anterior"],
        leituras["gas_atual"],
        fatura.consumo_gas,
        fatura.valor_gas,
        MARGEM_HORIZONTAL + largura_card + espaco,
        y,
        largura_card,
    )
    return y - ALTURA_CARD_CONSUMO - ESPACO_SECAO


def desenhar_composicao_financeira(pdf, fatura, largura, y):
    largura_util = largura - (2 * MARGEM_HORIZONTAL)
    base = y - ALTURA_COMPOSICAO
    pdf.setFillColor(COR_FUNDO_SUAVE)
    pdf.setStrokeColor(COR_BORDA)
    pdf.roundRect(
        MARGEM_HORIZONTAL,
        base,
        largura_util,
        ALTURA_COMPOSICAO,
        RAIO_CARD,
        stroke=1,
        fill=1,
    )

    coluna_esquerda = (
        ("Água e esgoto", f"R$ {formatar_valor_monetario(fatura.valor_agua)}"),
        ("Gás", f"R$ {formatar_valor_monetario(fatura.valor_gas)}"),
        ("Aluguel", f"R$ {formatar_valor_monetario(fatura.valor_aluguel)}"),
        (
            "Condomínio",
            f"R$ {formatar_valor_monetario(fatura.valor_condominio)}",
        ),
        ("IPTU", f"R$ {formatar_valor_monetario(fatura.valor_iptu)}"),
    )
    coluna_direita = [
        ("Subtotal", f"R$ {formatar_valor_monetario(fatura.subtotal)}"),
    ]
    if fatura.desconto:
        coluna_direita.append(
            (
                "Desconto",
                f"- R$ {formatar_valor_monetario(fatura.desconto)}",
            )
        )
    if fatura.valor_outros:
        coluna_direita.append(
            (
                f"Outros — {fatura.observacao_outros[:45]}",
                f"R$ {formatar_valor_monetario(fatura.valor_outros)}",
            )
        )

    largura_coluna = (largura_util - 42) / 2
    for indice, (rotulo, valor) in enumerate(coluna_esquerda):
        _desenhar_linha_valor(
            pdf,
            rotulo,
            valor,
            MARGEM_HORIZONTAL + 14,
            y - 22 - (indice * 20),
            largura_coluna,
        )
    for indice, (rotulo, valor) in enumerate(coluna_direita):
        _desenhar_linha_valor(
            pdf,
            rotulo,
            valor,
            MARGEM_HORIZONTAL + largura_coluna + 28,
            y - 22 - (indice * 20),
            largura_coluna,
        )
    return base - ESPACO_SECAO


def desenhar_total(pdf, fatura, largura, y):
    largura_util = largura - (2 * MARGEM_HORIZONTAL)
    base = y - ALTURA_TOTAL
    pdf.setFillColor(COR_TOTAL)
    pdf.setStrokeColor(COR_PRIMARIA)
    pdf.roundRect(
        MARGEM_HORIZONTAL,
        base,
        largura_util,
        ALTURA_TOTAL,
        RAIO_CARD,
        stroke=1,
        fill=1,
    )
    pdf.setFillColor(COR_PRIMARIA)
    pdf.setFont(FONTE_DESTAQUE, 11)
    pdf.drawString(
        MARGEM_HORIZONTAL + 16,
        y - 28,
        "TOTAL NORMAL",
    )
    pdf.setFont(FONTE_DESTAQUE, 20)
    pdf.drawRightString(
        largura - MARGEM_HORIZONTAL - 16,
        y - 34,
        f"R$ {formatar_valor_monetario(fatura.valor_total)}",
    )
    linha_y = y - 58
    if fatura.valor_bonificacao:
        data_limite = fatura.data_limite_bonificacao.strftime("%d/%m/%Y")
        pdf.setFont(FONTE_REGULAR, 8)
        pdf.drawString(
            MARGEM_HORIZONTAL + 16,
            linha_y,
            f"Bonificação para pagamento até {data_limite}",
        )
        pdf.setFont(FONTE_DESTAQUE, 10)
        pdf.drawRightString(
            largura - MARGEM_HORIZONTAL - 16,
            linha_y,
            (
                f"Valor até {data_limite}: R$ "
                f"{formatar_valor_monetario(fatura.valor_com_bonificacao)}"
            ),
        )
        linha_y -= 18
    if fatura.status == fatura.Status.PAGA and fatura.data_pagamento:
        pdf.setFont(FONTE_REGULAR, 8)
        texto = (
            f"Pago em {fatura.data_pagamento.strftime('%d/%m/%Y')} · "
            f"Bonificação aplicada: "
            f"{'sim' if fatura.bonificacao_aplicada else 'não'}"
        )
        pdf.drawString(MARGEM_HORIZONTAL + 16, linha_y, texto)
        pdf.setFont(FONTE_DESTAQUE, 10)
        pdf.drawRightString(
            largura - MARGEM_HORIZONTAL - 16,
            linha_y,
            f"Valor pago: R$ {formatar_valor_monetario(fatura.valor_pago)}",
        )
    return base - ESPACO_SECAO


def desenhar_observacoes(pdf, configuracao, largura, altura, y):
    if not configuracao.observacoes_padrao:
        return y

    largura_texto = largura - (2 * MARGEM_HORIZONTAL)
    linhas = _quebrar_texto(
        pdf,
        configuracao.observacoes_padrao,
        largura_texto,
        FONTE_REGULAR,
        8,
    )
    altura_necessaria = 23 + (len(linhas) * 11)
    limite_rodape = MARGEM_INFERIOR + ALTURA_RODAPE

    if y - altura_necessaria < limite_rodape:
        pdf.showPage()
        y = altura - MARGEM_SUPERIOR

    pdf.setFillColor(COR_SECUNDARIA)
    pdf.setFont(FONTE_DESTAQUE, 8)
    pdf.drawString(MARGEM_HORIZONTAL, y, "OBSERVAÇÕES")
    y -= 15
    return _desenhar_linhas(
        pdf,
        linhas,
        MARGEM_HORIZONTAL,
        y,
        tamanho=8,
        entrelinha=11,
    )


def desenhar_rodape(pdf, configuracao, largura):
    linha_y = MARGEM_INFERIOR + ALTURA_RODAPE
    pdf.setStrokeColor(COR_BORDA)
    pdf.setLineWidth(0.7)
    pdf.line(
        MARGEM_HORIZONTAL,
        linha_y,
        largura - MARGEM_HORIZONTAL,
        linha_y,
    )

    linhas = []
    if configuracao.texto_rodape:
        linhas.extend(
            _quebrar_texto(
                pdf,
                configuracao.texto_rodape,
                largura - (2 * MARGEM_HORIZONTAL),
                FONTE_REGULAR,
                7,
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

    _desenhar_linhas(
        pdf,
        linhas[:3],
        MARGEM_HORIZONTAL,
        linha_y - 15,
        tamanho=7,
        cor=COR_SECUNDARIA,
        entrelinha=10,
    )


def gerar_pdf_fatura(fatura, destino, configuracao=None):
    configuracao = configuracao or obter_configuracao()
    pdf = canvas.Canvas(destino, pagesize=A4)
    largura, altura = A4

    pdf.setTitle(
        f"Fatura {fatura.mes:02d}-{fatura.ano} "
        f"Apartamento {fatura.apartamento_numero_emissao}"
    )

    topo = altura - MARGEM_SUPERIOR
    leituras = obter_leituras_fatura(fatura)
    y = desenhar_cabecalho(
        pdf,
        fatura,
        configuracao,
        largura,
        topo,
    )
    y = desenhar_titulo_fatura(pdf, fatura, largura, y)
    y = desenhar_dados_apartamento(pdf, fatura, largura, y)
    y = desenhar_consumos(pdf, fatura, leituras, largura, y)
    y = desenhar_composicao_financeira(pdf, fatura, largura, y)
    y = desenhar_total(pdf, fatura, largura, y)
    desenhar_observacoes(pdf, configuracao, largura, altura, y)
    desenhar_rodape(pdf, configuracao, largura)

    pdf.showPage()
    pdf.save()


def gerar_pdf_fatura_bytes(fatura, configuracao=None):
    """Gera a mesma fatura individual e devolve seu conteúdo binário."""
    destino = BytesIO()
    gerar_pdf_fatura(
        fatura=fatura,
        destino=destino,
        configuracao=configuracao,
    )
    return destino.getvalue()
