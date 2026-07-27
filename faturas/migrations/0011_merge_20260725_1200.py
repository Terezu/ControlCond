from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("faturas", "0009_corrigir_e_proteger_valor_total"),
        (
            "faturas",
            "0010_fatura_data_cancelamento_fatura_data_pagamento_and_more",
        ),
    ]

    operations = []
