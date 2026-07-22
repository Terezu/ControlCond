from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apartamentos.models import Apartamento
from apartamentos.services import consultar_apartamento

from .models import ANO_MAXIMO, Leitura


@transaction.atomic
def cadastrar_leitura(
    apartamento,
    mes,
    ano,
    leitura_agua=None,
    leitura_gas=None,
):
    if not isinstance(apartamento, Apartamento) or apartamento.pk is None:
        raise ValueError("Apartamento inválido.")

    try:
        apartamento = (
            Apartamento.objects
            .select_for_update()
            .get(pk=apartamento.pk)
        )
    except Apartamento.DoesNotExist as exc:
        raise ValueError("Apartamento inválido.") from exc

    _validar_periodo(mes, ano)

    if leitura_agua is None and leitura_gas is None:
        raise ValueError(
            "Informe pelo menos uma leitura: água ou gás."
        )

    leitura = Leitura(
        apartamento=apartamento,
        mes=mes,
        ano=ano,
        leitura_agua=leitura_agua,
        leitura_gas=leitura_gas,
    )
    _validar_leitura(leitura)

    if Leitura.objects.filter(
        apartamento=apartamento,
        mes=leitura.mes,
        ano=leitura.ano,
    ).exists():
        raise ValueError(
            "Já existe uma leitura para este apartamento "
            "no mês e ano informados."
        )

    try:
        # O savepoint permite converter também uma colisão concorrente em
        # erro de domínio sem deixar a transação externa inutilizável.
        with transaction.atomic():
            leitura.save(force_insert=True)
    except IntegrityError as exc:
        if Leitura.objects.filter(
            apartamento=apartamento,
            mes=leitura.mes,
            ano=leitura.ano,
        ).exists():
            raise ValueError(
                "Já existe uma leitura para este apartamento "
                "no mês e ano informados."
            ) from exc
        raise ValueError(
            "Os dados da leitura violam uma regra de integridade."
        ) from exc
    return leitura


def consultar_leitura(leitura_id):
    try:
        return Leitura.objects.select_related("apartamento").get(pk=leitura_id)
    except Leitura.DoesNotExist as exc:
        raise ValueError("Leitura não encontrada.") from exc


@transaction.atomic
def editar_leitura(leitura_id, mes, ano, leitura_agua=None, leitura_gas=None):
    leitura = _consultar_leitura_para_atualizacao(leitura_id)
    _validar_periodo(mes, ano)
    leitura.mes = mes
    leitura.ano = ano
    leitura.leitura_agua = leitura_agua
    leitura.leitura_gas = leitura_gas
    _validar_leitura(leitura)

    if Leitura.objects.filter(
        apartamento=leitura.apartamento,
        mes=leitura.mes,
        ano=leitura.ano,
    ).exclude(pk=leitura.pk).exists():
        raise ValueError(
            "Já existe uma leitura para este apartamento "
            "no mês e ano informados."
        )

    try:
        with transaction.atomic():
            leitura.save(
                update_fields=["mes", "ano", "leitura_agua", "leitura_gas"]
            )
    except IntegrityError as exc:
        if Leitura.objects.filter(
            apartamento=leitura.apartamento,
            mes=leitura.mes,
            ano=leitura.ano,
        ).exclude(pk=leitura.pk).exists():
            raise ValueError(
                "Já existe uma leitura para este apartamento "
                "no mês e ano informados."
            ) from exc
        raise ValueError(
            "Os dados da leitura violam uma regra de integridade."
        ) from exc
    return leitura


def _consultar_leitura_para_atualizacao(leitura_id):
    apartamento_id = (
        Leitura.objects
        .filter(pk=leitura_id)
        .values_list("apartamento_id", flat=True)
        .first()
    )
    if apartamento_id is None:
        raise ValueError("Leitura não encontrada.")

    try:
        apartamento = (
            Apartamento.objects
            .select_for_update()
            .get(pk=apartamento_id)
        )
    except Apartamento.DoesNotExist as exc:
        raise ValueError("Apartamento inválido.") from exc

    try:
        leitura = (
            Leitura.objects
            .select_for_update()
            .select_related("apartamento")
            .get(pk=leitura_id, apartamento_id=apartamento.id)
        )
    except Leitura.DoesNotExist as exc:
        raise ValueError("Leitura não encontrada.") from exc

    leitura.apartamento = apartamento
    return leitura


def _validar_periodo(mes, ano):
    if (
        isinstance(mes, bool)
        or not isinstance(mes, int)
        or mes < 1
        or mes > 12
    ):
        raise ValueError("O mês deve estar entre 1 e 12.")
    if (
        isinstance(ano, bool)
        or not isinstance(ano, int)
        or ano < 2000
        or ano > ANO_MAXIMO
    ):
        raise ValueError("Informe um ano válido.")


def _validar_leitura(leitura):
    try:
        leitura.full_clean(
            validate_unique=False,
            validate_constraints=False,
        )
    except ValidationError as exc:
        raise ValueError(" ".join(exc.messages)) from exc


def listar_leituras(apartamento=None):
    """
    Retorna as leituras, opcionalmente filtradas por apartamento,
    da mais recente para a mais antiga.
    """
    leituras = Leitura.objects.select_related("apartamento")
    if apartamento is not None:
        leituras = leituras.filter(apartamento=apartamento)
    return leituras.order_by("-ano", "-mes", "-id")


def obter_ultima_leitura(apartamento):
    """
    Retorna a leitura mais recente do apartamento.
    """
    return listar_leituras(apartamento).first()


def buscar_ultimas_leituras(apartamento_id, limite=12):
    if (
        isinstance(limite, bool)
        or not isinstance(limite, int)
        or limite < 0
    ):
        raise ValueError("O limite deve ser um número inteiro não negativo.")
    consultar_apartamento(apartamento_id)
    return list(
        Leitura.objects.filter(apartamento_id=apartamento_id)
        .order_by("-ano", "-mes", "-id")[:limite]
    )


@transaction.atomic
def excluir_leitura(leitura_id):
    leitura = _consultar_leitura_para_atualizacao(leitura_id)
    if leitura.faturas.exists():
        raise ValueError(
            "A leitura não pode ser excluída porque está vinculada a uma fatura."
        )
    leitura.delete()
