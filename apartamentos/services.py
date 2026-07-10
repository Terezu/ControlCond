from .models import Apartamento


def cadastrar_apartamento(numero, bloco=None, observacoes=None):
    """Cria e retorna um apartamento."""
    if not numero:
        raise ValueError("O número do apartamento é obrigatório.")

    return Apartamento.objects.create(
        numero=numero,
        bloco=bloco or None,
        observacoes=observacoes or None,
    )


def editar_apartamento(apartamento_id, numero, bloco=None, observacoes=None):
    apartamento = consultar_apartamento(apartamento_id)
    if not numero:
        raise ValueError("O número do apartamento é obrigatório.")

    apartamento.numero = numero
    apartamento.bloco = bloco or None
    apartamento.observacoes = observacoes or None
    apartamento.save(update_fields=["numero", "bloco", "observacoes"])
    return apartamento


def consultar_apartamento(apartamento_id):
    try:
        return Apartamento.objects.get(pk=apartamento_id)
    except Apartamento.DoesNotExist as exc:
        raise ValueError("Apartamento não encontrado.") from exc


def listar_apartamentos():
    return Apartamento.objects.order_by("bloco", "numero", "id")


def excluir_apartamento(apartamento_id):
    apartamento = consultar_apartamento(apartamento_id)
    apartamento.delete()

