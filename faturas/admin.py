from django.contrib import admin

from .models import Fatura, HistoricoFinanceiroFatura


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
        "valor_original",
        "valor_final",
        "valor_pago",
        "bonificacao_aplicada",
        "valor_bonificacao_aplicada",
        "valor_bonificacao",
        "dia_limite_bonificacao",
        "valor_multa_aplicada",
        "valor_juros_aplicados",
        "percentual_multa_emissao",
        "percentual_juros_emissao",
        "tipo_juros_emissao",
        "dias_tolerancia_emissao",
        "percentual_bonificacao_emissao",
        "origem_bonificacao_emissao",
        "tipo_bonificacao_emissao",
        "valor_bonificacao_fixa_emissao",
        "dias_antecedencia_bonificacao_emissao",
        "forma_pagamento",
        "observacoes_pagamento",
        "data_geracao",
        "data_emissao",
        "data_vencimento",
        "data_limite_bonificacao",
        "data_pagamento",
        "dias_em_atraso",
        "dias_antecipados",
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
                "status",
            )
        return campos

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(HistoricoFinanceiroFatura)
class HistoricoFinanceiroFaturaAdmin(admin.ModelAdmin):
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
        "valores_anteriores",
        "valores_novos",
        "usuario",
        "criado_em",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
