from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify


def obter_condominio_padrao_id():
    condominio = Condominio.objects.order_by("id").first()
    if condominio is None:
        condominio = Condominio.objects.create(
            nome="Condomínio Inicial",
            slug="condominio-inicial",
        )
    return condominio.pk


class Condominio(models.Model):
    nome = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, unique=True, blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("nome", "id")
        verbose_name = "Condomínio"
        verbose_name_plural = "Condomínios"

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.nome) or "condominio"
            candidato = base
            indice = 2
            while Condominio.objects.exclude(pk=self.pk).filter(
                slug=candidato
            ).exists():
                candidato = f"{base}-{indice}"
                indice += 1
            self.slug = candidato
        super().save(*args, **kwargs)


class VinculoUsuarioCondominio(models.Model):
    class Papel(models.TextChoices):
        PROPRIETARIO = "proprietario", "Proprietário"
        ADMINISTRADOR = "administrador", "Administrador"
        OPERADOR = "operador", "Operador"
        CONSULTA = "consulta", "Somente consulta"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="vinculos_condominios",
    )
    condominio = models.ForeignKey(
        Condominio,
        on_delete=models.CASCADE,
        related_name="vinculos_usuarios",
    )
    papel = models.CharField(max_length=20, choices=Papel.choices)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("condominio__nome", "usuario__username")
        constraints = [
            models.UniqueConstraint(
                fields=("usuario", "condominio"),
                name="vinculo_usuario_condominio_unico",
            )
        ]

    def __str__(self):
        return f"{self.usuario} · {self.condominio} ({self.get_papel_display()})"

    def clean(self):
        super().clean()
        if self.ativo and self.condominio_id and not self.condominio.ativo:
            raise ValidationError(
                {"condominio": "Não é possível ativar vínculo com condomínio inativo."}
            )
