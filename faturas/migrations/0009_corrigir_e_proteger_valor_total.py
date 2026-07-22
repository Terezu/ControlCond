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

    operations = [
        migrations.RunPython(
            corrigir_valores_totais,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="fatura",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    valor_total=Round(
                        models.F("valor_agua") + models.F("valor_gas"),
                        precision=2,
                    )
                ),
                name="fatura_total_igual_a_soma",
            ),
        ),
    ]
