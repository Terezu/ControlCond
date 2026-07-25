from django.contrib import admin

from .models import ConfiguracaoCondominio, FaixaTarifaAgua


@admin.register(ConfiguracaoCondominio)
class ConfiguracaoCondominioAdmin(admin.ModelAdmin):
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
                    "valor_m3_gas", "moeda", "dias_vencimento_padrao",
                    "mensagem_cobranca_padrao",
                    "mensagem_pagamento_antecipado",
                    "percentual_multa_padrao",
                    "percentual_juros_padrao",
                    "valor_bonificacao_padrao",
                    "dia_bonificacao_padrao",
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
        return not ConfiguracaoCondominio.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FaixaTarifaAgua)
class FaixaTarifaAguaAdmin(admin.ModelAdmin):
    list_display = (
        "ordem",
        "consumo_inicial",
        "consumo_final",
        "valor",
        "ativa",
    )
    list_editable = ("consumo_inicial", "consumo_final", "valor", "ativa")
    ordering = ("ordem", "id")
