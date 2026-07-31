from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .deletion_guard import exclusao_usuario_esta_autorizada


@receiver(
    pre_delete,
    sender=get_user_model(),
    dispatch_uid="usuarios_bloquear_exclusao_fora_service",
)
def bloquear_exclusao_usuario_fora_service(sender, instance, **kwargs):
    if not exclusao_usuario_esta_autorizada():
        raise PermissionDenied(
            "A exclusão de usuários deve utilizar o fluxo global auditado."
        )
