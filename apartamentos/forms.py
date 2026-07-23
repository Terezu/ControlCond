from django import forms

from .models import LIMITE_LEITURA, Apartamento


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            field.widget.attrs.update({"class": "form-control"})

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
