import re

from django.core.exceptions import ValidationError


def somente_digitos(valor):
    return re.sub(r"\D", "", valor or "")


def formatar_cnpj(valor):
    digitos = somente_digitos(valor)
    if len(digitos) != 14:
        return valor.strip() if isinstance(valor, str) else valor
    return (
        f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/"
        f"{digitos[8:12]}-{digitos[12:]}"
    )


def validar_cnpj(valor):
    digitos = somente_digitos(valor)
    if len(digitos) != 14 or len(set(digitos)) == 1:
        raise ValidationError("Informe um CNPJ válido.")

    numeros = [int(digito) for digito in digitos]
    for tamanho, pesos in (
        (12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]),
        (13, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]),
    ):
        resto = sum(
            numero * peso
            for numero, peso in zip(numeros[:tamanho], pesos, strict=True)
        ) % 11
        esperado = 0 if resto < 2 else 11 - resto
        if numeros[tamanho] != esperado:
            raise ValidationError("Informe um CNPJ válido.")


def formatar_cep(valor):
    digitos = somente_digitos(valor)
    if len(digitos) != 8:
        return valor.strip() if isinstance(valor, str) else valor
    return f"{digitos[:5]}-{digitos[5:]}"
