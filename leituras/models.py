from django.db import models

from apartamentos.models import Apartamento


class Leitura(models.Model):
    apartamento = models.ForeignKey(
        Apartamento,
        on_delete=models.PROTECT,
        related_name="leituras",
    )

    mes = models.IntegerField()
    ano = models.IntegerField()

    leitura_agua = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )

    leitura_gas = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )

    data_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "leituras"
        ordering = ["-ano", "-mes"]

        constraints = [
            models.UniqueConstraint(
                fields=["apartamento", "mes", "ano"],
                name="leitura_unica_por_apartamento_e_mes",
            )
        ]

    def __str__(self):
        return f"Leitura {self.mes:02d}/{self.ano} - {self.apartamento}"
