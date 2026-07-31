from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

from .models import AuditoriaAcesso, AuditoriaRemocaoUsuario


User = get_user_model()
try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass


@admin.register(User)
class UsuarioProtegidoAdmin(UserAdmin):
    def has_delete_permission(self, request, obj=None):
        return False

    def delete_model(self, request, obj):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied(
            "Utilize o fluxo global auditado para remover usuários."
        )

    def delete_queryset(self, request, queryset):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied(
            "A exclusão em massa de usuários não é permitida."
        )


@admin.register(AuditoriaAcesso)
class AuditoriaAcessoAdmin(admin.ModelAdmin):
    list_display = (
        "criado_em",
        "acao",
        "executor",
        "usuario_afetado",
        "condominio",
    )
    list_filter = ("acao", "condominio")
    readonly_fields = (
        "executor",
        "usuario_afetado",
        "condominio",
        "acao",
        "papel_anterior",
        "papel_posterior",
        "ativo_anterior",
        "ativo_posterior",
        "origem",
        "justificativa",
        "operacao_global",
        "criado_em",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditoriaRemocaoUsuario)
class AuditoriaRemocaoUsuarioAdmin(admin.ModelAdmin):
    list_display = (
        "criado_em", "acao", "usuario_alvo_id", "executor",
        "resultado", "operacao_global",
    )
    list_filter = ("acao", "resultado", "operacao_global")
    readonly_fields = (
        "executor", "executor_id_interno", "usuario_alvo_id", "acao",
        "justificativa", "origem", "resultado", "situacao_anterior",
        "situacao_posterior", "modulos_com_referencias",
        "operacao_global", "criado_em",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
