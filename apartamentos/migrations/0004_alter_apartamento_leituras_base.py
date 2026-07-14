from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("apartamentos", "0003_apartamento_leitura_base_agua_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="apartamento",
            name="leitura_base_agua",
            field=models.DecimalField(decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AlterField(
            model_name="apartamento",
            name="leitura_base_gas",
            field=models.DecimalField(decimal_places=2, max_digits=10, null=True),
        ),
    ]
