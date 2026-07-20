from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Prefetch

from faturas.models import Fatura
from leituras.models import Leitura

from .models import LIMITE_LEITURA, Apartamento


def cadastrar_apartamento(
    numero,
    leitura_base_agua,
    leitura_base_gas,
    bloco=None,
    observacoes=None,
):
    """Cria e retorna um apartamento."""
    numero = _normalizar_numero(numero)
    bloco = _normalizar_texto_opcional(bloco)
    observacoes = _normalizar_texto_opcional(observacoes)
    leitura_base_agua, leitura_base_gas = _validar_leituras_base(
        leitura_base_agua,
        leitura_base_gas,
    )

    apartamento = Apartamento(
        numero=numero,
        bloco=bloco,
        observacoes=observacoes,
        leitura_base_agua=leitura_base_agua,
        leitura_base_gas=leitura_base_gas,
    )
    _validar_modelo(apartamento)
    apartamento.save(force_insert=True)
    return apartamento


@transaction.atomic
def editar_apartamento(
    apartamento_id,
    numero,
    leitura_base_agua,
    leitura_base_gas,
    bloco=None,
    observacoes=None,
):
    try:
        apartamento = (
            Apartamento.objects
            .select_for_update()
            .get(pk=apartamento_id)
        )
    except Apartamento.DoesNotExist as exc:
        raise ValueError("Apartamento não encontrado.") from exc
    numero = _normalizar_numero(numero)
    bloco = _normalizar_texto_opcional(bloco)
    observacoes = _normalizar_texto_opcional(observacoes)
    leitura_base_agua, leitura_base_gas = _validar_leituras_base(
        leitura_base_agua,
        leitura_base_gas,
    )

    apartamento.numero = numero
    apartamento.bloco = bloco
    apartamento.observacoes = observacoes
    apartamento.leitura_base_agua = leitura_base_agua
    apartamento.leitura_base_gas = leitura_base_gas
    _validar_modelo(apartamento)
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


def _validar_leituras_base(
    leitura_base_agua,
    leitura_base_gas,
):
    if leitura_base_agua is None or leitura_base_gas is None:
        raise ValueError(
            "Informe as leituras-base de água e gás."
        )
    return (
        _normalizar_leitura_base(leitura_base_agua, "água"),
        _normalizar_leitura_base(leitura_base_gas, "gás"),
    )


def _normalizar_leitura_base(valor, recurso):
    if isinstance(valor, bool):
        raise ValueError(
            f"A leitura-base de {recurso} deve ser um número válido."
        )
    try:
        valor = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(
            f"A leitura-base de {recurso} deve ser um número válido."
        ) from exc

    if not valor.is_finite():
        raise ValueError(
            f"A leitura-base de {recurso} deve ser um número finito."
        )
    if valor < 0:
        raise ValueError(
            f"A leitura-base de {recurso} não pode ser negativa."
        )
    if valor > LIMITE_LEITURA:
        raise ValueError(
            f"A leitura-base de {recurso} excede o valor máximo permitido."
        )
    return valor


def _normalizar_numero(numero):
    if numero is None or isinstance(numero, bool):
        raise ValueError("O número do apartamento é obrigatório.")
    numero = str(numero).strip()
    if not numero:
        raise ValueError("O número do apartamento é obrigatório.")
    return numero


def _normalizar_texto_opcional(valor):
    if valor is None:
        return None
    valor = str(valor).strip()
    return valor or None



def _validar_modelo(apartamento):
    try:
        apartamento.full_clean(validate_unique=False, validate_constraints=False)
    except ValidationError as exc:
        raise ValueError(" ".join(exc.messages)) from exc


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


@transaction.atomic
def excluir_apartamento(apartamento_id):
    try:
        apartamento = (
            Apartamento.objects
            .select_for_update()
            .get(pk=apartamento_id)
        )
    except Apartamento.DoesNotExist as exc:
        raise ValueError("Apartamento não encontrado.") from exc
    apartamento.delete()
