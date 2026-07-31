from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.functions import Trim


class Pessoa(models.Model):
    class Situacao(models.TextChoices):
        ATIVA = "ativa", "Ativa"
        INATIVA = "inativa", "Inativa"

    condominio = models.ForeignKey(
        "condominios.Condominio",
        on_delete=models.PROTECT,
        related_name="pessoas",
    )
    nome_completo = models.CharField("Nome completo", max_length=150)
    cpf = models.CharField("CPF", max_length=11, unique=True)
    rg = models.CharField("RG", max_length=30, blank=True, null=True)
    email = models.EmailField("E-mail", max_length=254)
    telefone = models.CharField(max_length=20)
    data_nascimento = models.DateField(
        "Data de nascimento", blank=True, null=True
    )
    observacoes = models.TextField("Observações", blank=True, null=True)
    situacao = models.CharField(
        max_length=7,
        choices=Situacao.choices,
        default=Situacao.ATIVA,
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "pessoas"
        ordering = ["nome_completo", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    ~Q(nome_completo="")
                    & Q(nome_completo=Trim("nome_completo"))
                ),
                name="pessoa_nome_valido",
            ),
            models.CheckConstraint(
                condition=Q(cpf__regex=r"^[0-9]{11}$"),
                name="pessoa_cpf_normalizado",
            ),
        ]

    def __str__(self):
        return self.nome_completo

    @property
    def cpf_formatado(self):
        if len(self.cpf) != 11 or not self.cpf.isdigit():
            return self.cpf
        return (
            f"{self.cpf[:3]}.{self.cpf[3:6]}.{self.cpf[6:9]}"
            f"-{self.cpf[9:]}"
        )

    def clean(self):
        super().clean()
        self.nome_completo = (self.nome_completo or "").strip()
        self.cpf = "".join(
            caractere for caractere in str(self.cpf or "")
            if caractere.isdigit()
        )
        self.rg = (self.rg or "").strip() or None
        self.email = (self.email or "").strip().lower()
        self.telefone = (self.telefone or "").strip()
        self.observacoes = (self.observacoes or "").strip() or None
        if not self.nome_completo:
            raise ValidationError(
                {"nome_completo": "Informe o nome completo."}
            )


class VinculoPessoaApartamento(models.Model):
    class Tipo(models.TextChoices):
        PROPRIETARIO = "proprietario", "Proprietário"
        MORADOR = "morador", "Morador"
        INQUILINO = "inquilino", "Inquilino"
        RESPONSAVEL_FINANCEIRO = (
            "responsavel_financeiro",
            "Responsável financeiro",
        )

    pessoa = models.ForeignKey(
        Pessoa,
        on_delete=models.PROTECT,
        related_name="vinculos_apartamentos",
    )
    apartamento = models.ForeignKey(
        "apartamentos.Apartamento",
        on_delete=models.PROTECT,
        related_name="vinculos_pessoas",
    )
    tipo = models.CharField(max_length=24, choices=Tipo.choices)
    data_inicio = models.DateField("Data de início")
    data_fim = models.DateField("Data de fim", blank=True, null=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "vinculos_pessoas_apartamentos"
        ordering = ["tipo", "-ativo", "-data_inicio", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(data_fim__isnull=True) | Q(data_fim__gte=models.F("data_inicio")),
                name="vinculo_periodo_valido",
            ),
            models.CheckConstraint(
                condition=Q(ativo=True, data_fim__isnull=True) | Q(ativo=False),
                name="vinculo_ativo_sem_data_fim",
            ),
            models.UniqueConstraint(
                fields=["pessoa", "apartamento", "tipo"],
                condition=Q(ativo=True),
                name="vinculo_ativo_unico_por_pessoa_tipo",
            ),
            models.UniqueConstraint(
                fields=["apartamento"],
                condition=Q(
                    ativo=True,
                    tipo="responsavel_financeiro",
                ),
                name="responsavel_financeiro_ativo_unico",
            ),
        ]

    def __str__(self):
        return (
            f"{self.pessoa} — {self.get_tipo_display()} — "
            f"{self.apartamento}"
        )

    def clean(self):
        super().clean()
        if (
            self.pessoa_id
            and self.apartamento_id
            and self.pessoa.condominio_id != self.apartamento.condominio_id
        ):
            raise ValidationError(
                "Pessoa e apartamento devem pertencer ao mesmo condomínio."
            )
        if self.ativo and self.data_fim is not None:
            raise ValidationError(
                {"data_fim": "Um vínculo ativo não pode possuir data de fim."}
            )
        if self.data_fim and self.data_fim < self.data_inicio:
            raise ValidationError(
                {"data_fim": "A data de fim não pode anteceder a data de início."}
            )
