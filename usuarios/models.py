from django.conf import settings
from django.db import models
import uuid


class AuditoriaAcesso(models.Model):
    executor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="auditorias_acesso_executadas",
    )
    usuario_afetado = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="auditorias_acesso_recebidas",
    )
    condominio = models.ForeignKey(
        "condominios.Condominio",
        on_delete=models.PROTECT,
        related_name="auditorias_acesso",
    )
    acao = models.CharField(max_length=30)
    papel_anterior = models.CharField(max_length=30, blank=True)
    papel_posterior = models.CharField(max_length=30, blank=True)
    ativo_anterior = models.BooleanField(null=True)
    ativo_posterior = models.BooleanField(null=True)
    origem = models.CharField(max_length=30, default="painel")
    justificativa = models.TextField(blank=True)
    operacao_global = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "auditoria_acessos"
        ordering = ["-criado_em", "-id"]


class EstadoPrivacidadeUsuario(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="estado_privacidade",
    )
    identificador_anonimo = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False
    )
    anonimizado_em = models.DateTimeField(blank=True, null=True)
    anonimizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="anonimizacoes_executadas",
        blank=True,
        null=True,
    )

    class Meta:
        db_table = "estado_privacidade_usuarios"

    @property
    def anonimizado(self):
        return self.anonimizado_em is not None


class AuditoriaRemocaoUsuario(models.Model):
    class Acao(models.TextChoices):
        DESATIVACAO_CONTA = "desativacao_conta", "Desativação de conta"
        REATIVACAO_CONTA = "reativacao_conta", "Reativação de conta"
        ANONIMIZACAO = "anonimizacao", "Anonimização"
        EXCLUSAO_FISICA = "exclusao_fisica", "Exclusão física"

    executor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="auditorias_remocao_executadas",
        blank=True,
        null=True,
    )
    executor_id_interno = models.PositiveBigIntegerField()
    usuario_alvo_id = models.PositiveBigIntegerField(db_index=True)
    acao = models.CharField(max_length=30, choices=Acao.choices)
    justificativa = models.TextField()
    origem = models.CharField(max_length=50, default="painel_global")
    resultado = models.CharField(max_length=30)
    situacao_anterior = models.JSONField(default=dict)
    situacao_posterior = models.JSONField(default=dict)
    modulos_com_referencias = models.JSONField(default=dict)
    operacao_global = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "auditoria_remocao_usuarios"
        ordering = ["-criado_em", "-id"]
