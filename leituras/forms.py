from django import forms

from apartamentos.models import Apartamento

from .models import ANO_MAXIMO, Leitura


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
                    "max": ANO_MAXIMO,
                }
            ),
            "leitura_agua": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": 0,
                }
            ),
            "leitura_gas": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": 0,
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            field.widget.attrs.update({"class": "form-control"})

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


class FiltrarLeiturasForm(forms.Form):
    apartamento = forms.ModelChoiceField(
        queryset=Apartamento.objects.none(),
        required=False,
        label="Apartamento",
        empty_label="Todos os apartamentos",
    )
    bloco = forms.CharField(
        required=False,
        label="Bloco",
        max_length=50,
    )
    mes = forms.ChoiceField(
        required=False,
        label="Mês",
        choices=[
            ("", "Todos os meses"),
            *[(numero, f"{numero:02d}") for numero in range(1, 13)],
        ],
    )
    ano = forms.IntegerField(
        required=False,
        label="Ano",
        min_value=2000,
        max_value=ANO_MAXIMO,
    )

    def __init__(self, *args, **kwargs):
        condominio = kwargs.pop("condominio", None)
        if condominio is None:
            from condominios.models import Condominio
            condominio = Condominio.objects.order_by("id").first()
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            classe = (
                "form-select"
                if isinstance(field.widget, forms.Select)
                else "form-control"
            )
            field.widget.attrs.update({"class": classe})

        self.fields["apartamento"].queryset = (
            Apartamento.objects.filter(
                condominio=condominio
            ).order_by("bloco", "numero", "id")
        )
