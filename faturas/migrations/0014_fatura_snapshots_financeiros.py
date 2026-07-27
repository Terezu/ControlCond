import calendar
from datetime import date
from decimal import Decimal

import django.core.validators
from django.db import migrations, models


def preencher_snapshots_financeiros(apps, schema_editor):
    Fatura = apps.get_model("faturas", "Fatura")
    Configuracao = apps.get_model(
        "configuracoes",
        "ConfiguracaoCondominio",
    )
    configuracoes = {
        item.condominio_id: item
        for item in Configuracao.objects.all()
    }
    campos = (
        "data_vencimento",
        "data_limite_bonificacao",
        "dias_em_atraso",
        "dias_antecipados",
        "valor_multa_aplicada",
        "valor_juros_aplicados",
        "valor_bonificacao_aplicada",
        "valor_original",
        "valor_final",
    )
    for fatura in Fatura.objects.select_related(
        "apartamento__condominio"
    ).iterator():
        configuracao = configuracoes.get(fatura.apartamento.condominio_id)
        dia_vencimento = (
            configuracao.dia_vencimento_padrao
            if configuracao is not None
            else Configuracao._meta.get_field(
                "dia_vencimento_padrao"
            ).default
        )
        ultimo_dia = calendar.monthrange(fatura.ano, fatura.mes)[1]
        fatura.data_vencimento = date(
            fatura.ano,
            fatura.mes,
            min(dia_vencimento, ultimo_dia),
        )
        if fatura.valor_bonificacao and fatura.dia_limite_bonificacao:
            fatura.data_limite_bonificacao = date(
                fatura.ano,
                fatura.mes,
                min(fatura.dia_limite_bonificacao, ultimo_dia),
            )
        fatura.valor_original = fatura.valor_total + fatura.desconto
        fatura.valor_multa_aplicada = Decimal("0.00")
        fatura.valor_juros_aplicados = Decimal("0.00")
        fatura.valor_bonificacao_aplicada = (
            fatura.valor_bonificacao
            if fatura.bonificacao_aplicada
            else Decimal("0.00")
        )
        if fatura.status == "paga" and fatura.data_pagamento:
            diferenca = fatura.data_pagamento - fatura.data_vencimento
            fatura.dias_em_atraso = max(diferenca.days, 0)
            fatura.dias_antecipados = max(-diferenca.days, 0)
            fatura.valor_final = (
                fatura.valor_pago
                if fatura.valor_pago is not None
                else (
                    fatura.valor_original
                    - fatura.valor_bonificacao_aplicada
                )
            )
        Fatura.objects.filter(pk=fatura.pk).update(
            **{campo: getattr(fatura, campo) for campo in campos}
        )


class Migration(migrations.Migration):

    dependencies = [
        ("configuracoes", "0006_configuracaocondominio_dia_vencimento_padrao_and_more"),
        ("faturas", "0013_fatura_faixa_agua_utilizada_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="fatura",
            name="data_limite_bonificacao",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="fatura",
            name="data_vencimento",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="fatura",
            name="dias_antecipados",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="fatura",
            name="dias_em_atraso",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="fatura",
            name="valor_bonificacao_aplicada",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                max_digits=10,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0"))
                ],
            ),
        ),
        migrations.AddField(
            model_name="fatura",
            name="valor_final",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0"))
                ],
            ),
        ),
        migrations.AddField(
            model_name="fatura",
            name="valor_juros_aplicados",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                max_digits=10,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0"))
                ],
            ),
        ),
        migrations.AddField(
            model_name="fatura",
            name="valor_multa_aplicada",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                max_digits=10,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0"))
                ],
            ),
        ),
        migrations.AddField(
            model_name="fatura",
            name="valor_original",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                max_digits=10,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0"))
                ],
            ),
        ),
        migrations.RunPython(
            preencher_snapshots_financeiros,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="fatura",
            name="data_vencimento",
            field=models.DateField(),
        ),
        migrations.AddConstraint(
            model_name="fatura",
            constraint=models.CheckConstraint(
                condition=models.Q(("valor_original__gte", 0)),
                name="fatura_valor_original_nao_negativo",
            ),
        ),
        migrations.AddConstraint(
            model_name="fatura",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("valor_final__isnull", True))
                    | models.Q(("valor_final__gte", 0))
                ),
                name="fatura_valor_final_nao_negativo",
            ),
        ),
        migrations.AddConstraint(
            model_name="fatura",
            constraint=models.CheckConstraint(
                condition=models.Q(("valor_multa_aplicada__gte", 0)),
                name="fatura_multa_aplicada_nao_negativa",
            ),
        ),
        migrations.AddConstraint(
            model_name="fatura",
            constraint=models.CheckConstraint(
                condition=models.Q(("valor_juros_aplicados__gte", 0)),
                name="fatura_juros_aplicados_nao_negativos",
            ),
        ),
        migrations.AddConstraint(
            model_name="fatura",
            constraint=models.CheckConstraint(
                condition=models.Q(("valor_bonificacao_aplicada__gte", 0)),
                name="fatura_bonus_aplicado_nao_negativo",
            ),
        ),
    ]
