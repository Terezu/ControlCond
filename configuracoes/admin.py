from django.contrib import admin

from .models import (
    ConfiguracaoCondominio,
    FaixaTarifaAgua,
    TabelaTarifariaAgua,
    TarifaGas,
)


@admin.register(ConfiguracaoCondominio)
class ConfiguracaoCondominioAdmin(admin.ModelAdmin):
    list_display = ("nome", "condominio", "atualizado_em")
    list_filter = ("condominio",)
    autocomplete_fields = ("condominio",)
    fieldsets = (
        (
            "Dados do condomínio",
            {
                "fields": (
                    "nome", "razao_social", "cnpj", "endereco", "numero",
                    "complemento", "bairro", "cep", "cidade", "estado",
                    "pais", "telefone", "celular", "email", "website",
                    "nome_sindico", "administrador",
                    "mensagem_institucional_rodape",
                )
            },
        ),
        (
            "Dados da administradora",
            {
                "fields": (
                    "administradora_nome",
                    "administradora_responsavel",
                    "administradora_telefone",
                    "administradora_email",
                )
            },
        ),
        (
            "Identidade visual",
            {
                "fields": (
                    "logo", "favicon", "cor_primaria",
                    "cor_secundaria", "cor_destaque",
                )
            },
        ),
        (
            "Financeiro",
            {
                "fields": (
                    "moeda",
                    "dia_vencimento_padrao",
                    "dias_tolerancia_pagamento",
                    "percentual_multa_padrao",
                    "percentual_juros_padrao",
                    "tipo_juros",
                    "percentual_bonificacao_padrao",
                    "dias_antecedencia_bonificacao",
                    "dias_vencimento_padrao",
                    "valor_bonificacao_padrao",
                    "dia_bonificacao_padrao",
                    "mensagem_cobranca_padrao",
                    "mensagem_pagamento_antecipado",
                )
            },
        ),
        (
            "Pagamento",
            {
                "fields": (
                    "pix", "favorecido_nome", "favorecido_documento",
                    "banco", "agencia", "conta", "tipo_conta",
                    "codigo_barras_padrao", "instrucoes_pagamento",
                )
            },
        ),
        (
            "PDF",
            {
                "fields": (
                    "mensagem_cabecalho", "observacoes_padrao",
                    "texto_rodape", "texto_juridico",
                    "cidade_assinatura", "responsavel_emissao",
                    "cargo_responsavel",
                )
            },
        ),
        (
            "Dashboard",
            {
                "fields": (
                    "mostrar_grafico_financeiro",
                    "mostrar_ultimos_pagamentos",
                    "mostrar_ultimos_cadastros",
                    "mostrar_resumo_financeiro",
                )
            },
        ),
    )

    def has_add_permission(self, request):
        from condominios.models import Condominio
        return Condominio.objects.filter(configuracao__isnull=True).exists()

    def has_delete_permission(self, request, obj=None):
        return False


class FaixaTarifaAguaInline(admin.TabularInline):
    model = FaixaTarifaAgua
    extra = 0

    def has_change_permission(self, request, obj=None):
        return not (obj and obj.foi_utilizada)

    def has_delete_permission(self, request, obj=None):
        return not (obj and obj.foi_utilizada)


@admin.register(FaixaTarifaAgua)
class FaixaTarifaAguaAdmin(admin.ModelAdmin):
    list_display = (
        "tabela", "ordem", "consumo_inicial", "consumo_final", "valor", "ativa",
    )
    list_filter = ("ativa", "tabela")
    ordering = ("tabela", "ordem")


@admin.register(TabelaTarifariaAgua)
class TabelaTarifariaAguaAdmin(admin.ModelAdmin):
    list_display = (
        "nome", "condominio", "data_inicio_vigencia",
        "data_fim_vigencia", "ativa",
    )
    list_filter = ("condominio", "ativa")
    search_fields = ("nome", "condominio__nome")
    autocomplete_fields = ("condominio",)
    ordering = ("-data_inicio_vigencia",)
    inlines = (FaixaTarifaAguaInline,)

    def has_delete_permission(self, request, obj=None):
        return not (obj and obj.foi_utilizada)


@admin.register(TarifaGas)
class TarifaGasAdmin(admin.ModelAdmin):
    list_display = (
        "nome", "condominio", "valor_por_m3", "data_inicio_vigencia",
        "data_fim_vigencia", "ativa",
    )
    list_filter = ("condominio", "ativa")
    search_fields = ("nome", "condominio__nome")
    autocomplete_fields = ("condominio",)
    ordering = ("-data_inicio_vigencia",)

    def has_delete_permission(self, request, obj=None):
        return not (obj and obj.foi_utilizada)
