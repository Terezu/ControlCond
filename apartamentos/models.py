from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Coalesce, Lower, Trim


LIMITE_LEITURA = Decimal("999999.99")
LIMITE_VALOR_MONETARIO = Decimal("99999999.99")


class Apartamento(models.Model):
    numero = models.CharField(max_length=20)
    bloco = models.CharField(max_length=50, blank=True, null=True)
    observacoes = models.TextField(blank=True, null=True)
    valor_aluguel = models.DecimalField(
        "Valor padrão do aluguel",
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        blank=True,
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(LIMITE_VALOR_MONETARIO),
        ],
    )
    valor_condominio = models.DecimalField(
        "Valor padrão do condomínio",
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        blank=True,
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(LIMITE_VALOR_MONETARIO),
        ],
    )
    valor_iptu = models.DecimalField(
        "Valor padrão do IPTU",
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        blank=True,
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(LIMITE_VALOR_MONETARIO),
        ],
    )
    valor_bonificacao = models.DecimalField(
        "Valor padrão da bonificação",
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        blank=True,
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(LIMITE_VALOR_MONETARIO),
        ],
    )
    dia_limite_bonificacao = models.PositiveSmallIntegerField(
        "Dia limite padrão da bonificação",
        blank=True,
        null=True,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
    )

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
            models.UniqueConstraint(
                Lower("numero"),
                Coalesce(Lower("bloco"), models.Value("")),
                name="apartamento_unico_por_numero_e_bloco",
                violation_error_message=(
                    "Já existe um apartamento com este número e bloco."
                ),
            ),
            models.CheckConstraint(
                condition=models.Q(valor_aluguel__gte=0),
                name="apartamento_aluguel_nao_negativo",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    valor_aluguel__lte=LIMITE_VALOR_MONETARIO
                ),
                name="apartamento_aluguel_no_limite",
            ),
            models.CheckConstraint(
                condition=models.Q(valor_condominio__gte=0),
                name="apartamento_condominio_nao_negativo",
            ),
            models.CheckConstraint(
                condition=models.Q(valor_iptu__gte=0),
                name="apartamento_iptu_nao_negativo",
            ),
            models.CheckConstraint(
                condition=models.Q(valor_bonificacao__gte=0),
                name="apartamento_bonificacao_nao_negativa",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(dia_limite_bonificacao__isnull=True)
                    | models.Q(
                        dia_limite_bonificacao__gte=1,
                        dia_limite_bonificacao__lte=31,
                    )
                ),
                name="apartamento_dia_bonificacao_valido",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(valor_bonificacao=0)
                    | models.Q(dia_limite_bonificacao__isnull=False)
                ),
                name="apartamento_bonificacao_com_dia",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(numero="")
                    & models.Q(numero=Trim("numero"))
                ),
                name="apartamento_numero_valido",
                violation_error_message=(
                    "O número do apartamento é obrigatório e não pode "
                    "conter espaços nas extremidades."
                ),
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(bloco__isnull=True)
                    | (
                        ~models.Q(bloco="")
                        & models.Q(bloco=Trim("bloco"))
                    )
                ),
                name="apartamento_bloco_normalizado",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(observacoes__isnull=True)
                    | (
                        ~models.Q(observacoes="")
                        & models.Q(observacoes=Trim("observacoes"))
                    )
                ),
                name="apartamento_observacoes_normalizadas",
            ),
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

        if isinstance(self.numero, str):
            self.numero = self.numero.strip()
        if isinstance(self.bloco, str):
            self.bloco = self.bloco.strip() or None
        if isinstance(self.observacoes, str):
            self.observacoes = self.observacoes.strip() or None

        if (
            isinstance(self.valor_bonificacao, Decimal)
            and self.valor_bonificacao > 0
            and self.dia_limite_bonificacao is None
        ):
            raise ValidationError(
                {
                    "dia_limite_bonificacao": (
                        "Informe o dia limite quando houver bonificação."
                    )
                }
            )

        if not self.numero:
            raise ValidationError(
                {"numero": "O número do apartamento é obrigatório."}
            )

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
