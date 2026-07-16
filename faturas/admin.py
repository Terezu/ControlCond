from django.contrib import admin

from .models import Fatura


@admin.register(Fatura)
class FaturaAdmin(admin.ModelAdmin):
    list_display = ("apartamento", "mes", "ano", "valor_total", "status")
    list_filter = ("status", "ano", "mes")
    search_fields = ("apartamento__numero", "apartamento__bloco")
    readonly_fields = (
        "apartamento",
        "leitura",
        "mes",
        "ano",
        "consumo_agua",
        "consumo_gas",
        "valor_agua",
        "valor_gas",
        "valor_total",
        "data_geracao",
        "data_emissao",
        "apartamento_numero_emissao",
        "apartamento_bloco_emissao",
        "leitura_agua_anterior",
        "leitura_agua_atual",
        "leitura_gas_anterior",
        "leitura_gas_atual",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
