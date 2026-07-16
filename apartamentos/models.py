from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


LIMITE_LEITURA = Decimal("999999.99")


class Apartamento(models.Model):
    numero = models.CharField(max_length=20)
    bloco = models.CharField(max_length=50, blank=True, null=True)
    observacoes = models.TextField(blank=True, null=True)

    leitura_base_agua = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(LIMITE_LEITURA),
        ],
    )

    leitura_base_gas = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(LIMITE_LEITURA),
        ],
    )

    class Meta:
        db_table = "apartamentos"
        ordering = ["bloco", "numero"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(leitura_base_agua__isnull=True)
                    | models.Q(leitura_base_agua__gte=0)
                ),
                name="apartamento_base_agua_nao_negativa",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(leitura_base_gas__isnull=True)
                    | models.Q(leitura_base_gas__gte=0)
                ),
                name="apartamento_base_gas_nao_negativa",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(leitura_base_agua__isnull=True)
                    | models.Q(leitura_base_agua__lte=LIMITE_LEITURA)
                ),
                name="apartamento_base_agua_no_limite",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(leitura_base_gas__isnull=True)
                    | models.Q(leitura_base_gas__lte=LIMITE_LEITURA)
                ),
                name="apartamento_base_gas_no_limite",
            ),
        ]

    def __str__(self):
        if self.bloco:
            return f"Apartamento {self.numero} - Bloco {self.bloco}"
        return f"Apartamento {self.numero}"

    def clean(self):
        super().clean()

        if not self.pk:
            return

        erros = {}
        campos = (
            ("leitura_base_agua", "leitura_agua", "água"),
            ("leitura_base_gas", "leitura_gas", "gás"),
        )

        for campo_base, campo_leitura, recurso in campos:
            leitura_base = getattr(self, campo_base)
            if not isinstance(leitura_base, Decimal):
                continue

            primeira_leitura = (
                self.leituras
                .filter(**{f"{campo_leitura}__isnull": False})
                .order_by("ano", "mes", "id")
                .values_list(campo_leitura, flat=True)
                .first()
            )
            if (
                primeira_leitura is not None
                and leitura_base > primeira_leitura
            ):
                erros[campo_base] = (
                    f"A leitura-base de {recurso} não pode ser maior que "
                    "a primeira leitura cadastrada para esse medidor."
                )

        if erros:
            raise ValidationError(erros)
