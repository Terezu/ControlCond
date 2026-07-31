from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from .models import Contrato


def contratos_do_condominio(condominio):
    return (
        Contrato.objects.filter(condominio=condominio)
        .select_related(
            "apartamento",
            "pessoa_contratante",
            "responsavel_financeiro",
            "usuario_rescisao",
        )
    )


def contratos_para_apartamentos(condominio):
    return contratos_do_condominio(condominio).order_by(
        "-data_inicio", "-id"
    )


def classificar_contratos(condominio, hoje=None):
    hoje = hoje or timezone.localdate()
    base = contratos_do_condominio(condominio)
    ativos = base.filter(
        data_rescisao__isnull=True,
        data_inicio__lte=hoje,
        data_termino__gte=hoje,
    )
    return {
        "ativos": ativos,
        "proximos": ativos.filter(
            data_termino__lte=hoje + timedelta(days=45)
        ),
        "futuros": base.filter(
            data_rescisao__isnull=True, data_inicio__gt=hoje
        ),
        "inativos": base.filter(
            Q(data_rescisao__isnull=False) | Q(data_termino__lt=hoje)
        ),
    }


def contrato_atual_apartamento(apartamento, hoje=None):
    hoje = hoje or timezone.localdate()
    return (
        contratos_do_condominio(apartamento.condominio)
        .filter(
            apartamento=apartamento,
            data_rescisao__isnull=True,
            data_inicio__lte=hoje,
            data_termino__gte=hoje,
        )
        .first()
    )


def filtrar_contratos(
    condominio,
    *,
    busca=None,
    situacao=None,
    apartamento=None,
    inicio_de=None,
    inicio_ate=None,
    termino_de=None,
    termino_ate=None,
    proximos=False,
    encerrados=False,
    rescindidos=False,
    aba=None,
    incluir_dados_sensiveis=True,
):
    hoje = timezone.localdate()
    contratos = contratos_do_condominio(condominio)
    if busca:
        busca = busca.strip()
        filtro = (
            Q(pessoa_contratante__nome_completo__icontains=busca)
            | Q(responsavel_financeiro__nome_completo__icontains=busca)
            | Q(apartamento__numero__icontains=busca)
            | Q(apartamento__bloco__icontains=busca)
        )
        if incluir_dados_sensiveis:
            cpf = "".join(c for c in busca if c.isdigit())
            if cpf:
                filtro |= Q(pessoa_contratante__cpf__icontains=cpf)
                filtro |= Q(responsavel_financeiro__cpf__icontains=cpf)
        contratos = contratos.filter(filtro)
    if apartamento:
        contratos = contratos.filter(apartamento=apartamento)
    if inicio_de:
        contratos = contratos.filter(data_inicio__gte=inicio_de)
    if inicio_ate:
        contratos = contratos.filter(data_inicio__lte=inicio_ate)
    if termino_de:
        contratos = contratos.filter(data_termino__gte=termino_de)
    if termino_ate:
        contratos = contratos.filter(data_termino__lte=termino_ate)
    if proximos or aba == "proximos":
        contratos = contratos.filter(
            data_rescisao__isnull=True,
            data_inicio__lte=hoje,
            data_termino__range=(hoje, hoje + timedelta(days=45)),
        )
    elif encerrados:
        contratos = contratos.filter(
            data_rescisao__isnull=True, data_termino__lt=hoje
        )
    elif rescindidos:
        contratos = contratos.filter(data_rescisao__isnull=False)
    elif aba == "ativos":
        contratos = contratos.filter(
            data_rescisao__isnull=True,
            data_inicio__lte=hoje,
            data_termino__gte=hoje,
        )
    elif aba == "futuros":
        contratos = contratos.filter(
            data_rescisao__isnull=True, data_inicio__gt=hoje
        )
    elif aba == "inativos":
        contratos = contratos.filter(
            Q(data_rescisao__isnull=False) | Q(data_termino__lt=hoje)
        )
    elif situacao == Contrato.Situacao.ATIVO:
        contratos = contratos.filter(
            data_rescisao__isnull=True,
            data_inicio__lte=hoje,
            data_termino__gte=hoje,
        )
    elif situacao == Contrato.Situacao.FUTURO:
        contratos = contratos.filter(
            data_rescisao__isnull=True, data_inicio__gt=hoje
        )
    elif situacao == Contrato.Situacao.ENCERRADO:
        contratos = contratos.filter(
            data_rescisao__isnull=True, data_termino__lt=hoje
        )
    elif situacao == Contrato.Situacao.RESCINDIDO:
        contratos = contratos.filter(data_rescisao__isnull=False)
    return contratos.order_by("data_termino", "apartamento__bloco", "apartamento__numero")
