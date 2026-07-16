from decimal import Decimal

from django import forms

from .models import Apartamento

LIMITE_LEITURA = Decimal("999999.99")


class ApartamentoForm(forms.ModelForm):
    class Meta:
        model = Apartamento
        fields = (
            "numero",
            "bloco",
            "leitura_base_agua",
            "leitura_base_gas",
            "observacoes",
        )
        labels = {
            "numero": "Número",
            "bloco": "Bloco",
            "leitura_base_agua": "Leitura-base de água",
            "leitura_base_gas": "Leitura-base de gás",
            "observacoes": "Observações",
        }
        widgets = {
            "leitura_base_agua": forms.NumberInput(
                attrs={"min": "0", "max": str(LIMITE_LEITURA), "step": "0.01"}
            ),
            "leitura_base_gas": forms.NumberInput(
                attrs={"min": "0", "max": str(LIMITE_LEITURA), "step": "0.01"}
            ),
            "observacoes": forms.Textarea(attrs={"rows": 4}),
        }

    def clean_leitura_base_agua(self):
        valor = self.cleaned_data["leitura_base_agua"]
        if valor < 0:
            raise forms.ValidationError(
                "A leitura-base de água não pode ser negativa."
            )
        if valor > LIMITE_LEITURA:
            raise forms.ValidationError(
                "A leitura-base de água excede o valor máximo permitido."
            )
        return valor

    def clean_leitura_base_gas(self):
        valor = self.cleaned_data["leitura_base_gas"]
        if valor < 0:
            raise forms.ValidationError(
                "A leitura-base de gás não pode ser negativa."
            )
        if valor > LIMITE_LEITURA:
            raise forms.ValidationError(
                "A leitura-base de gás excede o valor máximo permitido."
            )
        return valor
