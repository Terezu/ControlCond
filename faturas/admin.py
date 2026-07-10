from django.contrib import admin

from .models import Fatura


@admin.register(Fatura)
class FaturaAdmin(admin.ModelAdmin):
    list_display = ("apartamento", "mes", "ano", "valor_total", "status")
    list_filter = ("status", "ano", "mes")
    search_fields = ("apartamento__numero", "apartamento__bloco")

