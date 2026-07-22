from django.db.models import Sum
from django.shortcuts import render

from apartamentos.models import Apartamento
from faturas.models import Fatura
from leituras.models import Leitura


def formatar_valor_monetario(valor):
    """
    Formata um valor no padrão monetário brasileiro.

    Exemplo:
        1234.50 -> R$ 1.234,50
    """
    valor_formatado = f"{valor:,.2f}"

    valor_formatado = (
        valor_formatado
        .replace(",", "_")
        .replace(".", ",")
        .replace("_", ".")
    )

    return f"R$ {valor_formatado}"


def dashboard(request):
    total_apartamentos = Apartamento.objects.count()
    total_leituras = Leitura.objects.count()

    faturas_pendentes = Fatura.objects.filter(
        status=Fatura.Status.PENDENTE
    )

    total_faturas_pendentes = faturas_pendentes.count()

    valor_total_pendente = (
        faturas_pendentes.aggregate(
            total=Sum("valor_total")
        )["total"]
        or 0
    )

    ultimas_faturas = (
        Fatura.objects
        .select_related("apartamento")
        .order_by("-ano", "-mes", "-id")[:5]
    )

    context = {
        "total_apartamentos": total_apartamentos,
        "total_leituras": total_leituras,
        "total_faturas_pendentes": total_faturas_pendentes,
        "valor_total_pendente_formatado": (
            formatar_valor_monetario(valor_total_pendente)
        ),
        "ultimas_faturas": ultimas_faturas,
        "cabecalhos_ultimas_faturas": [
            "Apartamento",
            "Competência",
            "Valor",
            "Status",
        ],
    }

    return render(
        request,
        "dashboard/inicio.html",
        context,
    )
