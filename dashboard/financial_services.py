from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import (
    Avg,
    CharField,
    Count,
    DecimalField,
    DurationField,
    ExpressionWrapper,
    F,
    Min,
    OuterRef,
    Q,
    Subquery,
    Sum,
)
from django.db.models.functions import Coalesce
from django.utils import timezone

from contratos.models import Contrato
from faturas.models import Fatura

from .services import NOMES_MESES, _percentual


ZERO = Decimal("0.00")
MESES_EVOLUCAO = 6
LIMITE_TABELAS = 5


@dataclass(frozen=True)
class ComponenteReceita:
    nome: str
    valor: Decimal
    participacao: Decimal


@dataclass(frozen=True)
class MesEvolucao:
    mes: int
    ano: int
    competencia: str
    previsto: Decimal
    recebido: Decimal
    pendente: Decimal
    inadimplencia: Decimal


@dataclass(frozen=True)
class DashboardFinanceiro:
    mes: int
    ano: int
    competencia: str
    receita_prevista: Decimal
    receita_recebida: Decimal
    valor_pendente: Decimal
    valor_vencido: Decimal
    faturas_emitidas: int
    faturas_pagas: int
    faturas_pendentes: int
    faturas_vencidas: int
    faturas_canceladas: int
    percentual_inadimplencia: Decimal
    percentual_recebimento: Decimal
    componentes: tuple
    total_bruto: Decimal
    total_descontos: Decimal
    total_liquido_previsto: Decimal
    evolucao: tuple
    apartamentos_inadimplentes: int
    fatura_vencida_mais_antiga: object
    media_dias_atraso: Decimal
    maiores_inadimplentes: tuple
    ultimos_pagamentos: tuple
    faturas_proximas_vencimento: int
    contratos_sem_cobranca: int


def _subtrair_meses(mes, ano, quantidade):
    indice = ano * 12 + mes - 1 - quantidade
    return indice % 12 + 1, indice // 12


def _queryset_filtrado(condominio, mes, ano, apartamento=None, status=""):
    queryset = Fatura.objects.filter(
        apartamento__condominio=condominio,
        mes=mes,
        ano=ano,
    )
    if apartamento is not None:
        queryset = queryset.filter(apartamento=apartamento)
    if status:
        queryset = queryset.filter(status=status)
    return queryset


def _agregar_periodo(queryset, hoje):
    pendente = Q(status=Fatura.Status.PENDENTE)
    paga = Q(status=Fatura.Status.PAGA)
    valida = Q(status__in=(Fatura.Status.PENDENTE, Fatura.Status.PAGA))
    vencida = pendente & Q(data_vencimento__lt=hoje)
    valor_recebido = Coalesce(
        "valor_final", "valor_pago", "valor_total",
        output_field=DecimalField(max_digits=10, decimal_places=2),
    )
    return queryset.aggregate(
        emitidas=Count("id"),
        pagas=Count("id", filter=paga),
        pendentes=Count("id", filter=pendente),
        vencidas=Count("id", filter=vencida),
        canceladas=Count("id", filter=Q(status=Fatura.Status.CANCELADA)),
        previsto=Sum("valor_total", filter=valida, default=ZERO),
        recebido=Sum(valor_recebido, filter=paga, default=ZERO),
        pendente=Sum("valor_total", filter=pendente, default=ZERO),
        vencido=Sum("valor_total", filter=vencida, default=ZERO),
        aluguel=Sum("valor_aluguel", filter=valida, default=ZERO),
        condominio=Sum("valor_condominio", filter=valida, default=ZERO),
        agua=Sum("valor_agua", filter=valida, default=ZERO),
        gas=Sum("valor_gas", filter=valida, default=ZERO),
        iptu=Sum("valor_iptu", filter=valida, default=ZERO),
        outros=Sum("valor_outros", filter=valida, default=ZERO),
        descontos=Sum("desconto", filter=valida, default=ZERO),
    )


def _obter_evolucao(
    condominio, mes, ano, hoje, apartamento=None, status=""
):
    inicio_mes, inicio_ano = _subtrair_meses(
        mes, ano, MESES_EVOLUCAO - 1
    )
    inicio = date(inicio_ano, inicio_mes, 1)
    fim = date(ano, mes, 28) + timedelta(days=4)
    fim = fim.replace(day=1)
    filtro_data = Q(ano__gt=inicio.year) | Q(
        ano=inicio.year, mes__gte=inicio.month
    )
    queryset = Fatura.objects.filter(
        apartamento__condominio=condominio,
    ).filter(filtro_data).filter(
        Q(ano__lt=fim.year) | Q(ano=fim.year, mes__lt=fim.month)
    )
    if apartamento is not None:
        queryset = queryset.filter(apartamento=apartamento)
    if status:
        queryset = queryset.filter(status=status)
    recebido = Coalesce(
        "valor_final", "valor_pago", "valor_total",
        output_field=DecimalField(max_digits=10, decimal_places=2),
    )
    linhas = queryset.values("ano", "mes").annotate(
        previsto=Sum(
            "valor_total",
            filter=Q(status__in=(Fatura.Status.PENDENTE, Fatura.Status.PAGA)),
            default=ZERO,
        ),
        recebido=Sum(
            recebido, filter=Q(status=Fatura.Status.PAGA), default=ZERO
        ),
        pendente=Sum(
            "valor_total", filter=Q(status=Fatura.Status.PENDENTE), default=ZERO
        ),
        total_validas=Count(
            "id", filter=Q(status__in=(Fatura.Status.PENDENTE, Fatura.Status.PAGA))
        ),
        vencidas=Count(
            "id", filter=Q(status=Fatura.Status.PENDENTE, data_vencimento__lt=hoje)
        ),
    )
    por_competencia = {(item["ano"], item["mes"]): item for item in linhas}
    evolucao = []
    for deslocamento in range(MESES_EVOLUCAO - 1, -1, -1):
        mes_item, ano_item = _subtrair_meses(mes, ano, deslocamento)
        item = por_competencia.get((ano_item, mes_item), {})
        evolucao.append(MesEvolucao(
            mes_item,
            ano_item,
            f"{NOMES_MESES[mes_item][:3]}/{str(ano_item)[-2:]}",
            item.get("previsto", ZERO),
            item.get("recebido", ZERO),
            item.get("pendente", ZERO),
            _percentual(item.get("vencidas", 0), item.get("total_validas", 0)),
        ))
    return tuple(evolucao)


def obter_dashboard_financeiro(
    condominio, mes, ano, *, apartamento=None, status="", data_referencia=None
):
    hoje = data_referencia or timezone.localdate()
    queryset = _queryset_filtrado(
        condominio, mes, ano, apartamento=apartamento, status=status
    )
    totais = _agregar_periodo(queryset, hoje)
    total_validas = totais["pagas"] + totais["pendentes"]
    percentual_recebimento = (
        _percentual(totais["recebido"], totais["previsto"])
        if totais["previsto"] else Decimal("0.0")
    )

    categorias = (
        ("Aluguel", totais["aluguel"]),
        ("Condomínio", totais["condominio"]),
        ("Água", totais["agua"]),
        ("Gás", totais["gas"]),
        ("IPTU", totais["iptu"]),
        ("Outros valores", totais["outros"]),
    )
    total_bruto = sum((valor for _, valor in categorias), ZERO)
    componentes = tuple(
        ComponenteReceita(nome, valor, _percentual(valor, total_bruto))
        for nome, valor in categorias
    )

    vencidas = queryset.filter(
        status=Fatura.Status.PENDENTE,
        data_vencimento__lt=hoje,
    )
    atraso = ExpressionWrapper(
        hoje - F("data_vencimento"), output_field=DurationField()
    )
    media_atraso = vencidas.aggregate(media=Avg(atraso))["media"]
    media_dias = Decimal(str(media_atraso.days if media_atraso else 0))

    contrato_ativo = Contrato.objects.filter(
        condominio=condominio,
        apartamento_id=OuterRef("apartamento_id"),
        data_inicio__lte=hoje,
        data_termino__gte=hoje,
        data_rescisao__isnull=True,
        rescindido_em__isnull=True,
    ).order_by("-data_inicio", "-id")
    maiores = tuple(
        vencidas.values("apartamento_id")
        .annotate(
            quantidade=Count("id"),
            valor=Sum("valor_total", default=ZERO),
            vencimento_mais_antigo=Min("data_vencimento"),
            apartamento_numero=F("apartamento__numero"),
            apartamento_bloco=F("apartamento__bloco"),
            contrato_id=Subquery(contrato_ativo.values("id")[:1]),
            responsavel=Subquery(
                contrato_ativo.values("responsavel_financeiro__nome_completo")[:1],
                output_field=CharField(),
            ),
        ).order_by("-valor", "apartamento_numero")[:LIMITE_TABELAS]
    )
    ultimos_pagamentos = tuple(
        queryset.filter(
            status=Fatura.Status.PAGA, data_pagamento__isnull=False
        ).select_related("apartamento").order_by(
            "-data_pagamento", "-id"
        )[:LIMITE_TABELAS]
    )

    proximas = queryset.filter(
        status=Fatura.Status.PENDENTE,
        data_vencimento__range=(hoje, hoje + timedelta(days=7)),
    ).count()
    cobrancas_periodo = _queryset_filtrado(
        condominio, mes, ano, apartamento=apartamento
    )
    apartamentos_faturados = cobrancas_periodo.exclude(
        status=Fatura.Status.CANCELADA
    ).values("apartamento_id")
    contratos_sem_cobranca = Contrato.objects.filter(
        condominio=condominio,
        data_inicio__lte=hoje,
        data_termino__gte=hoje,
        data_rescisao__isnull=True,
        rescindido_em__isnull=True,
    ).exclude(apartamento_id__in=apartamentos_faturados)
    if apartamento is not None:
        contratos_sem_cobranca = contratos_sem_cobranca.filter(
            apartamento=apartamento
        )

    return DashboardFinanceiro(
        mes=mes,
        ano=ano,
        competencia=f"{NOMES_MESES[mes]} de {ano}",
        receita_prevista=totais["previsto"],
        receita_recebida=totais["recebido"],
        valor_pendente=totais["pendente"],
        valor_vencido=totais["vencido"],
        faturas_emitidas=totais["emitidas"],
        faturas_pagas=totais["pagas"],
        faturas_pendentes=totais["pendentes"],
        faturas_vencidas=totais["vencidas"],
        faturas_canceladas=totais["canceladas"],
        percentual_inadimplencia=_percentual(
            totais["vencidas"], total_validas
        ),
        percentual_recebimento=percentual_recebimento,
        componentes=componentes,
        total_bruto=total_bruto,
        total_descontos=totais["descontos"],
        total_liquido_previsto=totais["previsto"],
        evolucao=_obter_evolucao(
            condominio,
            mes,
            ano,
            hoje,
            apartamento=apartamento,
            status=status,
        ),
        apartamentos_inadimplentes=vencidas.values(
            "apartamento_id"
        ).distinct().count(),
        fatura_vencida_mais_antiga=vencidas.select_related(
            "apartamento"
        ).order_by("data_vencimento", "id").first(),
        media_dias_atraso=media_dias,
        maiores_inadimplentes=maiores,
        ultimos_pagamentos=ultimos_pagamentos,
        faturas_proximas_vencimento=proximas,
        contratos_sem_cobranca=contratos_sem_cobranca.count(),
    )
