from decimal import Decimal, InvalidOperation

from django import template


register = template.Library()


@register.filter
def moeda_br(valor):
    try:
        numero = Decimal(valor or 0)
    except (InvalidOperation, TypeError, ValueError):
        numero = Decimal("0.00")
    formatado = f"{numero:,.2f}"
    formatado = (
        formatado
        .replace(",", "_")
        .replace(".", ",")
        .replace("_", ".")
    )
    return f"R$ {formatado}"


@register.filter
def percentual(valor):
    try:
        numero = Decimal(valor or 0)
    except (InvalidOperation, TypeError, ValueError):
        numero = Decimal("0.0")
    return f"{numero:.1f}%"
