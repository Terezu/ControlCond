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

    nome = models.CharField("Nome", max_length=150, blank=True)
    cnpj = models.CharField(
        "CNPJ",
        max_length=18,
        blank=True,
        validators=[validar_cnpj],
    )
    endereco = models.CharField("Endereço", max_length=255, blank=True)
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
    email = models.EmailField("E-mail", max_length=254, blank=True)

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
    observacoes_padrao = models.TextField(
        "Observações padrão",
        blank=True,
    )
    texto_rodape = models.TextField(
        "Texto de rodapé",
        blank=True,
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
            "cidade",
            "telefone",
            "email",
            "administradora_nome",
            "administradora_responsavel",
            "administradora_telefone",
            "administradora_email",
            "observacoes_padrao",
            "texto_rodape",
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
