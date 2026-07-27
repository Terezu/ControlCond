from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("faturas", "0018_bonificacao_especifica_fatura"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="fatura",
            name="fatura_bonificacao_com_dia",
        ),
        migrations.AddConstraint(
            model_name="fatura",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(valor_bonificacao=0)
                    | models.Q(dia_limite_bonificacao__isnull=False)
                    | models.Q(data_limite_bonificacao__isnull=False)
                ),
                name="fatura_bonificacao_com_dia",
            ),
        ),
    ]
