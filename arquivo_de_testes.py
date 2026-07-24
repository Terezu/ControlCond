import argparse
import os
from io import BytesIO


def main():
    parser = argparse.ArgumentParser(
        description="Valida em memória o PDF de uma fatura existente."
    )
    parser.add_argument("fatura_id", type=int, help="ID da fatura")
    argumentos = parser.parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django

    django.setup()

    from faturas.pdf import gerar_pdf_fatura
    from faturas.services import consultar_fatura

    try:
        fatura = consultar_fatura(argumentos.fatura_id)
    except ValueError as exc:
        parser.error(str(exc))

    buffer = BytesIO()
    gerar_pdf_fatura(fatura=fatura, destino=buffer)
    print(f"PDF validado em memória: {buffer.tell()} bytes")


if __name__ == "__main__":
    main()
