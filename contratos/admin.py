from django.contrib import admin

from .models import (
    AuditoriaRescisaoContrato,
    Contrato,
    VinculoFinanceiroContrato,
)


@admin.register(Contrato)
class ContratoAdmin(admin.ModelAdmin):
    list_display = (
        "apartamento", "pessoa_contratante", "data_inicio",
        "data_termino", "situacao",
    )
    list_filter = ("situacao", "condominio")
    search_fields = (
        "apartamento__numero", "pessoa_contratante__nome_completo",
    )

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditoriaRescisaoContrato)
class AuditoriaRescisaoContratoAdmin(admin.ModelAdmin):
    list_display = (
        "criado_em", "contrato", "condominio", "executor",
        "situacao_anterior", "situacao_posterior",
    )
    list_filter = ("condominio", "situacao_anterior", "situacao_posterior")
    readonly_fields = tuple(
        campo.name for campo in AuditoriaRescisaoContrato._meta.fields
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(VinculoFinanceiroContrato)
class VinculoFinanceiroContratoAdmin(admin.ModelAdmin):
    list_display = ("contrato", "vinculo", "criado_pelo_contrato")
    readonly_fields = tuple(
        campo.name for campo in VinculoFinanceiroContrato._meta.fields
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
