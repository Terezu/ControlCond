from django.contrib import admin

from .models import Apartamento


@admin.register(Apartamento)
class ApartamentoAdmin(admin.ModelAdmin):
    list_display = ("id", "condominio", "numero", "bloco", "observacoes")
    search_fields = ("numero", "bloco", "condominio__nome")
    list_filter = ("condominio", "bloco")
    autocomplete_fields = ("condominio",)
