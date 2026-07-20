import argparse
import os


def main():
    parser = argparse.ArgumentParser(
        description="Gera em disco o PDF de uma fatura existente."
    )
    parser.add_argument("fatura_id", type=int, help="ID da fatura")
    parser.add_argument(
        "--pasta",
        help="Pasta de destino (por padrão, faturas_geradas no projeto)",
    )
    argumentos = parser.parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django

    django.setup()

    from faturas.services import gerar_pdf_fatura

    try:
        caminho = gerar_pdf_fatura(argumentos.fatura_id, argumentos.pasta)
    except ValueError as exc:
        parser.error(str(exc))
    print("PDF gerado em:", caminho)


if __name__ == "__main__":
    main()
