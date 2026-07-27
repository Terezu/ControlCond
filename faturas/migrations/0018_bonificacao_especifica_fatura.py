from decimal import Decimal

from django.db import migrations, models
import django.core.validators


def classificar_bonificacoes_existentes(apps, schema_editor):
    Fatura = apps.get_model("faturas", "Fatura")
    for fatura in Fatura.objects.all().iterator():
        if fatura.valor_bonificacao > 0:
            fatura.origem_bonificacao_emissao = "especifica"
            fatura.tipo_bonificacao_emissao = "valor_fixo"
            fatura.valor_bonificacao_fixa_emissao = (
                fatura.valor_bonificacao
            )
        elif fatura.percentual_bonificacao_emissao > 0:
            fatura.origem_bonificacao_emissao = "condominio"
            fatura.tipo_bonificacao_emissao = "percentual"
        else:
            fatura.origem_bonificacao_emissao = "nenhuma"
            fatura.tipo_bonificacao_emissao = "nenhuma"
        fatura.save(
            update_fields=[
                "origem_bonificacao_emissao",
                "tipo_bonificacao_emissao",
                "valor_bonificacao_fixa_emissao",
            ]
        )


class Migration(migrations.Migration):

    dependencies = [
        (
            "faturas",
            "0017_renomear_historico_financeiro_e_indice_faturas",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="fatura",
            name="origem_bonificacao_emissao",
            field=models.CharField(
                choices=[
                    (
                        "condominio",
                        "Usar bonificação padrão do condomínio",
                    ),
                    ("especifica", "Definir bonificação específica"),
                    ("nenhuma", "Não aplicar bonificação"),
                ],
                default="condominio",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="fatura",
            name="tipo_bonificacao_emissao",
            field=models.CharField(
                choices=[
                    ("percentual", "Percentual"),
                    ("valor_fixo", "Valor fixo"),
                    ("nenhuma", "Nenhuma"),
                ],
                default="nenhuma",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="fatura",
            name="valor_bonificacao_fixa_emissao",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                max_digits=10,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0")),
                    django.core.validators.MaxValueValidator(
                        Decimal("99999999.99")
                    ),
                ],
            ),
        ),
        migrations.RunPython(
            classificar_bonificacoes_existentes,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="fatura",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    percentual_bonificacao_emissao__gte=0,
                    percentual_bonificacao_emissao__lte=100,
                ),
                name="fatura_bonus_percentual_emissao_valido",
            ),
        ),
        migrations.AddConstraint(
            model_name="fatura",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    valor_bonificacao_fixa_emissao__gte=0,
                ),
                name="fatura_bonus_fixo_emissao_nao_negativo",
            ),
        ),
    ]
