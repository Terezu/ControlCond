from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apartamentos.models import Apartamento


LIMITE_LEITURA = Decimal("999999.99")
ANO_MAXIMO = 9999


class Leitura(models.Model):
    apartamento = models.ForeignKey(
        Apartamento,
        on_delete=models.PROTECT,
        related_name="leituras",
    )

    mes = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    ano = models.IntegerField(
        validators=[MinValueValidator(2000), MaxValueValidator(ANO_MAXIMO)]
    )

    leitura_agua = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(LIMITE_LEITURA),
        ],
    )

    leitura_gas = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(LIMITE_LEITURA),
        ],
    )

    data_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "leituras"
        ordering = ["-ano", "-mes"]

        constraints = [
            models.UniqueConstraint(
                fields=["apartamento", "mes", "ano"],
                name="leitura_unica_por_apartamento_e_mes",
            ),
            models.CheckConstraint(
                condition=models.Q(mes__gte=1, mes__lte=12),
                name="leitura_mes_valido",
            ),
            models.CheckConstraint(
                condition=models.Q(ano__gte=2000, ano__lte=ANO_MAXIMO),
                name="leitura_ano_valido",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(leitura_agua__isnull=False)
                    | models.Q(leitura_gas__isnull=False)
                ),
                name="leitura_agua_ou_gas_informado",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(leitura_agua__isnull=True)
                    | models.Q(leitura_agua__gte=0)
                ),
                name="leitura_agua_nao_negativa",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(leitura_gas__isnull=True)
                    | models.Q(leitura_gas__gte=0)
                ),
                name="leitura_gas_nao_negativa",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(leitura_agua__isnull=True)
                    | models.Q(leitura_agua__lte=LIMITE_LEITURA)
                ),
                name="leitura_agua_no_limite",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(leitura_gas__isnull=True)
                    | models.Q(leitura_gas__lte=LIMITE_LEITURA)
                ),
                name="leitura_gas_no_limite",
            ),
        ]

    def __str__(self):
        return f"Leitura {self.mes:02d}/{self.ano} - {self.apartamento}"

    def clean(self):
        super().clean()

        if (
            self.apartamento_id is None
            or not isinstance(self.mes, int)
            or not isinstance(self.ano, int)
        ):
            return

        apartamento = (
            Apartamento.objects
            .filter(pk=self.apartamento_id)
            .values("leitura_base_agua", "leitura_base_gas")
            .first()
        )
        if apartamento is None:
            return

        outras_leituras = Leitura.objects.filter(
            apartamento_id=self.apartamento_id,
        )
        if self.pk:
            outras_leituras = outras_leituras.exclude(pk=self.pk)

        anteriores = outras_leituras.filter(
            models.Q(ano__lt=self.ano)
            | models.Q(ano=self.ano, mes__lt=self.mes)
        )
        posteriores = outras_leituras.filter(
            models.Q(ano__gt=self.ano)
            | models.Q(ano=self.ano, mes__gt=self.mes)
        )

        erros = {}
        campos = (
            ("leitura_agua", "leitura_base_agua", "água"),
            ("leitura_gas", "leitura_base_gas", "gás"),
        )
        for campo_leitura, campo_base, recurso in campos:
            valor_atual = getattr(self, campo_leitura)
            if not isinstance(valor_atual, Decimal):
                continue

            anterior = (
                anteriores
                .filter(**{f"{campo_leitura}__isnull": False})
                .order_by("-ano", "-mes", "-id")
                .values(campo_leitura, "mes", "ano")
                .first()
            )
            if anterior is None:
                valor_anterior = apartamento[campo_base]
                if valor_anterior is not None and valor_atual < valor_anterior:
                    erros.setdefault(campo_leitura, []).append(
                        f"A leitura de {recurso} não pode ser menor que "
                        "a leitura-base do apartamento."
                    )
            elif valor_atual < anterior[campo_leitura]:
                erros.setdefault(campo_leitura, []).append(
                    f"A leitura de {recurso} não pode ser menor que a "
                    f"medição anterior ({anterior['mes']:02d}/{anterior['ano']})."
                )

            posterior = (
                posteriores
                .filter(**{f"{campo_leitura}__isnull": False})
                .order_by("ano", "mes", "id")
                .values(campo_leitura, "mes", "ano")
                .first()
            )
            if posterior is not None and valor_atual > posterior[campo_leitura]:
                erros.setdefault(campo_leitura, []).append(
                    f"A leitura de {recurso} não pode ser maior que a "
                    f"medição posterior ({posterior['mes']:02d}/{posterior['ano']})."
                )

        if erros:
            raise ValidationError(erros)
