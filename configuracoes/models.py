from decimal import Decimal

from django.core.validators import (
    FileExtensionValidator,
    MaxValueValidator,
    MinValueValidator,
    RegexValidator,
)
from django.db import models

from .validators import formatar_cep, formatar_cnpj, validar_cnpj


CHAVE_CONFIGURACAO = 1
LIMITE_VALOR_GAS = Decimal("999999.99")
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
    chave = models.PositiveSmallIntegerField(
        default=CHAVE_CONFIGURACAO,
        editable=False,
        unique=True,
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
        default="#1F4E5F",
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
        default="#64748B",
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
        default="#E8F1F4",
        validators=[
            RegexValidator(
                r"^#[0-9A-Fa-f]{6}$",
                "Informe uma cor hexadecimal no formato #RRGGBB.",
            )
        ],
    )
    moeda = models.CharField("Moeda", max_length=3, default="BRL")
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
                condition=models.Q(chave=CHAVE_CONFIGURACAO),
                name="configuracao_condominio_registro_unico",
            ),
            models.CheckConstraint(
                condition=models.Q(valor_m3_gas__gte=0),
                name="configuracao_valor_gas_nao_negativo",
            ),
            models.CheckConstraint(
                condition=models.Q(valor_m3_gas__lte=LIMITE_VALOR_GAS),
                name="configuracao_valor_gas_no_limite",
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


class FaixaTarifaAgua(models.Model):
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
    ordem = models.PositiveSmallIntegerField(unique=True)
    ativa = models.BooleanField(default=True)

    class Meta:
        db_table = "faixas_tarifa_agua"
        ordering = ["ordem", "id"]
        verbose_name = "Faixa da tarifa de água"
        verbose_name_plural = "Faixas da tarifa de água"
        constraints = [
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
