from django.contrib import admin

from .models import ConfiguracaoCondominio


@admin.register(ConfiguracaoCondominio)
class ConfiguracaoCondominioAdmin(admin.ModelAdmin):
    fieldsets = (
        (
            "Dados do condomínio",
            {
                "fields": (
                    "nome", "cnpj", "endereco", "cep",
                    "cidade", "estado", "telefone", "email",
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
        ("Cobranças", {"fields": ("valor_m3_gas",)}),
        (
            "PDF",
            {
                "fields": (
                    "logo", "observacoes_padrao", "texto_rodape",
                )
            },
        ),
    )

    def has_add_permission(self, request):
        return not ConfiguracaoCondominio.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
