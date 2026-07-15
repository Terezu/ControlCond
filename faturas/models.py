from decimal import Decimal

from django.db import models

from apartamentos.models import Apartamento
from leituras.models import Leitura


class Fatura(models.Model):
    class Status(models.TextChoices):
        PENDENTE = "pendente", "Pendente"
        PAGA = "paga", "Paga"
        CANCELADA = "cancelada", "Cancelada"

    apartamento = models.ForeignKey(
        Apartamento,
        on_delete=models.PROTECT,
        related_name="faturas",
    )

    leitura = models.ForeignKey(
        Leitura,
        on_delete=models.SET_NULL,
        related_name="faturas",
        blank=True,
        null=True,
    )

    mes = models.IntegerField()
    ano = models.IntegerField()

    consumo_agua = models.PositiveIntegerField()
    consumo_gas = models.PositiveIntegerField()

    valor_agua = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    valor_gas = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    valor_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDENTE,
    )

    data_geracao = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "faturas"
        ordering = ["-ano", "-mes"]

        constraints = [
            models.UniqueConstraint(
                fields=["apartamento", "mes", "ano"],
                name="fatura_unica_por_apartamento_e_mes",
            )
        ]
    
    data_emissao = models.DateTimeField(
    auto_now_add=True,
    )

    def __str__(self):
        return f"Fatura {self.mes:02d}/{self.ano} - {self.apartamento}"
