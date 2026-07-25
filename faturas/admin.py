from django.contrib import admin

from .models import Fatura, HistoricoStatusFatura


@admin.register(Fatura)
class FaturaAdmin(admin.ModelAdmin):
    list_display = (
        "apartamento", "condominio", "mes", "ano", "valor_total", "status",
    )
    list_filter = ("apartamento__condominio", "status", "ano", "mes")
    search_fields = (
        "apartamento__numero", "apartamento__bloco",
        "apartamento__condominio__nome",
    )

    @admin.display(ordering="apartamento__condominio")
    def condominio(self, obj):
        return obj.apartamento.condominio
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
        "valor_pago",
        "bonificacao_aplicada",
        "data_geracao",
        "data_emissao",
        "data_pagamento",
        "data_cancelamento",
        "apartamento_numero_emissao",
        "apartamento_bloco_emissao",
        "leitura_agua_anterior",
        "leitura_agua_atual",
        "leitura_gas_anterior",
        "leitura_gas_atual",
    )

    def get_readonly_fields(self, request, obj=None):
        campos = self.readonly_fields
        if obj is not None and obj.status != Fatura.Status.PENDENTE:
            return (
                *campos,
                "valor_aluguel",
                "valor_condominio",
                "valor_iptu",
                "valor_outros",
                "observacao_outros",
                "desconto",
                "valor_bonificacao",
                "dia_limite_bonificacao",
                "status",
            )
        return campos

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(HistoricoStatusFatura)
class HistoricoStatusFaturaAdmin(admin.ModelAdmin):
    list_display = (
        "fatura",
        "acao",
        "status_anterior",
        "novo_status",
        "usuario",
        "criado_em",
    )
    list_filter = ("acao", "status_anterior", "novo_status")
    search_fields = (
        "fatura__apartamento_numero_emissao",
        "motivo",
        "usuario__username",
    )
    readonly_fields = (
        "fatura",
        "status_anterior",
        "novo_status",
        "acao",
        "motivo",
        "usuario",
        "criado_em",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
