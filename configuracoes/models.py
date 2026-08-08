from decimal import Decimal
from datetime import date

from django.core.validators import (
    FileExtensionValidator,
    MaxValueValidator,
    MinValueValidator,
    RegexValidator,
)
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db import models
from django.db.models import Q

from .validators import formatar_cep, formatar_cnpj, validar_cnpj
from condominios.models import obter_condominio_padrao_id


CHAVE_CONFIGURACAO = 1
LIMITE_VALOR_GAS = Decimal("999999.99")
COR_PRIMARIA_PADRAO = "#1F4E5F"
COR_SECUNDARIA_PADRAO = "#64748B"
COR_DESTAQUE_PADRAO = "#E8F1F4"
ESTADOS_BRASILEIROS = (
    ("AC", "Acre"),
    ("AL", "Alagoas"),
    ("AP", "Amapá"),
    ("AM", "Amazonas"),
    ("BA", "Bahia"),
    ("CE", "Ceará"),
    ("DF", "Distrito Federal"),
    ("ES", "Espírito Santo"),
    ("GO", "Goiás"),
    ("MA", "Maranhão"),
    ("MT", "Mato Grosso"),
    ("MS", "Mato Grosso do Sul"),
    ("MG", "Minas Gerais"),
    ("PA", "Pará"),
    ("PB", "Paraíba"),
    ("PR", "Paraná"),
    ("PE", "Pernambuco"),
    ("PI", "Piauí"),
    ("RJ", "Rio de Janeiro"),
    ("RN", "Rio Grande do Norte"),
    ("RS", "Rio Grande do Sul"),
    ("RO", "Rondônia"),
    ("RR", "Roraima"),
    ("SC", "Santa Catarina"),
    ("SP", "São Paulo"),
    ("SE", "Sergipe"),
    ("TO", "Tocantins"),
)


class ConfiguracaoCondominio(models.Model):
    class TipoJuros(models.TextChoices):
        DIARIO = "diario", "Diário"
        MENSAL = "mensal", "Mensal"

    condominio = models.OneToOneField(
        "condominios.Condominio",
        on_delete=models.CASCADE,
        related_name="configuracao",
        default=obter_condominio_padrao_id,
    )
    chave = models.PositiveSmallIntegerField(
        default=CHAVE_CONFIGURACAO,
        editable=False,
    )

    nome = models.CharField(
        "Nome do condomínio",
        max_length=150,
        default="ControlCond",
    )
    razao_social = models.CharField("Razão social", max_length=180, blank=True)
    cnpj = models.CharField(
        "CNPJ",
        max_length=18,
        blank=True,
        validators=[validar_cnpj],
    )
    endereco = models.CharField("Endereço", max_length=255, blank=True)
    numero = models.CharField("Número", max_length=30, blank=True)
    complemento = models.CharField("Complemento", max_length=100, blank=True)
    bairro = models.CharField("Bairro", max_length=100, blank=True)
    cep = models.CharField(
        "CEP",
        max_length=9,
        blank=True,
        validators=[
            RegexValidator(
                r"^\d{5}-\d{3}$",
                "Informe o CEP no formato 00000-000.",
            )
        ],
    )
    cidade = models.CharField("Cidade", max_length=100, blank=True)
    estado = models.CharField(
        "Estado",
        max_length=2,
        blank=True,
        choices=ESTADOS_BRASILEIROS,
    )
    telefone = models.CharField("Telefone", max_length=20, blank=True)
    celular = models.CharField("Celular", max_length=20, blank=True)
    email = models.EmailField("E-mail", max_length=254, blank=True)
    website = models.URLField("Website", blank=True)
    pais = models.CharField("País", max_length=80, default="Brasil", blank=True)
    nome_sindico = models.CharField("Nome do síndico", max_length=150, blank=True)
    administrador = models.CharField("Administrador", max_length=150, blank=True)
    mensagem_institucional_rodape = models.TextField(
        "Mensagem institucional do rodapé",
        blank=True,
    )

    administradora_nome = models.CharField(
        "Nome da administradora",
        max_length=150,
        blank=True,
    )
    administradora_responsavel = models.CharField(
        "Responsável",
        max_length=150,
        blank=True,
    )
    administradora_telefone = models.CharField(
        "Telefone",
        max_length=20,
        blank=True,
    )
    administradora_email = models.EmailField(
        "E-mail",
        max_length=254,
        blank=True,
    )

    valor_m3_gas = models.DecimalField(
        "Valor do m³ do gás",
        max_digits=8,
        decimal_places=2,
        default=Decimal("21.02"),
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(LIMITE_VALOR_GAS),
        ],
    )

    logo = models.ImageField(
        "Logo",
        upload_to="configuracoes/logos/",
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(
                allowed_extensions=["png", "jpg", "jpeg", "webp"]
            )
        ],
    )
    favicon = models.ImageField(
        "Ícone/favicon",
        upload_to="configuracoes/icones/",
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(
                allowed_extensions=["png", "jpg", "jpeg", "webp", "ico"]
            )
        ],
    )
    cor_primaria = models.CharField(
        "Cor primária",
        max_length=7,
        default=COR_PRIMARIA_PADRAO,
        validators=[
            RegexValidator(
                r"^#[0-9A-Fa-f]{6}$",
                "Informe uma cor hexadecimal no formato #RRGGBB.",
            )
        ],
    )
    cor_secundaria = models.CharField(
        "Cor secundária",
        max_length=7,
        default=COR_SECUNDARIA_PADRAO,
        validators=[
            RegexValidator(
                r"^#[0-9A-Fa-f]{6}$",
                "Informe uma cor hexadecimal no formato #RRGGBB.",
            )
        ],
    )
    cor_destaque = models.CharField(
        "Cor de destaque",
        max_length=7,
        default=COR_DESTAQUE_PADRAO,
        validators=[
            RegexValidator(
                r"^#[0-9A-Fa-f]{6}$",
                "Informe uma cor hexadecimal no formato #RRGGBB.",
            )
        ],
    )
    moeda = models.CharField("Moeda", max_length=3, default="BRL")
    dia_vencimento_padrao = models.PositiveSmallIntegerField(
        "Dia padrão de vencimento",
        default=10,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        help_text="Dia do mês utilizado como vencimento padrão.",
    )
    dias_tolerancia_pagamento = models.PositiveSmallIntegerField(
        "Dias de tolerância",
        default=0,
        validators=[MaxValueValidator(365)],
        help_text="Quantidade de dias após o vencimento sem encargos.",
    )
    dias_vencimento_padrao = models.PositiveSmallIntegerField(
        "Dias padrão para vencimento",
        default=10,
        validators=[MinValueValidator(1), MaxValueValidator(365)],
    )
    mensagem_cobranca_padrao = models.TextField(
        "Mensagem padrão de cobrança",
        blank=True,
    )
    mensagem_pagamento_antecipado = models.TextField(
        "Mensagem padrão para pagamento antecipado",
        blank=True,
    )
    percentual_multa_padrao = models.DecimalField(
        "Percentual padrão de multa",
        max_digits=6,
        decimal_places=3,
        default=Decimal("0.000"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    percentual_juros_padrao = models.DecimalField(
        "Percentual padrão de juros",
        max_digits=6,
        decimal_places=3,
        default=Decimal("0.000"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    tipo_juros = models.CharField(
        "Tipo de juros",
        max_length=7,
        choices=TipoJuros.choices,
        default=TipoJuros.MENSAL,
    )
    percentual_bonificacao_padrao = models.DecimalField(
        "Percentual padrão de bonificação",
        max_digits=6,
        decimal_places=3,
        default=Decimal("0.000"),
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(Decimal("100")),
        ],
    )
    dias_antecedencia_bonificacao = models.PositiveSmallIntegerField(
        "Dias de antecedência para bonificação",
        default=0,
        validators=[MaxValueValidator(365)],
        help_text=(
            "Quantidade de dias antes do vencimento para aplicar "
            "a bonificação."
        ),
    )
    valor_bonificacao_padrao = models.DecimalField(
        "Valor padrão da bonificação",
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    dia_bonificacao_padrao = models.PositiveSmallIntegerField(
        "Dia padrão para bonificação",
        blank=True,
        null=True,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
    )
    pix = models.CharField("PIX", max_length=255, blank=True)
    favorecido_nome = models.CharField(
        "Nome do favorecido",
        max_length=150,
        blank=True,
    )
    favorecido_documento = models.CharField(
        "CPF/CNPJ do favorecido",
        max_length=20,
        blank=True,
    )
    banco = models.CharField("Banco", max_length=100, blank=True)
    agencia = models.CharField("Agência", max_length=30, blank=True)
    conta = models.CharField("Conta", max_length=30, blank=True)
    tipo_conta = models.CharField("Tipo de conta", max_length=50, blank=True)
    codigo_barras_padrao = models.CharField(
        "Código de barras padrão",
        max_length=255,
        blank=True,
    )
    instrucoes_pagamento = models.TextField(
        "Instruções para pagamento",
        blank=True,
    )
    mensagem_cabecalho = models.TextField("Mensagem no cabeçalho", blank=True)
    observacoes_padrao = models.TextField(
        "Observações padrão",
        blank=True,
    )
    texto_rodape = models.TextField(
        "Texto de rodapé",
        blank=True,
    )
    texto_juridico = models.TextField("Texto jurídico", blank=True)
    cidade_assinatura = models.CharField(
        "Cidade utilizada na assinatura",
        max_length=100,
        blank=True,
    )
    responsavel_emissao = models.CharField(
        "Responsável pela emissão",
        max_length=150,
        blank=True,
    )
    cargo_responsavel = models.CharField(
        "Cargo do responsável",
        max_length=100,
        blank=True,
    )
    mostrar_grafico_financeiro = models.BooleanField(
        "Mostrar gráfico financeiro",
        default=True,
    )
    mostrar_ultimos_pagamentos = models.BooleanField(
        "Mostrar últimos pagamentos",
        default=True,
    )
    mostrar_ultimos_cadastros = models.BooleanField(
        "Mostrar últimos cadastros",
        default=True,
    )
    mostrar_resumo_financeiro = models.BooleanField(
        "Mostrar resumo financeiro",
        default=True,
    )

    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "configuracao_condominio"
        verbose_name = "Configuração do condomínio"
        verbose_name_plural = "Configurações do condomínio"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(valor_m3_gas__gte=0),
                name="configuracao_valor_gas_nao_negativo",
            ),
            models.CheckConstraint(
                condition=models.Q(valor_m3_gas__lte=LIMITE_VALOR_GAS),
                name="configuracao_valor_gas_no_limite",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    dia_vencimento_padrao__gte=1,
                    dia_vencimento_padrao__lte=31,
                ),
                name="configuracao_dia_vencimento_valido",
            ),
            models.CheckConstraint(
                condition=models.Q(dias_tolerancia_pagamento__lte=365),
                name="configuracao_tolerancia_no_limite",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    percentual_bonificacao_padrao__gte=0,
                    percentual_bonificacao_padrao__lte=100,
                ),
                name="configuracao_percentual_bonus_valido",
            ),
            models.CheckConstraint(
                condition=models.Q(dias_antecedencia_bonificacao__lte=365),
                name="configuracao_antecedencia_bonus_no_limite",
            ),
        ]

    def __str__(self):
        return self.nome or "Configurações do condomínio"

    def clean(self):
        super().clean()
        self.chave = CHAVE_CONFIGURACAO

        campos_texto = (
            "nome",
            "endereco",
            "numero",
            "complemento",
            "bairro",
            "cidade",
            "telefone",
            "celular",
            "email",
            "website",
            "pais",
            "nome_sindico",
            "administrador",
            "mensagem_institucional_rodape",
            "administradora_nome",
            "administradora_responsavel",
            "administradora_telefone",
            "administradora_email",
            "observacoes_padrao",
            "texto_rodape",
            "mensagem_cobranca_padrao",
            "mensagem_pagamento_antecipado",
            "pix",
            "favorecido_nome",
            "favorecido_documento",
            "banco",
            "agencia",
            "conta",
            "tipo_conta",
            "codigo_barras_padrao",
            "instrucoes_pagamento",
            "mensagem_cabecalho",
            "texto_juridico",
            "cidade_assinatura",
            "responsavel_emissao",
            "cargo_responsavel",
        )
        for campo in campos_texto:
            valor = getattr(self, campo)
            if isinstance(valor, str):
                setattr(self, campo, valor.strip())

        if isinstance(self.cnpj, str):
            self.cnpj = formatar_cnpj(self.cnpj)
        if isinstance(self.cep, str):
            self.cep = formatar_cep(self.cep)
        if isinstance(self.estado, str):
            self.estado = self.estado.strip().upper()
        if isinstance(self.moeda, str):
            self.moeda = self.moeda.strip().upper()


class ConfiguracaoGlobal(models.Model):
    """Parâmetros técnicos não secretos da plataforma."""

    chave = models.PositiveSmallIntegerField(default=1, unique=True, editable=False)
    dias_retencao_padrao = models.PositiveIntegerField(
        "Retenção padrão (dias)",
        default=365,
        validators=[MinValueValidator(1), MaxValueValidator(3650)],
    )
    mensagem_manutencao = models.TextField(
        "Mensagem de manutenção",
        blank=True,
    )
    modo_manutencao = models.BooleanField(
        "Modo de manutenção",
        default=False,
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "configuracao_global"
        verbose_name = "Configuração global"
        verbose_name_plural = "Configurações globais"

    def __str__(self):
        return "Configurações globais do ControlCond"

    def clean(self):
        super().clean()
        self.chave = 1
        self.mensagem_manutencao = self.mensagem_manutencao.strip()


class AuditoriaConfiguracao(models.Model):
    class Tipo(models.TextChoices):
        INSTITUCIONAL = "institucional", "Institucional"
        OPERACIONAL = "operacional", "Operacional"
        GLOBAL = "global", "Global"

    executor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="auditorias_configuracao",
    )
    condominio = models.ForeignKey(
        "condominios.Condominio",
        on_delete=models.PROTECT,
        related_name="auditorias_configuracao",
        blank=True,
        null=True,
    )
    cargo = models.CharField(max_length=30)
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    valores_anteriores = models.JSONField(default=dict)
    valores_novos = models.JSONField(default=dict)
    origem = models.CharField(max_length=50, default="painel")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "auditoria_configuracoes"
        ordering = ["-criado_em", "-id"]
        verbose_name = "Auditoria de configuração"
        verbose_name_plural = "Auditorias de configurações"


class RegraVigenciaMixin(models.Model):
    data_inicio_vigencia = models.DateField("Início da vigência")
    data_fim_vigencia = models.DateField(
        "Fim da vigência",
        blank=True,
        null=True,
    )
    ativa = models.BooleanField(
        "Disponível administrativamente",
        default=True,
    )
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        if (
            self.data_fim_vigencia
            and self.data_fim_vigencia < self.data_inicio_vigencia
        ):
            raise ValidationError(
                {"data_fim_vigencia": "A data final não pode ser anterior à inicial."}
            )
        consulta = type(self).objects.exclude(pk=self.pk).filter(
            condominio_id=self.condominio_id,
            data_inicio_vigencia__lte=(self.data_fim_vigencia or date.max)
        ).filter(
            Q(data_fim_vigencia__isnull=True)
            | Q(data_fim_vigencia__gte=self.data_inicio_vigencia)
        )
        if consulta.exists():
            raise ValidationError(
                "O período de vigência se sobrepõe a outro registro."
            )


class TabelaTarifariaAgua(RegraVigenciaMixin):
    condominio = models.ForeignKey(
        "condominios.Condominio",
        on_delete=models.PROTECT,
        related_name="tabelas_agua",
        default=obter_condominio_padrao_id,
    )
    nome = models.CharField(max_length=150)

    class Meta:
        db_table = "tabelas_tarifarias_agua"
        ordering = ["-data_inicio_vigencia", "-id"]
        verbose_name = "Tabela tarifária de água"
        verbose_name_plural = "Tabelas tarifárias de água"

    def __str__(self):
        return self.nome

    @property
    def foi_utilizada(self):
        return self.faturas_utilizadas.exists()


class FaixaTarifaAgua(models.Model):
    tabela = models.ForeignKey(
        TabelaTarifariaAgua,
        on_delete=models.PROTECT,
        related_name="faixas",
    )
    consumo_inicial = models.PositiveIntegerField("Consumo inicial")
    consumo_final = models.PositiveIntegerField(
        "Consumo final",
        blank=True,
        null=True,
    )
    valor = models.DecimalField(
        "Valor",
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    ordem = models.PositiveSmallIntegerField()
    ativa = models.BooleanField(default=True)
    descricao = models.CharField(max_length=150, blank=True)

    class Meta:
        db_table = "faixas_tarifa_agua"
        ordering = ["ordem", "id"]
        verbose_name = "Faixa da tarifa de água"
        verbose_name_plural = "Faixas da tarifa de água"
        constraints = [
            models.UniqueConstraint(
                fields=("tabela", "ordem"),
                name="faixa_agua_ordem_unica_por_tabela",
            ),
            models.UniqueConstraint(
                fields=("tabela", "consumo_inicial", "consumo_final"),
                name="faixa_agua_intervalo_unico_por_tabela",
            ),
            models.CheckConstraint(
                condition=models.Q(valor__gte=0),
                name="faixa_agua_valor_nao_negativo",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(consumo_final__isnull=True)
                    | models.Q(consumo_final__gte=models.F("consumo_inicial"))
                ),
                name="faixa_agua_intervalo_valido",
            ),
        ]

    def __str__(self):
        final = self.consumo_final if self.consumo_final is not None else "∞"
        return f"{self.consumo_inicial}–{final} m³"

    def clean(self):
        super().clean()
        if (
            self.consumo_final is not None
            and self.consumo_final < self.consumo_inicial
        ):
            raise ValidationError(
                {"consumo_final": "O consumo final não pode ser menor que o inicial."}
            )
        # No cadastro, o inline formset valida as faixas antes de salvar a
        # tabela-pai. Nesse momento ainda não existe uma chave pela qual
        # procurar faixas persistidas; a continuidade entre os formulários é
        # validada por BaseFaixaTarifaAguaFormSet.clean().
        if self.tabela_id is None:
            return
        limite = self.consumo_final or 2**31 - 1
        sobreposta = (
            FaixaTarifaAgua.objects
            .filter(tabela_id=self.tabela_id)
            .exclude(pk=self.pk)
            .filter(consumo_inicial__lte=limite)
            .filter(
                Q(consumo_final__isnull=True)
                | Q(consumo_final__gte=self.consumo_inicial)
            )
        )
        if sobreposta.exists():
            raise ValidationError("Existem faixas de consumo sobrepostas.")

    def save(self, *args, **kwargs):
        if self.tabela_id is None:
            from django.db.models import Q
            from condominios.models import Condominio
            hoje = date.today()
            condominio = Condominio.objects.order_by("id").first()
            self.tabela = (
                TabelaTarifariaAgua.objects
                .filter(
                    condominio=condominio,
                    ativa=True,
                    data_inicio_vigencia__lte=hoje,
                )
                .filter(
                    Q(data_fim_vigencia__isnull=True)
                    | Q(data_fim_vigencia__gte=hoje)
                )
                .order_by("-data_inicio_vigencia")
                .first()
            )
            if self.tabela is None:
                raise ValidationError("Nenhuma tabela de água vigente.")
        return super().save(*args, **kwargs)


class TarifaGas(RegraVigenciaMixin):
    condominio = models.ForeignKey(
        "condominios.Condominio",
        on_delete=models.PROTECT,
        related_name="tarifas_gas",
        default=obter_condominio_padrao_id,
    )
    nome = models.CharField(max_length=150)
    valor_por_m3 = models.DecimalField(
        "Valor por m³",
        max_digits=8,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(LIMITE_VALOR_GAS),
        ],
    )

    class Meta:
        db_table = "tarifas_gas"
        ordering = ["-data_inicio_vigencia", "-id"]
        verbose_name = "Tarifa de gás"
        verbose_name_plural = "Tarifas de gás"
        constraints = [
            models.CheckConstraint(
                condition=Q(valor_por_m3__gte=0),
                name="tarifa_gas_valor_nao_negativo",
            ),
        ]

    def __str__(self):
        return self.nome

    @property
    def foi_utilizada(self):
        return self.faturas_utilizadas.exists()
