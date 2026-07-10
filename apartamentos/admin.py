from django.contrib import admin

from .models import Apartamento


@admin.register(Apartamento)
class ApartamentoAdmin(admin.ModelAdmin):
    list_display = ("numero", "bloco", "observacoes")
    search_fields = ("numero", "bloco")

