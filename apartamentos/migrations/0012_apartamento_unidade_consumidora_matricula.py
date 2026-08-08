from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("apartamentos", "0011_remove_apartamento_apartamento_unico_por_condominio_numero_bloco_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="apartamento",
            name="unidade_consumidora",
            field=models.CharField(
                blank=True,
                max_length=100,
                null=True,
                verbose_name="Unidade Consumidora",
            ),
        ),
        migrations.AddField(
            model_name="apartamento",
            name="matricula",
            field=models.CharField(
                blank=True,
                max_length=100,
                null=True,
                verbose_name="Matrícula",
            ),
        ),
        migrations.AddConstraint(
            model_name="apartamento",
            constraint=models.UniqueConstraint(
                condition=models.Q(unidade_consumidora__isnull=False),
                fields=("condominio", "unidade_consumidora"),
                name="apartamento_uc_unica_por_condominio",
                violation_error_message=(
                    "Esta Unidade Consumidora já pertence a outro apartamento."
                ),
            ),
        ),
        migrations.AddConstraint(
            model_name="apartamento",
            constraint=models.UniqueConstraint(
                condition=models.Q(matricula__isnull=False),
                fields=("condominio", "matricula"),
                name="apartamento_matricula_unica_por_condominio",
                violation_error_message=(
                    "Esta Matrícula já pertence a outro apartamento."
                ),
            ),
        ),
    ]
