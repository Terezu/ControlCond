from django.db.models import Prefetch

from faturas.models import Fatura
from leituras.models import Leitura

from .models import Apartamento


def cadastrar_apartamento(
    numero,
    leitura_base_agua,
    leitura_base_gas,
    bloco=None,
    observacoes=None,
):
    """Cria e retorna um apartamento."""
    if not numero:
        raise ValueError("O número do apartamento é obrigatório.")
    _validar_leituras_base(leitura_base_agua, leitura_base_gas)

    return Apartamento.objects.create(
        numero=numero,
        bloco=bloco or None,
        observacoes=observacoes or None,
        leitura_base_agua=leitura_base_agua,
        leitura_base_gas=leitura_base_gas,
    )


def editar_apartamento(
    apartamento_id,
    numero,
    leitura_base_agua,
    leitura_base_gas,
    bloco=None,
    observacoes=None,
):
    apartamento = consultar_apartamento(apartamento_id)
    if not numero:
        raise ValueError("O número do apartamento é obrigatório.")
    _validar_leituras_base(leitura_base_agua, leitura_base_gas)

    apartamento.numero = numero
    apartamento.bloco = bloco or None
    apartamento.observacoes = observacoes or None
    apartamento.leitura_base_agua = leitura_base_agua
    apartamento.leitura_base_gas = leitura_base_gas
    apartamento.save(
        update_fields=[
            "numero",
            "bloco",
            "observacoes",
            "leitura_base_agua",
            "leitura_base_gas",
        ]
    )
    return apartamento


def _validar_leituras_base(leitura_base_agua, leitura_base_gas):
    if leitura_base_agua is None or leitura_base_gas is None:
        raise ValueError(
            "Informe as leituras-base de água e gás."
        )
    if leitura_base_agua < 0 or leitura_base_gas < 0:
        raise ValueError("As leituras-base não podem ser negativas.")


def consultar_apartamento(apartamento_id):
    try:
        return Apartamento.objects.get(pk=apartamento_id)
    except Apartamento.DoesNotExist as exc:
        raise ValueError("Apartamento não encontrado.") from exc
    

def consultar_detalhes_apartamento(apartamento_id):
    try:
        return (
            Apartamento.objects
            .prefetch_related(
                Prefetch(
                    "leituras",
                    queryset=Leitura.objects.order_by("-ano", "-mes", "-id")
                ),
                Prefetch(
                    "faturas",
                    queryset=Fatura.objects.order_by("-ano", "-mes", "-id")
                ),
            )
            .get(pk=apartamento_id)
        )
    except Apartamento.DoesNotExist as exc:
        raise ValueError("Apartamento não encontrado.") from exc



def listar_apartamentos():
    return Apartamento.objects.order_by("bloco", "numero", "id")


def excluir_apartamento(apartamento_id):
    apartamento = consultar_apartamento(apartamento_id)
    apartamento.delete()
