from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "faturas",
            "0015_fatura_dias_antecedencia_bonificacao_emissao_and_more",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="historicostatusfatura",
            name="valores_anteriores",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="historicostatusfatura",
            name="valores_novos",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name="historicostatusfatura",
            name="acao",
            field=models.CharField(
                choices=[
                    ("fatura_criada", "Fatura criada"),
                    ("pagamento_confirmado", "Pagamento confirmado"),
                    (
                        "valores_financeiros_alterados",
                        "Valores financeiros alterados",
                    ),
                    ("fatura_cancelada", "Fatura cancelada"),
                    ("pagamento_estornado", "Pagamento estornado"),
                    ("fatura_reaberta", "Fatura reaberta"),
                ],
                max_length=30,
            ),
        ),
    ]
