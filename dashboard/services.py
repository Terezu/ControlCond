from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import (
    Count,
    Exists,
    OuterRef,
    Q,
    Subquery,
    Sum,
)

from apartamentos.models import Apartamento
from faturas.models import Fatura
from leituras.models import Leitura


NOMES_MESES = (
    "",
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
)
LIMITE_LISTAS = 5


@dataclass(frozen=True)
class ListaResumoDashboard:
    itens: tuple
    tem_mais: bool


@dataclass(frozen=True)
class ResumoDashboard:
    mes: int
    ano: int
    competencia: str
    total_apartamentos: int
    apartamentos_com_leitura: int
    apartamentos_sem_leitura: int
    apartamentos_com_fatura: int
    apartamentos_sem_fatura: int
    faturas_pendentes: int
    faturas_pagas: int
    faturas_canceladas: int
    valor_faturado: Decimal
    valor_recebido: Decimal
    valor_pendente: Decimal
    valor_cancelado: Decimal
    taxa_pagamento: Decimal
    taxa_inadimplencia: Decimal
    cobertura_leituras: Decimal
    cobertura_faturamento: Decimal
    lista_sem_leitura: ListaResumoDashboard
    lista_sem_fatura: ListaResumoDashboard
    lista_faturas_pendentes: ListaResumoDashboard


def _percentual(parte, total):
    if not total:
        return Decimal("0.0")
    return (
        Decimal(parte) * Decimal("100") / Decimal(total)
    ).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def _limitar(queryset):
    itens = list(queryset[: LIMITE_LISTAS + 1])
    return ListaResumoDashboard(
        itens=tuple(itens[:LIMITE_LISTAS]),
        tem_mais=len(itens) > LIMITE_LISTAS,
    )


def obter_resumo_dashboard(mes, ano):
    leituras_competencia = Q(leituras__mes=mes, leituras__ano=ano)
    faturas_competencia_apartamento = Q(
        faturas__mes=mes,
        faturas__ano=ano,
    )
    apartamentos = Apartamento.objects.aggregate(
        total=Count("id", distinct=True),
        com_leitura=Count(
            "id",
            filter=leituras_competencia,
            distinct=True,
        ),
        com_fatura=Count(
            "id",
            filter=faturas_competencia_apartamento,
            distinct=True,
        ),
    )
    total_apartamentos = apartamentos["total"]
    apartamentos_com_leitura = apartamentos["com_leitura"]
    apartamentos_com_fatura = apartamentos["com_fatura"]

    faturas = Fatura.objects.filter(mes=mes, ano=ano).aggregate(
        pendentes=Count(
            "id",
            filter=Q(status=Fatura.Status.PENDENTE),
        ),
        pagas=Count(
            "id",
            filter=Q(status=Fatura.Status.PAGA),
        ),
        canceladas=Count(
            "id",
            filter=Q(status=Fatura.Status.CANCELADA),
        ),
        faturado=Sum(
            "valor_total",
            filter=Q(
                status__in=(
                    Fatura.Status.PENDENTE,
                    Fatura.Status.PAGA,
                )
            ),
            default=Decimal("0.00"),
        ),
        recebido=Sum(
            "valor_total",
            filter=Q(status=Fatura.Status.PAGA),
            default=Decimal("0.00"),
        ),
        pendente=Sum(
            "valor_total",
            filter=Q(status=Fatura.Status.PENDENTE),
            default=Decimal("0.00"),
        ),
        cancelado=Sum(
            "valor_total",
            filter=Q(status=Fatura.Status.CANCELADA),
            default=Decimal("0.00"),
        ),
    )
    total_nao_canceladas = faturas["pendentes"] + faturas["pagas"]

    leitura_periodo = Leitura.objects.filter(
        apartamento_id=OuterRef("pk"),
        mes=mes,
        ano=ano,
    )
    fatura_periodo = Fatura.objects.filter(
        apartamento_id=OuterRef("pk"),
        mes=mes,
        ano=ano,
    )
    sem_leitura = (
        Apartamento.objects
        .annotate(tem_leitura=Exists(leitura_periodo))
        .filter(tem_leitura=False)
        .order_by("bloco", "numero", "id")
    )
    sem_fatura = (
        Apartamento.objects
        .annotate(
            tem_fatura=Exists(fatura_periodo),
            leitura_competencia_id=Subquery(
                leitura_periodo.values("id")[:1]
            ),
        )
        .filter(tem_fatura=False)
        .order_by("bloco", "numero", "id")
    )
    pendentes = (
        Fatura.objects
        .filter(
            mes=mes,
            ano=ano,
            status=Fatura.Status.PENDENTE,
        )
        .select_related("apartamento")
        .order_by(
            "apartamento__bloco",
            "apartamento__numero",
            "id",
        )
    )

    return ResumoDashboard(
        mes=mes,
        ano=ano,
        competencia=f"{NOMES_MESES[mes]} de {ano}",
        total_apartamentos=total_apartamentos,
        apartamentos_com_leitura=apartamentos_com_leitura,
        apartamentos_sem_leitura=(
            total_apartamentos - apartamentos_com_leitura
        ),
        apartamentos_com_fatura=apartamentos_com_fatura,
        apartamentos_sem_fatura=(
            total_apartamentos - apartamentos_com_fatura
        ),
        faturas_pendentes=faturas["pendentes"],
        faturas_pagas=faturas["pagas"],
        faturas_canceladas=faturas["canceladas"],
        valor_faturado=faturas["faturado"],
        valor_recebido=faturas["recebido"],
        valor_pendente=faturas["pendente"],
        valor_cancelado=faturas["cancelado"],
        taxa_pagamento=_percentual(
            faturas["pagas"],
            total_nao_canceladas,
        ),
        taxa_inadimplencia=_percentual(
            faturas["pendentes"],
            total_nao_canceladas,
        ),
        cobertura_leituras=_percentual(
            apartamentos_com_leitura,
            total_apartamentos,
        ),
        cobertura_faturamento=_percentual(
            apartamentos_com_fatura,
            total_apartamentos,
        ),
        lista_sem_leitura=_limitar(sem_leitura),
        lista_sem_fatura=_limitar(sem_fatura),
        lista_faturas_pendentes=_limitar(pendentes),
    )
