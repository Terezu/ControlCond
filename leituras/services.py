from apartamentos.services import consultar_apartamento

from .models import Leitura


def cadastrar_leitura(apartamento_id, mes, ano, leitura_agua=None, leitura_gas=None):
    apartamento = consultar_apartamento(apartamento_id)
    return Leitura.objects.create(
        apartamento=apartamento,
        mes=mes,
        ano=ano,
        leitura_agua=leitura_agua,
        leitura_gas=leitura_gas,
    )


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


def listar_leituras():
    return Leitura.objects.select_related("apartamento").order_by(
        "-ano", "-mes", "-id"
    )


def buscar_ultimas_leituras(apartamento_id, limite=12):
    consultar_apartamento(apartamento_id)
    return list(
        Leitura.objects.filter(apartamento_id=apartamento_id)
        .order_by("-ano", "-mes", "-id")[:limite]
    )


def excluir_leitura(leitura_id):
    leitura = consultar_leitura(leitura_id)
    leitura.delete()
