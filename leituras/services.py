from django.db import IntegrityError

from apartamentos.models import Apartamento

from .models import Leitura


def cadastrar_leitura(
    apartamento,
    mes,
    ano,
    leitura_agua=None,
    leitura_gas=None,
):
    if not isinstance(apartamento, Apartamento):
        raise ValueError("Apartamento inválido.")

    if mes < 1 or mes > 12:
        raise ValueError("O mês deve estar entre 1 e 12.")

    if leitura_agua is None and leitura_gas is None:
        raise ValueError(
            "Informe pelo menos uma leitura: água ou gás."
        )

    try:
        return Leitura.objects.create(
            apartamento=apartamento,
            mes=mes,
            ano=ano,
            leitura_agua=leitura_agua,
            leitura_gas=leitura_gas,
        )
    except IntegrityError as exc:
        raise ValueError(
            "Já existe uma leitura para este apartamento "
            "no mês e ano informados."
        ) from exc


def consultar_leitura(leitura_id):
    try:
        return Leitura.objects.select_related("apartamento").get(pk=leitura_id)
    except Leitura.DoesNotExist as exc:
        raise ValueError("Leitura não encontrada.") from exc


def editar_leitura(leitura_id, mes, ano, leitura_agua=None, leitura_gas=None):
    leitura = consultar_leitura(leitura_id)
    leitura.mes = mes
    leitura.ano = ano
    leitura.leitura_agua = leitura_agua
    leitura.leitura_gas = leitura_gas
    leitura.save(update_fields=["mes", "ano", "leitura_agua", "leitura_gas"])
    return leitura


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
    leitura.delete()
