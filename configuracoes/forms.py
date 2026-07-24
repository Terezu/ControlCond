from django import forms

from .models import ConfiguracaoCondominio
from .validators import formatar_cep, formatar_cnpj


class ConfiguracaoCondominioForm(forms.ModelForm):
    TAMANHO_MAXIMO_LOGO = 5 * 1024 * 1024

    class Meta:
        model = ConfiguracaoCondominio
        fields = (
            "nome",
            "cnpj",
            "endereco",
            "cep",
            "cidade",
            "estado",
            "telefone",
            "email",
            "administradora_nome",
            "administradora_responsavel",
            "administradora_telefone",
            "administradora_email",
            "valor_m3_gas",
            "logo",
            "observacoes_padrao",
            "texto_rodape",
        )
        widgets = {
            "valor_m3_gas": forms.NumberInput(
                attrs={"min": "0", "max": "999999.99", "step": "0.01"}
            ),
            "observacoes_padrao": forms.Textarea(attrs={"rows": 4}),
            "texto_rodape": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            classe = (
                "form-select"
                if isinstance(field.widget, forms.Select)
                else "form-control"
            )
            field.widget.attrs.update({"class": classe})

    def clean_logo(self):
        logo = self.cleaned_data.get("logo")
        if logo and getattr(logo, "size", 0) > self.TAMANHO_MAXIMO_LOGO:
            raise forms.ValidationError(
                "O logo deve possuir no máximo 5 MB."
            )
        return logo

    def clean_cnpj(self):
        return formatar_cnpj(self.cleaned_data["cnpj"])

    def clean_cep(self):
        return formatar_cep(self.cleaned_data["cep"])
