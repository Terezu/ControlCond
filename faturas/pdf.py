from pathlib import Path
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from django.conf import settings

from configuracoes.services import obter_configuracao


# Geometria geral
MARGEM_HORIZONTAL = 42
MARGEM_SUPERIOR = 24
MARGEM_INFERIOR = 28
ESPACO_SECAO = 6
RAIO_CARD = 6

# Identidade visual
LARGURA_MAXIMA_LOGO = 247.5
ALTURA_MAXIMA_LOGO = 90
ESPACO_ENTRE_LOGO_E_CABECALHO = 16

# Paleta e tipografia
COR_PRIMARIA = colors.HexColor("#1F4E5F")
COR_TEXTO = colors.HexColor("#263238")
COR_SECUNDARIA = colors.HexColor("#64748B")
COR_BORDA = colors.HexColor("#D9E2E8")
COR_FUNDO_SUAVE = colors.HexColor("#F5F8FA")
COR_TOTAL = colors.HexColor("#E8F1F4")
FONTE_REGULAR = "Helvetica"
FONTE_DESTAQUE = "Helvetica-Bold"

# Hierarquia financeira
TAMANHO_ROTULO_FINANCEIRO = 9
TAMANHO_VALOR_FINANCEIRO = 11
FONTE_ROTULO_FINANCEIRO = FONTE_REGULAR
FONTE_VALOR_FINANCEIRO = FONTE_DESTAQUE
ENTRELINHA_FINANCEIRA = 21
ESPACO_ANTES_VALOR_FINANCEIRO = 10

# Alturas dos blocos
ALTURA_CABECALHO = 96
ALTURA_DADOS_FATURA = 54
ALTURA_CARD_CONSUMO = 112
ALTURA_COMPOSICAO = 104
ALTURA_TOTAL = 88
ALTURA_TOTAL_PAGO = 134
ALTURA_TOTAL_PAGO_COM_BONIFICACAO = 158
ALTURA_RODAPE = 44


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
    caminho = None
    if configuracao.logo:
        try:
            caminho = Path(configuracao.logo.path)
        except (AttributeError, NotImplementedError, ValueError):
            caminho = None
    else:
        caminho_padrao = Path(settings.BASE_DIR) / "Logo.png"
        if caminho_padrao.is_file():
            caminho = caminho_padrao
    if caminho is None:
        return
    try:
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
        _juntar_partes(
            configuracao.endereco,
            configuracao.numero,
            configuracao.complemento,
        ),
        _juntar_partes(configuracao.bairro, configuracao.cep),
        _juntar_partes(
            configuracao.cidade,
            configuracao.estado,
            separador=" - ",
        ),
        _juntar_partes(
            configuracao.telefone,
            configuracao.celular,
            configuracao.email,
        ),
        configuracao.mensagem_cabecalho,
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
        ("Vencimento", fatura.data_vencimento.strftime("%d/%m/%Y")),
        ("Status", fatura.get_status_display()),
    )
    larguras = (0.20, 0.13, 0.16, 0.17, 0.18, 0.16)
    x = MARGEM_HORIZONTAL + 14
    for (rotulo, valor), proporcao in zip(campos, larguras, strict=True):
        _desenhar_campo_resumo(pdf, rotulo, valor, x, y - 21)
        x += largura_util * proporcao

    return base - ESPACO_SECAO


def _ajustar_texto_em_largura(pdf, texto, largura, fonte, tamanho):
    """Mantém rótulos longos dentro da área reservada à descrição."""
    texto = str(texto)
    if pdf.stringWidth(texto, fonte, tamanho) <= largura:
        return texto

    sufixo = "..."
    largura_sufixo = pdf.stringWidth(sufixo, fonte, tamanho)
    while (
        texto
        and pdf.stringWidth(texto, fonte, tamanho) + largura_sufixo > largura
    ):
        texto = texto[:-1].rstrip()
    return f"{texto}{sufixo}" if texto else sufixo


def _desenhar_linha_valor(
    pdf,
    rotulo,
    valor,
    x,
    y,
    largura,
    *,
    fonte_rotulo=FONTE_ROTULO_FINANCEIRO,
    tamanho_rotulo=TAMANHO_ROTULO_FINANCEIRO,
    fonte_valor=FONTE_VALOR_FINANCEIRO,
):
    largura_valor = pdf.stringWidth(
        valor,
        fonte_valor,
        TAMANHO_VALOR_FINANCEIRO,
    )
    largura_rotulo = max(
        0,
        largura - largura_valor - ESPACO_ANTES_VALOR_FINANCEIRO,
    )
    rotulo = _ajustar_texto_em_largura(
        pdf,
        rotulo,
        largura_rotulo,
        fonte_rotulo,
        tamanho_rotulo,
    )

    pdf.setFillColor(COR_SECUNDARIA)
    pdf.setFont(fonte_rotulo, tamanho_rotulo)
    pdf.drawString(x, y, rotulo)
    pdf.setFillColor(COR_TEXTO)
    pdf.setFont(fonte_valor, TAMANHO_VALOR_FINANCEIRO)
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
        topo - 44,
        largura_linha,
    )
    _desenhar_linha_valor(
        pdf,
        "Leitura atual",
        formatar_decimal(leitura_atual),
        x + 14,
        topo - 62,
        largura_linha,
    )

    pdf.setStrokeColor(COR_BORDA)
    pdf.line(x + 14, topo - 69, x + largura - 14, topo - 69)

    pdf.setFillColor(COR_SECUNDARIA)
    pdf.setFont(FONTE_REGULAR, 8)
    pdf.drawString(x + 14, topo - 83, "CONSUMO")
    pdf.drawRightString(x + largura - 14, topo - 83, "VALOR")

    pdf.setFillColor(COR_TEXTO)
    pdf.setFont(FONTE_DESTAQUE, 12)
    pdf.drawString(
        x + 14,
        topo - 102,
        f"{formatar_decimal(consumo)} m³",
    )
    pdf.setFillColor(COR_PRIMARIA)
    pdf.setFont(FONTE_VALOR_FINANCEIRO, TAMANHO_VALOR_FINANCEIRO)
    pdf.drawRightString(
        x + largura - 14,
        topo - 102,
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
        (
            f"Gás ({fatura.consumo_gas} m³ × R$ "
            f"{formatar_valor_monetario(fatura.valor_m3_gas_emissao)}/m³)",
            f"R$ {formatar_valor_monetario(fatura.valor_gas)}",
        ),
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

    largura_coluna = (largura_util - 56) / 2
    x_esquerda = MARGEM_HORIZONTAL + 14
    x_direita = MARGEM_HORIZONTAL + largura_coluna + 42

    separador_x = MARGEM_HORIZONTAL + (largura_util / 2)
    pdf.setStrokeColor(COR_BORDA)
    pdf.setLineWidth(0.6)
    pdf.line(separador_x, base + 14, separador_x, y - 14)

    for indice, (rotulo, valor) in enumerate(coluna_esquerda):
        _desenhar_linha_valor(
            pdf,
            rotulo,
            valor,
            x_esquerda,
            y - 18 - (indice * 19),
            largura_coluna,
            fonte_rotulo=FONTE_DESTAQUE,
            fonte_valor=FONTE_REGULAR,
        )
    for indice, (rotulo, valor) in enumerate(coluna_direita):
        _desenhar_linha_valor(
            pdf,
            rotulo,
            valor,
            x_direita,
            y - 18 - (indice * 19),
            largura_coluna,
            fonte_rotulo=FONTE_DESTAQUE,
            tamanho_rotulo=(
                10 if indice == 0 else TAMANHO_ROTULO_FINANCEIRO
            ),
            fonte_valor=FONTE_REGULAR,
        )
    return base - ESPACO_SECAO


def _desenhar_detalhes_pagamento(pdf, fatura, largura, y):
    x_inicial = MARGEM_HORIZONTAL + 16
    x_final = largura - MARGEM_HORIZONTAL - 16
    largura_util = x_final - x_inicial
    data_pagamento = fatura.data_pagamento.strftime("%d/%m/%Y")
    forma_pagamento = (
        fatura.get_forma_pagamento_display()
        if fatura.forma_pagamento
        else "Não informada"
    )
    dias_atraso = fatura.dias_em_atraso or 0
    texto_atraso = (
        f"{dias_atraso} dia{'s' if dias_atraso != 1 else ''} em atraso"
        if dias_atraso
        else "Sem atraso"
    )

    pdf.setFillColor(COR_SECUNDARIA)
    pdf.setFont(FONTE_REGULAR, 8)
    pdf.drawString(
        x_inicial,
        y,
        f"Pagamento: {data_pagamento} · {texto_atraso}",
    )
    pdf.drawRightString(
        x_final,
        y,
        f"Forma: {forma_pagamento}",
    )

    largura_coluna = largura_util / 3
    itens = (
        (
            "Valor original",
            f"R$ {formatar_valor_monetario(fatura.valor_original)}",
        ),
        (
            "Multa",
            f"R$ {formatar_valor_monetario(fatura.valor_multa_aplicada)}",
        ),
        (
            "Juros",
            f"R$ {formatar_valor_monetario(fatura.valor_juros_aplicados)}",
        ),
    )
    for indice, (rotulo, valor) in enumerate(itens):
        x = x_inicial + (indice * largura_coluna)
        pdf.setFillColor(COR_SECUNDARIA)
        pdf.setFont(FONTE_DESTAQUE, 7.5)
        pdf.drawString(x, y - 22, rotulo.upper())
        pdf.setFillColor(COR_TEXTO)
        pdf.setFont(FONTE_REGULAR, 9.5)
        pdf.drawString(x, y - 36, valor)

    valor_efetivo = (
        fatura.valor_final
        if fatura.valor_final is not None
        else (
            fatura.valor_pago
            if fatura.valor_pago is not None
            else fatura.valor_total
        )
    )
    pdf.setStrokeColor(COR_BORDA)
    pdf.setLineWidth(0.6)
    pdf.line(x_inicial, y - 48, x_final, y - 48)
    pdf.setFillColor(COR_PRIMARIA)
    pdf.setFont(FONTE_DESTAQUE, 9)
    pdf.drawString(x_inicial, y - 65, "VALOR EFETIVAMENTE PAGO")
    pdf.setFont(FONTE_REGULAR, 12)
    pdf.drawRightString(
        x_final,
        y - 65,
        f"R$ {formatar_valor_monetario(valor_efetivo)}",
    )


def _desenhar_texto_com_rotulo(
    pdf,
    rotulo,
    valor,
    x,
    y,
    *,
    tamanho,
    alinhado_a_direita=False,
):
    largura_rotulo = pdf.stringWidth(rotulo, FONTE_DESTAQUE, tamanho)
    largura_valor = pdf.stringWidth(valor, FONTE_REGULAR, tamanho)
    inicio = x - largura_rotulo - largura_valor if alinhado_a_direita else x

    pdf.setFont(FONTE_DESTAQUE, tamanho)
    pdf.drawString(inicio, y, rotulo)
    pdf.setFont(FONTE_REGULAR, tamanho)
    pdf.drawString(inicio + largura_rotulo, y, valor)


def desenhar_total(pdf, fatura, largura, y):
    largura_util = largura - (2 * MARGEM_HORIZONTAL)
    pagamento_confirmado = (
        fatura.status == fatura.Status.PAGA
        and fatura.data_pagamento is not None
    )
    if pagamento_confirmado and fatura.possui_bonificacao:
        altura = ALTURA_TOTAL_PAGO_COM_BONIFICACAO
    elif pagamento_confirmado:
        altura = ALTURA_TOTAL_PAGO
    else:
        altura = ALTURA_TOTAL
    base = y - altura
    pdf.setFillColor(COR_TOTAL)
    pdf.setStrokeColor(COR_PRIMARIA)
    pdf.roundRect(
        MARGEM_HORIZONTAL,
        base,
        largura_util,
        altura,
        RAIO_CARD,
        stroke=1,
        fill=1,
    )
    bonificacao_valida = bool(
        fatura.possui_bonificacao and fatura.data_limite_bonificacao
    )
    if bonificacao_valida:
        data_limite = fatura.data_limite_bonificacao.strftime("%d/%m/%Y")
        if (
            fatura.tipo_bonificacao_emissao
            == fatura.TipoBonificacao.PERCENTUAL
        ):
            bonus_configurado = (
                f"{formatar_decimal(fatura.percentual_bonificacao_emissao)}%"
            )
        else:
            bonus_configurado = (
                "R$ "
                f"{formatar_valor_monetario(
                    fatura.valor_bonificacao_fixa_emissao
                )}"
            )
        pdf.setFillColor(COR_PRIMARIA)
        pdf.setFont(FONTE_DESTAQUE, 10)
        pdf.drawString(
            MARGEM_HORIZONTAL + 16, y - 20, "VALOR COM BONIFICAÇÃO"
        )
        pdf.setFont(FONTE_DESTAQUE, 24)
        pdf.drawString(
            MARGEM_HORIZONTAL + 16,
            y - 46,
            f"R$ {formatar_valor_monetario(fatura.valor_com_bonificacao)}",
        )
        pdf.setFont(FONTE_DESTAQUE, 9)
        pdf.drawString(
            MARGEM_HORIZONTAL + 16,
            y - 63,
            f"Pagamento até {data_limite}",
        )
        _desenhar_texto_com_rotulo(
            pdf,
            "Valor normal após o prazo: ",
            f"R$ {formatar_valor_monetario(fatura.valor_total)}",
            largura - MARGEM_HORIZONTAL - 16,
            y - 42,
            tamanho=9.5,
            alinhado_a_direita=True,
        )
        _desenhar_texto_com_rotulo(
            pdf,
            f"Bonificação {fatura.descricao_origem_bonificacao}: ",
            bonus_configurado,
            largura - MARGEM_HORIZONTAL - 16,
            y - 61,
            tamanho=7.5,
            alinhado_a_direita=True,
        )
        linha_y = y - 86
    else:
        pdf.setFillColor(COR_PRIMARIA)
        pdf.setFont(FONTE_DESTAQUE, 11)
        pdf.drawString(MARGEM_HORIZONTAL + 16, y - 27, "TOTAL NORMAL")
        pdf.setFont(FONTE_DESTAQUE, 20)
        pdf.drawRightString(
            largura - MARGEM_HORIZONTAL - 16,
            y - 33,
            f"R$ {formatar_valor_monetario(fatura.valor_total)}",
        )
        linha_y = y - 55
    if pagamento_confirmado:
        _desenhar_detalhes_pagamento(pdf, fatura, largura, linha_y)
    return base - ESPACO_SECAO


def _desenhar_pagamento_pix(pdf, configuracao, largura, y):
    """Destaca a chave PIX sem alterar os dados configurados."""
    largura_util = largura - (2 * MARGEM_HORIZONTAL)
    pdf.setFillColor(COR_PRIMARIA)
    pdf.setFont(FONTE_DESTAQUE, 9)
    pdf.drawString(MARGEM_HORIZONTAL, y, "FORMA DE PAGAMENTO")
    pdf.setFont(FONTE_DESTAQUE, 12)
    pdf.drawString(MARGEM_HORIZONTAL, y - 15, "PIX")

    topo_box = y - 22
    altura_box = 46
    pdf.setFillColor(COR_FUNDO_SUAVE)
    pdf.setStrokeColor(COR_BORDA)
    pdf.roundRect(
        MARGEM_HORIZONTAL,
        topo_box - altura_box,
        largura_util,
        altura_box,
        RAIO_CARD,
        stroke=1,
        fill=1,
    )
    pdf.setFillColor(COR_PRIMARIA)
    pdf.setFont(FONTE_DESTAQUE, 7.5)
    pdf.drawString(
        MARGEM_HORIZONTAL + 12,
        topo_box - 14,
        "CHAVE PIX",
    )
    tamanho_chave = 15
    largura_chave = largura_util - 24
    while (
        tamanho_chave > 10
        and pdf.stringWidth(
            configuracao.pix, FONTE_DESTAQUE, tamanho_chave
        ) > largura_chave
    ):
        tamanho_chave -= 1
    pdf.setFillColor(COR_TEXTO)
    pdf.setFont(FONTE_DESTAQUE, tamanho_chave)
    pdf.drawString(MARGEM_HORIZONTAL + 12, topo_box - 34, configuracao.pix)

    dados_favorecido = _juntar_partes(
        f"Favorecido: {configuracao.favorecido_nome}"
        if configuracao.favorecido_nome
        else "",
        configuracao.favorecido_documento,
    )
    dados_bancarios = _juntar_partes(
        configuracao.banco,
        f"Agência {configuracao.agencia}" if configuracao.agencia else "",
        f"Conta {configuracao.conta}" if configuracao.conta else "",
        configuracao.tipo_conta,
    )
    linhas = [
        linha
        for texto in (
            dados_favorecido,
            dados_bancarios,
            configuracao.instrucoes_pagamento,
            (
                f"Código de barras: {configuracao.codigo_barras_padrao}"
                if configuracao.codigo_barras_padrao
                else ""
            ),
        )
        if texto
        for linha in _quebrar_texto(
            pdf, texto, largura_util, FONTE_REGULAR, 8
        )
    ]
    return _desenhar_linhas(
        pdf,
        linhas,
        MARGEM_HORIZONTAL,
        topo_box - altura_box - 12,
        tamanho=8,
        entrelinha=10,
    ) - 4


def desenhar_informacoes_complementares(pdf, configuracao, largura, altura, y):
    largura_texto = largura - (2 * MARGEM_HORIZONTAL)
    pagamento_sem_pix = _juntar_partes(
        (
            f"Favorecido: {configuracao.favorecido_nome}"
            if configuracao.favorecido_nome
            else ""
        ),
        configuracao.favorecido_documento,
        _juntar_partes(
            configuracao.banco,
            (
                f"Agência {configuracao.agencia}"
                if configuracao.agencia
                else ""
            ),
            f"Conta {configuracao.conta}" if configuracao.conta else "",
            configuracao.tipo_conta,
        ),
        configuracao.instrucoes_pagamento,
        (
            f"Código de barras: {configuracao.codigo_barras_padrao}"
            if configuracao.codigo_barras_padrao
            else ""
        ),
    )
    assinatura = _juntar_partes(
        configuracao.cidade_assinatura,
        configuracao.responsavel_emissao,
        configuracao.cargo_responsavel,
    )
    blocos = (
        ("COBRANÇA", configuracao.mensagem_cobranca_padrao),
        (
            "PAGAMENTO ANTECIPADO",
            configuracao.mensagem_pagamento_antecipado,
        ),
        ("PAGAMENTO", pagamento_sem_pix if not configuracao.pix else ""),
        ("OBSERVAÇÕES", configuracao.observacoes_padrao),
        ("INFORMAÇÕES LEGAIS", configuracao.texto_juridico),
        ("RESPONSÁVEL PELA EMISSÃO", assinatura),
    )
    limite_rodape = MARGEM_INFERIOR + ALTURA_RODAPE
    if configuracao.pix:
        y = _desenhar_pagamento_pix(pdf, configuracao, largura, y)

    # Os textos auxiliares ocupam duas colunas. Isso aproveita o espaço
    # horizontal disponível e evita que itens curtos abram uma segunda página.
    blocos_ativos = [(titulo, texto) for titulo, texto in blocos if texto]
    espaco_colunas = 16
    largura_coluna = (largura_texto - espaco_colunas) / 2
    for indice in range(0, len(blocos_ativos), 2):
        linha_blocos = blocos_ativos[indice:indice + 2]
        preparados = []
        for titulo, texto in linha_blocos:
            linhas = _quebrar_texto(
                pdf, texto, largura_coluna, FONTE_REGULAR, 7
            )
            preparados.append((titulo, linhas))

        maior_numero_linhas = max(len(linhas) for _, linhas in preparados)
        altura_linha = 17 + (maior_numero_linhas * 9)
        for coluna, (titulo, linhas) in enumerate(preparados):
            x = MARGEM_HORIZONTAL + coluna * (
                largura_coluna + espaco_colunas
            )
            pdf.setFillColor(COR_SECUNDARIA)
            pdf.setFont(FONTE_DESTAQUE, 7.5)
            pdf.drawString(x, y, titulo)
            _desenhar_linhas(
                pdf,
                linhas,
                x,
                y - 12,
                tamanho=7,
                entrelinha=9,
            )
        y -= altura_linha

    # O conteúdo configurável tem limites de campo; esta guarda mantém o
    # retorno coerente sem autorizar desenho dentro da área fixa do rodapé.
    y = max(y, limite_rodape)
    return y


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
        linhas.append(
            configuracao.mensagem_institucional_rodape
            or "Documento gerado automaticamente pelo ControlCond."
        )

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
    configuracao = configuracao or obter_configuracao(
        fatura.apartamento.condominio
    )
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
    y = desenhar_composicao_financeira(pdf, fatura, largura, y)
    y = desenhar_consumos(pdf, fatura, leituras, largura, y)
    y = desenhar_total(pdf, fatura, largura, y)
    desenhar_informacoes_complementares(
        pdf,
        configuracao,
        largura,
        altura,
        y,
    )
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
