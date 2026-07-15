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

    def clean(self):
        dados = super().clean()
        if not self.instance.pk:
            return dados

        primeira_leitura = self.instance.leituras.order_by(
            "ano", "mes", "id"
        ).first()
        if primeira_leitura is None:
            return dados

        leitura_base_agua = dados.get("leitura_base_agua")
        if (
            leitura_base_agua is not None
            and primeira_leitura.leitura_agua is not None
            and leitura_base_agua > primeira_leitura.leitura_agua
        ):
            self.add_error(
                "leitura_base_agua",
                "A leitura-base de água não pode ser maior que a primeira leitura cadastrada.",
            )

        leitura_base_gas = dados.get("leitura_base_gas")
        if (
            leitura_base_gas is not None
            and primeira_leitura.leitura_gas is not None
            and leitura_base_gas > primeira_leitura.leitura_gas
        ):
            self.add_error(
                "leitura_base_gas",
                "A leitura-base de gás não pode ser maior que a primeira leitura cadastrada.",
            )

        return dados
