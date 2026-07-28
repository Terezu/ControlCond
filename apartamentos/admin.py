from django.contrib import admin

from .models import Apartamento


@admin.register(Apartamento)
class ApartamentoAdmin(admin.ModelAdmin):
    list_display = (
        "id", "condominio", "numero", "bloco", "ativo",
        "arquivado", "retencao_ate",
    )
    list_filter = ("ativo", "arquivado", "situacao_retencao", "condominio")
    readonly_fields = (
        "arquivado_em", "arquivado_por", "retencao_ate",
        "identificador_backup",
    )
    search_fields = ("numero", "bloco", "condominio__nome")
    list_filter = ("condominio", "bloco")
    autocomplete_fields = ("condominio",)
