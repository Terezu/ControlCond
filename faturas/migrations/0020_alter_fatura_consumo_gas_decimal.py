from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("faturas", "0019_ajustar_limite_bonificacao_legada"),
    ]

    operations = [
        migrations.AlterField(
            model_name="fatura",
            name="consumo_gas",
            field=models.DecimalField(
                max_digits=10,
                decimal_places=2,
                validators=[MinValueValidator(Decimal("0"))],
            ),
        ),
    ]
