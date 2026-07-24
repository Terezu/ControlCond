from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Round

from apartamentos.models import Apartamento
from calculos.services import calcular_agua, calcular_gas
from configuracoes.models import LIMITE_VALOR_GAS
from leituras.models import Leitura


ANO_MAXIMO = 9999
LIMITE_VALOR_FINANCEIRO = Decimal("99999999.99")


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
    valor_aluguel = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(LIMITE_VALOR_FINANCEIRO),
        ],
    )
    desconto = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(LIMITE_VALOR_FINANCEIRO),
        ],
    )

    valor_m3_gas_emissao = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("21.02"),
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(LIMITE_VALOR_GAS),
        ],
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDENTE,
    )

    data_geracao = models.DateTimeField(auto_now_add=True)
    data_emissao = models.DateTimeField(auto_now_add=True)
    data_pagamento = models.DateTimeField(blank=True, null=True)
    data_cancelamento = models.DateTimeField(blank=True, null=True)

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
                condition=models.Q(valor_aluguel__gte=0),
                name="fatura_aluguel_nao_negativo",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    valor_aluguel__lte=LIMITE_VALOR_FINANCEIRO
                ),
                name="fatura_aluguel_no_limite",
            ),
            models.CheckConstraint(
                condition=models.Q(desconto__gte=0),
                name="fatura_desconto_nao_negativo",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    desconto__lte=LIMITE_VALOR_FINANCEIRO
                ),
                name="fatura_desconto_no_limite",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    desconto__lte=(
                        models.F("valor_agua")
                        + models.F("valor_gas")
                        + models.F("valor_aluguel")
                    )
                ),
                name="fatura_desconto_no_subtotal",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    valor_total=Round(
                        models.F("valor_agua")
                        + models.F("valor_gas")
                        + models.F("valor_aluguel")
                        - models.F("desconto"),
                        precision=2,
                    )
                ),
                name="fatura_total_igual_a_soma",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=["pendente", "paga", "cancelada"]
                ),
                name="fatura_status_valido",
            ),
            models.CheckConstraint(
                condition=models.Q(valor_m3_gas_emissao__gte=0),
                name="fatura_tarifa_gas_nao_negativa",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    valor_m3_gas_emissao__lte=LIMITE_VALOR_GAS
                ),
                name="fatura_tarifa_gas_no_limite",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        leitura_agua_anterior__isnull=True,
                        leitura_agua_atual__isnull=True,
                    )
                    | models.Q(
                        leitura_agua_anterior__isnull=False,
                        leitura_agua_atual__isnull=False,
                        leitura_agua_atual__gte=models.F(
                            "leitura_agua_anterior"
                        ),
                    )
                ),
                name="fatura_leituras_agua_coerentes",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        leitura_gas_anterior__isnull=True,
                        leitura_gas_atual__isnull=True,
                    )
                    | models.Q(
                        leitura_gas_anterior__isnull=False,
                        leitura_gas_atual__isnull=False,
                        leitura_gas_atual__gte=models.F(
                            "leitura_gas_anterior"
                        ),
                    )
                ),
                name="fatura_leituras_gas_coerentes",
            ),
        ]
    
    def __str__(self):
        return f"Fatura {self.mes:02d}/{self.ano} - {self.apartamento}"

    @staticmethod
    def calcular_composicao_financeira(
        valor_agua,
        valor_gas,
        valor_aluguel,
        desconto,
    ):
        centavos = Decimal("0.01")
        valores = tuple(
            valor.quantize(centavos, rounding=ROUND_HALF_UP)
            for valor in (
                valor_agua,
                valor_gas,
                valor_aluguel,
                desconto,
            )
        )
        valor_agua, valor_gas, valor_aluguel, desconto = valores
        subtotal = (valor_agua + valor_gas + valor_aluguel).quantize(
            centavos,
            rounding=ROUND_HALF_UP,
        )
        if subtotal > LIMITE_VALOR_FINANCEIRO:
            raise ValidationError(
                {"valor_total": "O subtotal excede o limite permitido."}
            )
        if desconto > subtotal:
            raise ValidationError(
                {"desconto": "O desconto não pode ultrapassar o subtotal."}
            )
        return subtotal, (subtotal - desconto).quantize(
            centavos,
            rounding=ROUND_HALF_UP,
        )

    @property
    def subtotal(self):
        subtotal, _ = self.calcular_composicao_financeira(
            self.valor_agua,
            self.valor_gas,
            self.valor_aluguel,
            self.desconto,
        )
        return subtotal

    def recalcular_valor_total(self):
        _, self.valor_total = self.calcular_composicao_financeira(
            self.valor_agua,
            self.valor_gas,
            self.valor_aluguel,
            self.desconto,
        )
        return self.valor_total

    def clean(self):
        super().clean()

        erros = {}
        valores = (self.valor_agua, self.valor_gas, self.valor_total)
        if all(isinstance(valor, Decimal) for valor in valores):
            try:
                _, total_esperado = self.calcular_composicao_financeira(
                    self.valor_agua,
                    self.valor_gas,
                    self.valor_aluguel,
                    self.desconto,
                )
            except ValidationError as exc:
                erros.update(exc.message_dict)
                total_esperado = None
            if (
                total_esperado is not None
                and self.valor_total != total_esperado
            ):
                erros["valor_total"] = (
                    "O valor total deve corresponder ao subtotal menos o desconto."
                )

        if self.leitura_id is not None:
            dados_leitura = (
                Leitura.objects
                .filter(pk=self.leitura_id)
                .values("apartamento_id", "mes", "ano")
                .first()
            )
            if dados_leitura is not None and (
                dados_leitura["apartamento_id"] != self.apartamento_id
                or dados_leitura["mes"] != self.mes
                or dados_leitura["ano"] != self.ano
            ):
                erros["leitura"] = (
                    "A leitura deve pertencer ao mesmo apartamento, mês e ano "
                    "da fatura."
                )

        calculos = (
            (
                "agua",
                "água",
                self.leitura_agua_anterior,
                self.leitura_agua_atual,
                self.consumo_agua,
                self.valor_agua,
                calcular_agua,
            ),
            (
                "gas",
                "gás",
                self.leitura_gas_anterior,
                self.leitura_gas_atual,
                self.consumo_gas,
                self.valor_gas,
                lambda anterior, atual: calcular_gas(
                    anterior,
                    atual,
                    self.valor_m3_gas_emissao,
                ),
            ),
        )
        for (
            campo_recurso,
            recurso,
            leitura_anterior,
            leitura_atual,
            consumo,
            valor,
            calcular,
        ) in calculos:
            if leitura_anterior is None and leitura_atual is None:
                continue
            if leitura_anterior is None or leitura_atual is None:
                erros[f"leitura_{campo_recurso}_atual"] = (
                    f"As leituras anterior e atual de {recurso} devem ser "
                    "informadas em conjunto."
                )
                continue
            try:
                resultado = calcular(leitura_anterior, leitura_atual)
            except ValueError as exc:
                erros[f"leitura_{campo_recurso}_atual"] = str(exc)
                continue
            if consumo != resultado["consumo"]:
                erros[f"consumo_{campo_recurso}"] = (
                    f"O consumo de {recurso} não corresponde às leituras."
                )
            if valor != resultado["valor"]:
                erros[f"valor_{campo_recurso}"] = (
                    f"O valor de {recurso} não corresponde ao consumo."
                )

        if erros:
            raise ValidationError(erros)


class HistoricoStatusFatura(models.Model):
    class Acao(models.TextChoices):
        PAGAMENTO_CONFIRMADO = (
            "pagamento_confirmado",
            "Pagamento confirmado",
        )
        FATURA_CANCELADA = "fatura_cancelada", "Fatura cancelada"
        PAGAMENTO_ESTORNADO = (
            "pagamento_estornado",
            "Pagamento estornado",
        )
        FATURA_REABERTA = "fatura_reaberta", "Fatura reaberta"

    fatura = models.ForeignKey(
        Fatura,
        on_delete=models.CASCADE,
        related_name="historico_status",
    )
    status_anterior = models.CharField(
        max_length=20,
        choices=Fatura.Status.choices,
    )
    novo_status = models.CharField(
        max_length=20,
        choices=Fatura.Status.choices,
    )
    acao = models.CharField(max_length=30, choices=Acao.choices)
    motivo = models.TextField(blank=True, max_length=500)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alteracoes_status_faturas",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "historico_status_faturas"
        ordering = ["-criado_em", "-id"]

    def __str__(self):
        return (
            f"{self.get_acao_display()} - Fatura {self.fatura_id}"
        )
