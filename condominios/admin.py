from django.contrib import admin

from .models import Condominio, VinculoUsuarioCondominio


class VinculoInline(admin.TabularInline):
    model = VinculoUsuarioCondominio
    extra = 0
    autocomplete_fields = ("usuario",)


@admin.register(Condominio)
class CondominioAdmin(admin.ModelAdmin):
    list_display = ("nome", "slug", "ativo", "atualizado_em")
    list_filter = ("ativo",)
    search_fields = ("nome", "slug")
    prepopulated_fields = {"slug": ("nome",)}
    inlines = (VinculoInline,)


@admin.register(VinculoUsuarioCondominio)
class VinculoUsuarioCondominioAdmin(admin.ModelAdmin):
    list_display = ("usuario", "condominio", "papel", "ativo")
    list_filter = ("papel", "ativo", "condominio")
    search_fields = ("usuario__username", "usuario__email", "condominio__nome")
    autocomplete_fields = ("usuario", "condominio")
