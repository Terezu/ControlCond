from faturas.pdf_service import gerar_pdf_fatura

caminho = gerar_pdf_fatura(8)

print("PDF gerado em:", caminho)