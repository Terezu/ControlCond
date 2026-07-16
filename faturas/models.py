from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apartamentos.models import Apartamento
from leituras.models import Leitura


ANO_MAXIMO = 9999


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
        on_delete=models.PROTECT,
        related_name="faturas",
        blank=True,
        null=True,
    )

    mes = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    ano = models.IntegerField(
        validators=[MinValueValidator(2000), MaxValueValidator(ANO_MAXIMO)]
    )

    consumo_agua = models.PositiveIntegerField()
    consumo_gas = models.PositiveIntegerField()

    valor_agua = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    valor_gas = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    valor_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDENTE,
    )

    data_geracao = models.DateTimeField(auto_now_add=True)
    data_emissao = models.DateTimeField(auto_now_add=True)

    # Retrato imutável dos dados usados na emissão. A leitura e o apartamento
    # podem ser corrigidos no futuro sem reescrever o documento já emitido.
    apartamento_numero_emissao = models.CharField(max_length=20, blank=True)
    apartamento_bloco_emissao = models.CharField(
        max_length=50,
        blank=True,
        null=True,
    )
    leitura_agua_anterior = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )
    leitura_agua_atual = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )
    leitura_gas_anterior = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )
    leitura_gas_atual = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )

    class Meta:
        db_table = "faturas"
        ordering = ["-ano", "-mes"]

        constraints = [
            models.UniqueConstraint(
                fields=["apartamento", "mes", "ano"],
                name="fatura_unica_por_apartamento_e_mes",
            ),
            models.CheckConstraint(
                condition=models.Q(mes__gte=1, mes__lte=12),
                name="fatura_mes_valido",
            ),
            models.CheckConstraint(
                condition=models.Q(ano__gte=2000, ano__lte=ANO_MAXIMO),
                name="fatura_ano_valido",
            ),
            models.CheckConstraint(
                condition=models.Q(valor_agua__gte=0),
                name="fatura_valor_agua_nao_negativo",
            ),
            models.CheckConstraint(
                condition=models.Q(valor_gas__gte=0),
                name="fatura_valor_gas_nao_negativo",
            ),
            models.CheckConstraint(
                condition=models.Q(valor_total__gte=0),
                name="fatura_valor_total_nao_negativo",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=["pendente", "paga", "cancelada"]
                ),
                name="fatura_status_valido",
            ),
        ]
    
    def __str__(self):
        return f"Fatura {self.mes:02d}/{self.ano} - {self.apartamento}"
