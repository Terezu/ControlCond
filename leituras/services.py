from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apartamentos.models import Apartamento
from apartamentos.services import consultar_apartamento

from .models import ANO_MAXIMO, Leitura


def cadastrar_leitura(
    apartamento,
    mes,
    ano,
    leitura_agua=None,
    leitura_gas=None,
):
    if not isinstance(apartamento, Apartamento):
        raise ValueError("Apartamento inválido.")

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
        raise ValueError(
            "Já existe uma leitura para este apartamento "
            "no mês e ano informados."
        ) from exc
    return leitura


def consultar_leitura(leitura_id):
    try:
        return Leitura.objects.select_related("apartamento").get(pk=leitura_id)
    except Leitura.DoesNotExist as exc:
        raise ValueError("Leitura não encontrada.") from exc


def editar_leitura(leitura_id, mes, ano, leitura_agua=None, leitura_gas=None):
    leitura = consultar_leitura(leitura_id)
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
        raise ValueError(
            "Já existe uma leitura para este apartamento "
            "no mês e ano informados."
        ) from exc
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


def listar_leituras(apartamento):
    """
    Retorna todas as leituras do apartamento,
    da mais recente para a mais antiga.
    """
    return (
        Leitura.objects
        .filter(apartamento=apartamento)
        .order_by("-ano", "-mes")
    )


def obter_ultima_leitura(apartamento):
    """
    Retorna a leitura mais recente do apartamento.
    """
    return listar_leituras(apartamento).first()


def buscar_ultimas_leituras(apartamento_id, limite=12):
    consultar_apartamento(apartamento_id)
    return list(
        Leitura.objects.filter(apartamento_id=apartamento_id)
        .order_by("-ano", "-mes", "-id")[:limite]
    )


def excluir_leitura(leitura_id):
    leitura = consultar_leitura(leitura_id)
    if leitura.faturas.exists():
        raise ValueError(
            "A leitura não pode ser excluída porque está vinculada a uma fatura."
        )
    leitura.delete()
