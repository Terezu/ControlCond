import calendar
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Round

from apartamentos.models import Apartamento
from calculos.services import calcular_agua, calcular_gas
from configuracoes.models import ConfiguracaoCondominio, LIMITE_VALOR_GAS
from leituras.models import Leitura


ANO_MAXIMO = 9999
LIMITE_VALOR_FINANCEIRO = Decimal("99999999.99")


class Fatura(models.Model):
    TipoJuros = ConfiguracaoCondominio.TipoJuros

    class OrigemBonificacao(models.TextChoices):
        CONDOMINIO = (
            "condominio",
            "Usar bonificação padrão do condomínio",
        )
        ESPECIFICA = "especifica", "Definir bonificação específica"
        NENHUMA = "nenhuma", "Não aplicar bonificação"

    class TipoBonificacao(models.TextChoices):
        PERCENTUAL = "percentual", "Percentual"
        VALOR_FIXO = "valor_fixo", "Valor fixo"
        NENHUMA = "nenhuma", "Nenhuma"

    class Status(models.TextChoices):
        PENDENTE = "pendente", "Pendente"
        PAGA = "paga", "Paga"
        CANCELADA = "cancelada", "Cancelada"

    class FormaPagamento(models.TextChoices):
        PIX = "pix", "PIX"
        BOLETO = "boleto", "Boleto"
        TRANSFERENCIA = "transferencia", "Transferência bancária"
        DINHEIRO = "dinheiro", "Dinheiro"
        CARTAO = "cartao", "Cartão"
        OUTRO = "outro", "Outro"
        NAO_INFORMADA = "nao_informada", "Não informada"

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
    tabela_agua_utilizada = models.ForeignKey(
        "configuracoes.TabelaTarifariaAgua",
        on_delete=models.PROTECT,
        related_name="faturas_utilizadas",
        blank=True,
        null=True,
    )
    faixa_agua_utilizada = models.ForeignKey(
        "configuracoes.FaixaTarifaAgua",
        on_delete=models.PROTECT,
        related_name="faturas_utilizadas",
        blank=True,
        null=True,
    )
    tarifa_gas_utilizada = models.ForeignKey(
        "configuracoes.TarifaGas",
        on_delete=models.PROTECT,
        related_name="faturas_utilizadas",
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
    valor_condominio = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(LIMITE_VALOR_FINANCEIRO),
        ],
    )
    valor_iptu = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(LIMITE_VALOR_FINANCEIRO),
        ],
    )
    valor_bonificacao = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(LIMITE_VALOR_FINANCEIRO),
        ],
    )
    dia_limite_bonificacao = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
    )
    valor_outros = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(-LIMITE_VALOR_FINANCEIRO),
            MaxValueValidator(LIMITE_VALOR_FINANCEIRO),
        ],
    )
    observacao_outros = models.CharField(max_length=255, blank=True)
    valor_pago = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(LIMITE_VALOR_FINANCEIRO),
        ],
    )
    bonificacao_aplicada = models.BooleanField(default=False)
    valor_multa_aplicada = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    valor_juros_aplicados = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    valor_bonificacao_aplicada = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    valor_original = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    valor_final = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    percentual_multa_emissao = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        default=Decimal("0.000"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    percentual_juros_emissao = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        default=Decimal("0.000"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    tipo_juros_emissao = models.CharField(
        max_length=7,
        choices=TipoJuros.choices,
        default=TipoJuros.MENSAL,
    )
    dias_tolerancia_emissao = models.PositiveSmallIntegerField(default=0)
    percentual_bonificacao_emissao = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        default=Decimal("0.000"),
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(Decimal("100")),
        ],
    )
    origem_bonificacao_emissao = models.CharField(
        max_length=12,
        choices=OrigemBonificacao.choices,
        default=OrigemBonificacao.CONDOMINIO,
    )
    tipo_bonificacao_emissao = models.CharField(
        max_length=10,
        choices=TipoBonificacao.choices,
        default=TipoBonificacao.NENHUMA,
    )
    valor_bonificacao_fixa_emissao = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(LIMITE_VALOR_FINANCEIRO),
        ],
    )
    dias_antecedencia_bonificacao_emissao = (
        models.PositiveSmallIntegerField(default=0)
    )
    forma_pagamento = models.CharField(
        max_length=20,
        choices=FormaPagamento.choices,
        blank=True,
    )
    observacoes_pagamento = models.TextField(blank=True, max_length=500)

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
    data_vencimento = models.DateField()
    data_limite_bonificacao = models.DateField(blank=True, null=True)
    data_pagamento = models.DateField(blank=True, null=True)
    dias_em_atraso = models.PositiveIntegerField(default=0)
    dias_antecipados = models.PositiveIntegerField(default=0)
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
        indexes = [
            models.Index(
                fields=["ano", "mes", "status", "data_vencimento"],
                name="fatura_comp_status_venc_idx",
            ),
        ]

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
                condition=models.Q(valor_original__gte=0),
                name="fatura_valor_original_nao_negativo",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(valor_final__isnull=True)
                    | models.Q(valor_final__gte=0)
                ),
                name="fatura_valor_final_nao_negativo",
            ),
            models.CheckConstraint(
                condition=models.Q(valor_multa_aplicada__gte=0),
                name="fatura_multa_aplicada_nao_negativa",
            ),
            models.CheckConstraint(
                condition=models.Q(valor_juros_aplicados__gte=0),
                name="fatura_juros_aplicados_nao_negativos",
            ),
            models.CheckConstraint(
                condition=models.Q(valor_bonificacao_aplicada__gte=0),
                name="fatura_bonus_aplicado_nao_negativo",
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
                condition=models.Q(valor_condominio__gte=0),
                name="fatura_condominio_nao_negativo",
            ),
            models.CheckConstraint(
                condition=models.Q(valor_iptu__gte=0),
                name="fatura_iptu_nao_negativo",
            ),
            models.CheckConstraint(
                condition=models.Q(valor_bonificacao__gte=0),
                name="fatura_bonificacao_nao_negativa",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    percentual_bonificacao_emissao__gte=0,
                    percentual_bonificacao_emissao__lte=100,
                ),
                name="fatura_bonus_percentual_emissao_valido",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    valor_bonificacao_fixa_emissao__gte=0,
                ),
                name="fatura_bonus_fixo_emissao_nao_negativo",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(dia_limite_bonificacao__isnull=True)
                    | models.Q(
                        dia_limite_bonificacao__gte=1,
                        dia_limite_bonificacao__lte=31,
                    )
                ),
                name="fatura_dia_bonificacao_valido",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(valor_bonificacao=0)
                    | models.Q(dia_limite_bonificacao__isnull=False)
                    | models.Q(data_limite_bonificacao__isnull=False)
                ),
                name="fatura_bonificacao_com_dia",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(valor_outros=0)
                    | ~models.Q(observacao_outros="")
                ),
                name="fatura_outros_com_observacao",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    desconto__lte=(
                        models.F("valor_agua")
                        + models.F("valor_gas")
                        + models.F("valor_aluguel")
                        + models.F("valor_condominio")
                        + models.F("valor_iptu")
                        + models.F("valor_outros")
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
                        + models.F("valor_condominio")
                        + models.F("valor_iptu")
                        + models.F("valor_outros")
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
        valor_condominio,
        valor_iptu,
        valor_outros,
        desconto,
    ):
        centavos = Decimal("0.01")
        valores = tuple(
            valor.quantize(centavos, rounding=ROUND_HALF_UP)
            for valor in (
                valor_agua,
                valor_gas,
                valor_aluguel,
                valor_condominio,
                valor_iptu,
                valor_outros,
                desconto,
            )
        )
        (
            valor_agua,
            valor_gas,
            valor_aluguel,
            valor_condominio,
            valor_iptu,
            valor_outros,
            desconto,
        ) = valores
        subtotal = (
            valor_agua
            + valor_gas
            + valor_aluguel
            + valor_condominio
            + valor_iptu
            + valor_outros
        ).quantize(
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
            self.valor_condominio,
            self.valor_iptu,
            self.valor_outros,
            self.desconto,
        )
        return subtotal

    def recalcular_valor_total(self):
        _, self.valor_total = self.calcular_composicao_financeira(
            self.valor_agua,
            self.valor_gas,
            self.valor_aluguel,
            self.valor_condominio,
            self.valor_iptu,
            self.valor_outros,
            self.desconto,
        )
        return self.valor_total

    @property
    def valor_com_bonificacao(self):
        return (self.valor_total - self.valor_bonificacao_configurada).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    @property
    def possui_bonificacao(self):
        return (
            self.origem_bonificacao_emissao
            != self.OrigemBonificacao.NENHUMA
            and self.tipo_bonificacao_emissao
            != self.TipoBonificacao.NENHUMA
            and self.valor_bonificacao_configurada > 0
        )

    @property
    def descricao_origem_bonificacao(self):
        return {
            self.OrigemBonificacao.CONDOMINIO: "Padrão do condomínio",
            self.OrigemBonificacao.ESPECIFICA: "Específica da fatura",
            self.OrigemBonificacao.NENHUMA: "Nenhuma",
        }[self.origem_bonificacao_emissao]

    @property
    def valor_bonificacao_configurada(self):
        if (
            self.tipo_bonificacao_emissao
            == self.TipoBonificacao.PERCENTUAL
        ):
            valor = (
                self.valor_total
                * self.percentual_bonificacao_emissao
                / Decimal("100")
            )
        elif (
            self.tipo_bonificacao_emissao
            == self.TipoBonificacao.VALOR_FIXO
        ):
            valor = self.valor_bonificacao_fixa_emissao
        else:
            valor = Decimal("0.00")
        return min(valor, self.valor_total).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    def calcular_data_limite_bonificacao_legada(self):
        if not self.dia_limite_bonificacao:
            return None
        ultimo_dia = calendar.monthrange(self.ano, self.mes)[1]
        return date(
            self.ano,
            self.mes,
            min(self.dia_limite_bonificacao, ultimo_dia),
        )

    def _preencher_snapshots_emissao(self):
        configuracao = (
            ConfiguracaoCondominio.objects
            .filter(condominio_id=self.apartamento.condominio_id)
            .first()
        )
        if configuracao is not None:
            self.percentual_multa_emissao = (
                configuracao.percentual_multa_padrao
            )
            self.percentual_juros_emissao = (
                configuracao.percentual_juros_padrao
            )
            self.tipo_juros_emissao = configuracao.tipo_juros
            self.dias_tolerancia_emissao = (
                configuracao.dias_tolerancia_pagamento
            )
            self.dias_antecedencia_bonificacao_emissao = (
                configuracao.dias_antecedencia_bonificacao
            )
        if (
            self.valor_bonificacao > 0
            and self.origem_bonificacao_emissao
            == self.OrigemBonificacao.CONDOMINIO
        ):
            self.origem_bonificacao_emissao = (
                self.OrigemBonificacao.ESPECIFICA
            )
            self.tipo_bonificacao_emissao = (
                self.TipoBonificacao.VALOR_FIXO
            )
            self.valor_bonificacao_fixa_emissao = self.valor_bonificacao
            self.percentual_bonificacao_emissao = Decimal("0.000")
        elif (
            self.origem_bonificacao_emissao
            == self.OrigemBonificacao.CONDOMINIO
        ):
            self.percentual_bonificacao_emissao = (
                configuracao.percentual_bonificacao_padrao
                if configuracao is not None
                else Decimal("0.000")
            )
            self.tipo_bonificacao_emissao = (
                self.TipoBonificacao.PERCENTUAL
                if self.percentual_bonificacao_emissao > 0
                else self.TipoBonificacao.NENHUMA
            )
            if self.percentual_bonificacao_emissao <= 0:
                self.origem_bonificacao_emissao = (
                    self.OrigemBonificacao.NENHUMA
                )
        if self.data_vencimento is None:
            dia_vencimento = (
                configuracao.dia_vencimento_padrao
                if configuracao is not None
                else ConfiguracaoCondominio._meta.get_field(
                    "dia_vencimento_padrao"
                ).default
            )
            ultimo_dia = calendar.monthrange(self.ano, self.mes)[1]
            self.data_vencimento = date(
                self.ano,
                self.mes,
                min(dia_vencimento, ultimo_dia),
            )
        if self.data_limite_bonificacao is None:
            if self.possui_bonificacao and not (
                self.valor_bonificacao > 0
                and self.dia_limite_bonificacao
            ):
                from datetime import timedelta
                self.data_limite_bonificacao = (
                    self.data_vencimento
                    - timedelta(
                        days=self.dias_antecedencia_bonificacao_emissao
                    )
                )
            elif self.valor_bonificacao > 0:
                self.data_limite_bonificacao = (
                    self.calcular_data_limite_bonificacao_legada()
                )
        self.valor_original = (
            self.valor_total + self.desconto
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    def save(self, *args, **kwargs):
        if self._state.adding:
            self._preencher_snapshots_emissao()
        elif self.pk:
            campos_congelados = (
                "data_vencimento",
                "data_limite_bonificacao",
                "data_pagamento",
                "dias_em_atraso",
                "dias_antecipados",
                "valor_multa_aplicada",
                "valor_juros_aplicados",
                "bonificacao_aplicada",
                "valor_bonificacao_aplicada",
                "origem_bonificacao_emissao",
                "tipo_bonificacao_emissao",
                "percentual_bonificacao_emissao",
                "valor_bonificacao_fixa_emissao",
                "valor_original",
                "valor_final",
                "valor_pago",
                "forma_pagamento",
                "observacoes_pagamento",
            )
            anterior = (
                type(self).objects
                .filter(pk=self.pk)
                .values("status", *campos_congelados)
                .first()
            )
            if (
                anterior
                and anterior["status"] == self.Status.PAGA
                and anterior["valor_final"] is not None
                and self.status == self.Status.PAGA
                and any(
                    getattr(self, campo) != anterior[campo]
                    for campo in campos_congelados
                )
            ):
                raise ValidationError(
                    "Os dados financeiros de uma fatura paga "
                    "não podem ser alterados."
                )
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()

        erros = {}
        if self.apartamento_id:
            condominio_id = self.apartamento.condominio_id
            if (
                self.tabela_agua_utilizada_id
                and self.tabela_agua_utilizada.condominio_id != condominio_id
            ):
                erros["tabela_agua_utilizada"] = (
                    "A tabela deve pertencer ao condomínio da fatura."
                )
            if (
                self.tarifa_gas_utilizada_id
                and self.tarifa_gas_utilizada.condominio_id != condominio_id
            ):
                erros["tarifa_gas_utilizada"] = (
                    "A tarifa deve pertencer ao condomínio da fatura."
                )
            if (
                self.faixa_agua_utilizada_id
                and self.tabela_agua_utilizada_id
                and self.faixa_agua_utilizada.tabela_id
                != self.tabela_agua_utilizada_id
            ):
                erros["faixa_agua_utilizada"] = (
                    "A faixa deve pertencer à tabela utilizada."
                )
        valores = (self.valor_agua, self.valor_gas, self.valor_total)
        if all(isinstance(valor, Decimal) for valor in valores):
            try:
                _, total_esperado = self.calcular_composicao_financeira(
                    self.valor_agua,
                    self.valor_gas,
                    self.valor_aluguel,
                    self.valor_condominio,
                    self.valor_iptu,
                    self.valor_outros,
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

        if self.valor_outros and not self.observacao_outros.strip():
            erros["observacao_outros"] = (
                "Informe a observação quando Outros for diferente de zero."
            )
        if (
            isinstance(self.valor_bonificacao, Decimal)
            and self.valor_bonificacao > 0
            and self.data_limite_bonificacao is None
        ):
            erros["data_limite_bonificacao"] = (
                "A bonificação deve possuir uma data limite."
            )
        if (
            isinstance(self.valor_bonificacao, Decimal)
            and isinstance(self.valor_total, Decimal)
            and self.valor_bonificacao > self.valor_total
        ):
            erros["valor_bonificacao"] = (
                "A bonificação não pode ultrapassar o valor normal da fatura."
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
                lambda anterior, atual: calcular_agua(
                    anterior,
                    atual,
                    self.mes,
                    self.ano,
                    condominio=self.apartamento.condominio,
                ),
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
            # A água usa tabela global versionável. Depois da emissão, seu
            # valor persistido é o snapshot da tarifa daquele mês e não pode
            # ser invalidado por alterações futuras nas faixas. Na criação,
            # e sempre para o gás (que possui tarifa própria na fatura), a
            # conferência financeira continua integral.
            if (
                valor != resultado["valor"]
                and (
                    campo_recurso == "gas"
                    or self._state.adding
                )
            ):
                erros[f"valor_{campo_recurso}"] = (
                    f"O valor de {recurso} não corresponde ao consumo."
                )

        if erros:
            raise ValidationError(erros)


class HistoricoFinanceiroFatura(models.Model):
    ROTULOS_VALORES = {
        "status": "Status",
        "valor_agua": "Água",
        "valor_gas": "Gás",
        "valor_aluguel": "Aluguel",
        "valor_condominio": "Condomínio",
        "valor_iptu": "IPTU",
        "valor_outros": "Outros",
        "desconto": "Desconto",
        "valor_bonificacao": "Bonificação configurada",
        "valor_original": "Valor original",
        "valor_total": "Valor da fatura",
        "valor_multa_aplicada": "Multa aplicada",
        "valor_juros_aplicados": "Juros aplicados",
        "valor_bonificacao_aplicada": "Bonificação aplicada",
        "valor_final": "Valor final",
        "valor_pago": "Valor pago",
        "data_vencimento": "Vencimento",
        "data_pagamento": "Pagamento",
        "dias_em_atraso": "Dias em atraso",
        "dias_antecipados": "Dias antecipados",
        "forma_pagamento": "Forma de pagamento",
    }

    class Acao(models.TextChoices):
        FATURA_CRIADA = "fatura_criada", "Fatura criada"
        PAGAMENTO_CONFIRMADO = (
            "pagamento_confirmado",
            "Pagamento confirmado",
        )
        VALORES_FINANCEIROS_ALTERADOS = (
            "valores_financeiros_alterados",
            "Valores financeiros alterados",
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
        related_name="historico_financeiro",
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
    valores_anteriores = models.JSONField(default=dict, blank=True)
    valores_novos = models.JSONField(default=dict, blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alteracoes_financeiras_faturas",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "historico_status_faturas"
        ordering = ["-criado_em", "-id"]

    def __str__(self):
        return (
            f"{self.get_acao_display()} - Fatura {self.fatura_id}"
        )

    @property
    def alteracoes_financeiras(self):
        campos = dict.fromkeys(
            (
                *self.valores_anteriores.keys(),
                *self.valores_novos.keys(),
            )
        )
        alteracoes = []
        for campo in campos:
            anterior = self.valores_anteriores.get(campo)
            novo = self.valores_novos.get(campo)
            if anterior == novo and self.valores_anteriores:
                continue
            alteracoes.append(
                {
                    "campo": self.ROTULOS_VALORES.get(campo, campo),
                    "anterior": anterior,
                    "novo": novo,
                }
            )
        return tuple(alteracoes)
