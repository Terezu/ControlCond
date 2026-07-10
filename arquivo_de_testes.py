from faturas.services import gerar_pdf_fatura


if __name__ == "__main__":
    caminho = gerar_pdf_fatura(8)
    print("PDF gerado em:", caminho)
