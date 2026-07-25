from django.db import migrations, models
from django.db.models.functions import Round


def corrigir_valores_totais(apps, schema_editor):
    Fatura = apps.get_model("faturas", "Fatura")
    alias = schema_editor.connection.alias

    faturas = (
        Fatura.objects
        .using(alias)
        .only("id", "valor_agua", "valor_gas", "valor_total")
        .iterator()
    )
    for fatura in faturas:
        total_correto = fatura.valor_agua + fatura.valor_gas
        if fatura.valor_total != total_correto:
            (
                Fatura.objects
                .using(alias)
                .filter(pk=fatura.pk)
                .update(valor_total=total_correto)
            )


class Migration(migrations.Migration):

    dependencies = [
        ("faturas", "0008_limitar_ano"),
    ]

    # Esta ramificação ficou órfã quando a composição financeira passou a
    # incluir aluguel e desconto na migration paralela 0009. Executar o
    # RunPython antigo em bancos existentes sobrescreveria totais válidos.
    # A migration é mantida no grafo e reconciliada pela 0011, sem operações.
    operations = []
