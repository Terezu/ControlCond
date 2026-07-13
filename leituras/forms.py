from django import forms

from .models import Leitura


class LeituraForm(forms.ModelForm):
    class Meta:
        model = Leitura
        fields = [
            "mes",
            "ano",
            "leitura_agua",
            "leitura_gas",
        ]

        labels = {
            "mes": "Mês",
            "ano": "Ano",
            "leitura_agua": "Leitura de água",
            "leitura_gas": "Leitura de gás",
        }

        widgets = {
            "mes": forms.NumberInput(
                attrs={
                    "min": 1,
                    "max": 12,
                }
            ),
            "ano": forms.NumberInput(
                attrs={
                    "min": 2000,
                }
            ),
            "leitura_agua": forms.NumberInput(
                attrs={
                    "step": "0.001",
                    "min": 0,
                }
            ),
            "leitura_gas": forms.NumberInput(
                attrs={
                    "step": "0.001",
                    "min": 0,
                }
            ),
        }

    def clean_mes(self):
        mes = self.cleaned_data["mes"]

        if mes < 1 or mes > 12:
            raise forms.ValidationError(
                "Informe um mês entre 1 e 12."
            )

        return mes

    def clean_ano(self):
        ano = self.cleaned_data["ano"]

        if ano < 2000:
            raise forms.ValidationError(
                "Informe um ano válido."
            )

        return ano

    def clean(self):
        dados = super().clean()

        leitura_agua = dados.get("leitura_agua")
        leitura_gas = dados.get("leitura_gas")

        if leitura_agua is None and leitura_gas is None:
            raise forms.ValidationError(
                "Informe pelo menos uma leitura: água ou gás."
            )

        if leitura_agua is not None and leitura_agua < 0:
            self.add_error(
                "leitura_agua",
                "A leitura de água não pode ser negativa."
            )

        if leitura_gas is not None and leitura_gas < 0:
            self.add_error(
                "leitura_gas",
                "A leitura de gás não pode ser negativa."
            )

        return dados
    