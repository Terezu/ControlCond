from django.contrib import admin

from .models import Leitura


@admin.register(Leitura)
class LeituraAdmin(admin.ModelAdmin):
    list_display = ("apartamento", "mes", "ano", "leitura_agua", "leitura_gas")
    list_filter = ("ano", "mes")
    search_fields = ("apartamento__numero", "apartamento__bloco")

