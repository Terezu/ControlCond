from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class Contrato(models.Model):
    class Situacao(models.TextChoices):
        FUTURO = "futuro", "Futuro"
        ATIVO = "ativo", "Ativo"
        ENCERRADO = "encerrado", "Encerrado"
        RESCINDIDO = "rescindido", "Rescindido"

    condominio = models.ForeignKey(
        "condominios.Condominio",
        on_delete=models.PROTECT,
        related_name="contratos",
    )
    apartamento = models.ForeignKey(
        "apartamentos.Apartamento",
        on_delete=models.PROTECT,
        related_name="contratos",
    )
    pessoa_contratante = models.ForeignKey(
        "pessoas.Pessoa",
        on_delete=models.PROTECT,
        related_name="contratos_como_contratante",
    )
    responsavel_financeiro = models.ForeignKey(
        "pessoas.Pessoa",
        on_delete=models.PROTECT,
        related_name="contratos_como_responsavel_financeiro",
    )
    data_inicio = models.DateField("Data de início")
    data_termino = models.DateField("Data de término")
    situacao = models.CharField(
        max_length=10,
        choices=Situacao.choices,
        editable=False,
        default=Situacao.FUTURO,
    )
    data_rescisao = models.DateField(
        "Data da rescisão", blank=True, null=True
    )
    justificativa_rescisao = models.TextField(
        "Justificativa da rescisão", blank=True, null=True
    )
    usuario_rescisao = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="contratos_rescindidos",
        blank=True,
        null=True,
    )
    rescindido_em = models.DateTimeField(blank=True, null=True)
    observacoes = models.TextField(blank=True, null=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "contratos"
        ordering = ["data_termino", "apartamento__bloco", "apartamento__numero"]
        constraints = [
            models.CheckConstraint(
                condition=Q(data_termino__gt=F("data_inicio")),
                name="contrato_periodo_valido",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        situacao="rescindido",
                        data_rescisao__isnull=False,
                        justificativa_rescisao__isnull=False,
                        usuario_rescisao__isnull=False,
                        rescindido_em__isnull=False,
                    )
                    | ~Q(situacao="rescindido")
                ),
                name="contrato_rescisao_auditada",
            ),
        ]

    def __str__(self):
        return f"Contrato {self.apartamento} · {self.data_inicio:%d/%m/%Y}"

    def calcular_situacao(self, hoje=None):
        if self.data_rescisao or self.rescindido_em:
            return self.Situacao.RESCINDIDO
        hoje = hoje or timezone.localdate()
        if hoje < self.data_inicio:
            return self.Situacao.FUTURO
        if hoje > self.data_termino:
            return self.Situacao.ENCERRADO
        return self.Situacao.ATIVO

    @property
    def dias_restantes(self):
        if self.calcular_situacao() != self.Situacao.ATIVO:
            return None
        return (self.data_termino - timezone.localdate()).days

    @property
    def proximo_vencimento(self):
        dias = self.dias_restantes
        return dias is not None and 0 <= dias <= 45

    def pode_ser_rescindido(self, hoje=None):
        return self.calcular_situacao(hoje) in {
            self.Situacao.ATIVO,
            self.Situacao.FUTURO,
        }

    def clean(self):
        super().clean()
        if self.data_inicio and self.data_termino:
            if self.data_termino <= self.data_inicio:
                raise ValidationError(
                    {"data_termino": "A data de término deve ser posterior à data de início."}
                )
        ids = {
            self.condominio_id,
            getattr(self.apartamento, "condominio_id", None)
            if self.apartamento_id else None,
            getattr(self.pessoa_contratante, "condominio_id", None)
            if self.pessoa_contratante_id else None,
            getattr(self.responsavel_financeiro, "condominio_id", None)
            if self.responsavel_financeiro_id else None,
        }
        ids.discard(None)
        if len(ids) > 1:
            raise ValidationError(
                "Contrato, apartamento e pessoas devem pertencer ao mesmo condomínio."
            )
        self.observacoes = (self.observacoes or "").strip() or None
        self.situacao = self.calcular_situacao()

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Contratos não podem ser excluídos; o histórico deve ser preservado."
        )


class VinculoFinanceiroContrato(models.Model):
    contrato = models.OneToOneField(
        Contrato,
        on_delete=models.PROTECT,
        related_name="dependencia_vinculo_financeiro",
    )
    vinculo = models.ForeignKey(
        "pessoas.VinculoPessoaApartamento",
        on_delete=models.PROTECT,
        related_name="dependencias_contratos",
    )
    criado_pelo_contrato = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "vinculos_financeiros_contratos"


class AuditoriaRescisaoContrato(models.Model):
    contrato = models.OneToOneField(
        Contrato,
        on_delete=models.PROTECT,
        related_name="auditoria_rescisao",
    )
    condominio = models.ForeignKey(
        "condominios.Condominio",
        on_delete=models.PROTECT,
        related_name="auditorias_rescisoes_contratos",
    )
    apartamento = models.ForeignKey(
        "apartamentos.Apartamento",
        on_delete=models.PROTECT,
        related_name="auditorias_rescisoes_contratos",
    )
    executor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="auditorias_rescisoes_contratos",
    )
    responsavel_financeiro = models.ForeignKey(
        "pessoas.Pessoa",
        on_delete=models.PROTECT,
        related_name="auditorias_rescisoes_como_responsavel",
    )
    vinculo_financeiro_encerrado = models.ForeignKey(
        "pessoas.VinculoPessoaApartamento",
        on_delete=models.PROTECT,
        related_name="auditorias_encerramento_por_rescisao",
        blank=True,
        null=True,
    )
    situacao_anterior = models.CharField(
        max_length=10, choices=Contrato.Situacao.choices
    )
    situacao_posterior = models.CharField(
        max_length=10, choices=Contrato.Situacao.choices
    )
    justificativa = models.TextField()
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "auditorias_rescisoes_contratos"
        ordering = ["-criado_em", "-id"]
