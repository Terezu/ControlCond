from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import (
    Count,
    DecimalField,
    Exists,
    OuterRef,
    Q,
    Subquery,
    Sum,
)
from django.db.models.functions import Coalesce
from django.utils import timezone

from apartamentos.models import Apartamento
from contratos.models import AuditoriaRescisaoContrato, Contrato
from faturas.models import Fatura, HistoricoFinanceiroFatura
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
class AtividadeDashboard:
    tipo: str
    descricao: str
    ocorrido_em: object
    url_name: str
    objeto_id: int


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
    faturas_vencidas: int
    faturas_canceladas: int
    receitas_previstas: Decimal
    receitas_recebidas: Decimal
    receitas_pendentes: Decimal
    receitas_vencidas: Decimal
    total_bonificacoes_concedidas: Decimal
    total_multas_arrecadadas: Decimal
    receita_liquida: Decimal
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
    contratos_ativos: int
    contratos_proximos_vencimento: int
    contratos_vencidos: int
    contratos_encerrando_breve: int
    reajustes_futuros: int | None
    apartamentos_ocupados: int
    apartamentos_disponiveis: int
    variacao_receitas_percentual: Decimal | None
    receitas_mes_anterior: Decimal
    atividades_recentes: tuple


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


def _competencia_anterior(mes, ano):
    return (12, ano - 1) if mes == 1 else (mes - 1, ano)


def _obter_atividades_recentes(condominio):
    """Monta a timeline somente com eventos persistidos no domínio."""
    atividades = []
    for contrato in Contrato.objects.filter(condominio=condominio).only(
        "id", "criado_em"
    ).order_by("-criado_em")[:LIMITE_LISTAS]:
        atividades.append(AtividadeDashboard(
            "contrato", "Contrato criado", contrato.criado_em,
            "contratos:detalhes", contrato.id,
        ))
    for rescisao in AuditoriaRescisaoContrato.objects.filter(
        condominio=condominio
    ).only("contrato_id", "criado_em").order_by("-criado_em")[:LIMITE_LISTAS]:
        atividades.append(AtividadeDashboard(
            "contrato", "Contrato encerrado", rescisao.criado_em,
            "contratos:detalhes", rescisao.contrato_id,
        ))
    for leitura in Leitura.objects.filter(
        apartamento__condominio=condominio
    ).only("id", "data_registro").order_by("-data_registro")[:LIMITE_LISTAS]:
        atividades.append(AtividadeDashboard(
            "leitura", "Leitura cadastrada", leitura.data_registro,
            "leituras:lista", leitura.id,
        ))
    for historico in HistoricoFinanceiroFatura.objects.filter(
        fatura__apartamento__condominio=condominio
    ).only("fatura_id", "acao", "criado_em").order_by(
        "-criado_em"
    )[:LIMITE_LISTAS]:
        tipo = (
            "pagamento"
            if historico.acao == historico.Acao.PAGAMENTO_CONFIRMADO
            else "fatura"
        )
        atividades.append(AtividadeDashboard(
            tipo, historico.get_acao_display(), historico.criado_em,
            "faturas:detalhes", historico.fatura_id,
        ))
    atividades.sort(key=lambda item: item.ocorrido_em, reverse=True)
    return tuple(atividades[:LIMITE_LISTAS])


def obter_resumo_dashboard(condominio, mes, ano, data_referencia=None):
    data_referencia = data_referencia or timezone.localdate()
    leituras_competencia = Q(leituras__mes=mes, leituras__ano=ano)
    faturas_competencia_apartamento = Q(
        faturas__mes=mes,
        faturas__ano=ano,
    )
    apartamentos_queryset = Apartamento.objects.filter(
        condominio=condominio
    )
    apartamentos = apartamentos_queryset.aggregate(
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

    faturas_queryset = Fatura.objects.filter(
        apartamento__condominio=condominio, mes=mes, ano=ano
    )
    pendente = Q(status=Fatura.Status.PENDENTE)
    paga = Q(status=Fatura.Status.PAGA)
    nao_cancelada = Q(
        status__in=(Fatura.Status.PENDENTE, Fatura.Status.PAGA)
    )
    vencida = Q(
        status=Fatura.Status.PENDENTE,
        data_vencimento__lt=data_referencia,
    )
    valor_recebido = Coalesce(
        "valor_final",
        "valor_pago",
        "valor_total",
        output_field=DecimalField(max_digits=10, decimal_places=2),
    )
    faturas = faturas_queryset.aggregate(
        pendentes=Count(
            "id",
            filter=pendente,
        ),
        pagas=Count(
            "id",
            filter=paga,
        ),
        vencidas=Count(
            "id",
            filter=vencida,
        ),
        canceladas=Count(
            "id",
            filter=Q(status=Fatura.Status.CANCELADA),
        ),
        faturado=Sum(
            "valor_total",
            filter=nao_cancelada,
            default=Decimal("0.00"),
        ),
        recebido=Sum(
            valor_recebido,
            filter=paga,
            default=Decimal("0.00"),
        ),
        pendente=Sum(
            "valor_total",
            filter=pendente,
            default=Decimal("0.00"),
        ),
        vencido=Sum(
            "valor_total",
            filter=vencida,
            default=Decimal("0.00"),
        ),
        cancelado=Sum(
            "valor_total",
            filter=Q(status=Fatura.Status.CANCELADA),
            default=Decimal("0.00"),
        ),
        bonificacoes=Sum(
            "valor_bonificacao_aplicada",
            filter=paga,
            default=Decimal("0.00"),
        ),
        multas=Sum(
            "valor_multa_aplicada",
            filter=paga,
            default=Decimal("0.00"),
        ),
    )
    total_nao_canceladas = faturas["pendentes"] + faturas["pagas"]

    mes_anterior, ano_anterior = _competencia_anterior(mes, ano)
    receitas_mes_anterior = Fatura.objects.filter(
        apartamento__condominio=condominio,
        mes=mes_anterior,
        ano=ano_anterior,
        status__in=(Fatura.Status.PENDENTE, Fatura.Status.PAGA),
    ).aggregate(total=Sum("valor_total", default=Decimal("0.00")))["total"]
    variacao_receitas = None
    if receitas_mes_anterior:
        variacao_receitas = (
            (faturas["faturado"] - receitas_mes_anterior)
            * Decimal("100") / receitas_mes_anterior
        ).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    limite_proximo = data_referencia + timedelta(days=45)
    limite_breve = data_referencia + timedelta(days=90)
    sem_rescisao = Q(data_rescisao__isnull=True, rescindido_em__isnull=True)
    contratos = Contrato.objects.filter(condominio=condominio).aggregate(
        ativos=Count("id", filter=sem_rescisao & Q(
            data_inicio__lte=data_referencia, data_termino__gte=data_referencia,
        )),
        proximos=Count("id", filter=sem_rescisao & Q(
            data_inicio__lte=data_referencia,
            data_termino__range=(data_referencia, limite_proximo),
        )),
        vencidos=Count(
            "id", filter=sem_rescisao & Q(data_termino__lt=data_referencia)
        ),
        encerrando=Count("id", filter=sem_rescisao & Q(
            data_inicio__lte=data_referencia,
            data_termino__range=(data_referencia, limite_breve),
        )),
        ocupados=Count("apartamento_id", distinct=True, filter=sem_rescisao & Q(
            data_inicio__lte=data_referencia, data_termino__gte=data_referencia,
        )),
    )

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
        apartamentos_queryset
        .annotate(tem_leitura=Exists(leitura_periodo))
        .filter(tem_leitura=False)
        .order_by("bloco", "numero", "id")
    )
    sem_fatura = (
        apartamentos_queryset
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
            apartamento__condominio=condominio,
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
        faturas_vencidas=faturas["vencidas"],
        faturas_canceladas=faturas["canceladas"],
        receitas_previstas=faturas["faturado"],
        receitas_recebidas=faturas["recebido"],
        receitas_pendentes=faturas["pendente"],
        receitas_vencidas=faturas["vencido"],
        total_bonificacoes_concedidas=faturas["bonificacoes"],
        total_multas_arrecadadas=faturas["multas"],
        receita_liquida=faturas["recebido"],
        valor_faturado=faturas["faturado"],
        valor_recebido=faturas["recebido"],
        valor_pendente=faturas["pendente"],
        valor_cancelado=faturas["cancelado"],
        taxa_pagamento=_percentual(
            faturas["pagas"],
            total_nao_canceladas,
        ),
        taxa_inadimplencia=_percentual(
            faturas["vencidas"],
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
        contratos_ativos=contratos["ativos"],
        contratos_proximos_vencimento=contratos["proximos"],
        contratos_vencidos=contratos["vencidos"],
        contratos_encerrando_breve=contratos["encerrando"],
        # Ainda não existe entidade de reajuste no domínio.
        reajustes_futuros=None,
        apartamentos_ocupados=contratos["ocupados"],
        apartamentos_disponiveis=max(
            total_apartamentos - contratos["ocupados"], 0
        ),
        variacao_receitas_percentual=variacao_receitas,
        receitas_mes_anterior=receitas_mes_anterior,
        atividades_recentes=_obter_atividades_recentes(condominio),
    )
