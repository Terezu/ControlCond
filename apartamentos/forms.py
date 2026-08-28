from decimal import Decimal

from django import forms

from configuracoes.services import obter_configuracao
from .models import (
    LIMITE_LEITURA,
    LIMITE_VALOR_MONETARIO,
    Apartamento,
)


class ApartamentoForm(forms.ModelForm):
    class Meta:
        model = Apartamento
        fields = (
            "numero",
            "bloco",
            "valor_aluguel",
            "valor_condominio",
            "valor_iptu",
            "valor_bonificacao",
            "dia_limite_bonificacao",
            "leitura_base_agua",
            "leitura_base_gas",
            "observacoes",
        )
        labels = {
            "numero": "Número",
            "bloco": "Bloco",
            "valor_aluguel": "Valor padrão do aluguel",
            "valor_condominio": "Valor padrão do condomínio",
            "valor_iptu": "Valor padrão do IPTU",
            "valor_bonificacao": "Valor padrão da bonificação",
            "dia_limite_bonificacao": "Dia limite da bonificação",
            "leitura_base_agua": "Leitura-base de água",
            "leitura_base_gas": "Leitura-base de gás",
            "observacoes": "Observações",
        }
        widgets = {
            "valor_aluguel": forms.NumberInput(
                attrs={
                    "min": "0",
                    "max": str(LIMITE_VALOR_MONETARIO),
                    "step": "0.01",
                }
            ),
            "valor_condominio": forms.NumberInput(
                attrs={
                    "min": "0",
                    "max": str(LIMITE_VALOR_MONETARIO),
                    "step": "0.01",
                }
            ),
            "valor_iptu": forms.NumberInput(
                attrs={
                    "min": "0",
                    "max": str(LIMITE_VALOR_MONETARIO),
                    "step": "0.01",
                }
            ),
            "valor_bonificacao": forms.NumberInput(
                attrs={
                    "min": "0",
                    "max": str(LIMITE_VALOR_MONETARIO),
                    "step": "0.01",
                }
            ),
            "dia_limite_bonificacao": forms.NumberInput(
                attrs={"min": "1", "max": "31", "step": "1"}
            ),
            "leitura_base_agua": forms.NumberInput(
                attrs={"min": "0", "max": str(LIMITE_LEITURA), "step": "0.01"}
            ),
            "leitura_base_gas": forms.NumberInput(
                attrs={"min": "0", "max": str(LIMITE_LEITURA), "step": "0.01"}
            ),
            "observacoes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        condominio = kwargs.pop("condominio", None)
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            field.widget.attrs.update({"class": "form-control"})
        if not self.is_bound and not getattr(self.instance, "pk", None):
            if condominio is None:
                condominio = self.instance.condominio
            configuracao = obter_configuracao(condominio)
            self.fields["valor_bonificacao"].initial = (
                configuracao.valor_bonificacao_padrao
            )
            self.fields["dia_limite_bonificacao"].initial = (
                configuracao.dia_bonificacao_padrao
            )

    def clean_valor_aluguel(self):
        return self.cleaned_data["valor_aluguel"] or Decimal("0.00")

    def clean(self):
        cleaned_data = super().clean()
        for campo in (
            "valor_condominio",
            "valor_iptu",
            "valor_bonificacao",
        ):
            if campo in cleaned_data:
                cleaned_data[campo] = cleaned_data[campo] or Decimal("0.00")
        if (
            cleaned_data.get("valor_bonificacao", Decimal("0.00")) > 0
            and not cleaned_data.get("dia_limite_bonificacao")
        ):
            self.add_error(
                "dia_limite_bonificacao",
                "Informe o dia limite quando houver bonificação.",
            )
        return cleaned_data

class FiltrarApartamentosForm(forms.Form):
    numero = forms.CharField(
        required=False,
        label="Número do apartamento",
        max_length=20,
    )
    bloco = forms.CharField(
        required=False,
        label="Bloco",
        max_length=50,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            field.widget.attrs.update({"class": "form-control"})
