from django.contrib import admin

from .models import Pessoa, VinculoPessoaApartamento


@admin.register(Pessoa)
class PessoaAdmin(admin.ModelAdmin):
    list_display = ("nome_completo", "cpf", "condominio", "situacao")
    list_filter = ("situacao", "condominio")
    search_fields = ("nome_completo", "cpf", "email", "telefone")


@admin.register(VinculoPessoaApartamento)
class VinculoPessoaApartamentoAdmin(admin.ModelAdmin):
    list_display = (
        "pessoa",
        "apartamento",
        "tipo",
        "data_inicio",
        "data_fim",
        "ativo",
    )
    list_filter = ("tipo", "ativo", "apartamento__condominio")
    search_fields = (
        "pessoa__nome_completo",
        "pessoa__cpf",
        "apartamento__numero",
    )
