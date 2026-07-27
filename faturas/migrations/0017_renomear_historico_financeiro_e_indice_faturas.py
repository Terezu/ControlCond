import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "faturas",
            "0016_historicostatusfatura_snapshots_financeiros",
        ),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameModel(
            old_name="HistoricoStatusFatura",
            new_name="HistoricoFinanceiroFatura",
        ),
        migrations.AlterField(
            model_name="historicofinanceirofatura",
            name="fatura",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="historico_financeiro",
                to="faturas.fatura",
            ),
        ),
        migrations.AlterField(
            model_name="historicofinanceirofatura",
            name="usuario",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="alteracoes_financeiras_faturas",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name="fatura",
            index=models.Index(
                fields=["ano", "mes", "status", "data_vencimento"],
                name="fatura_comp_status_venc_idx",
            ),
        ),
    ]
