from django import forms
from django.utils import timezone

from faturas.models import ANO_MAXIMO


class FiltroCompetenciaDashboardForm(forms.Form):
    mes = forms.TypedChoiceField(
        label="Mês",
        choices=[
            (numero, f"{numero:02d}")
            for numero in range(1, 13)
        ],
        coerce=int,
    )
    ano = forms.IntegerField(
        label="Ano",
        min_value=2000,
        max_value=ANO_MAXIMO,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            classe = (
                "form-select"
                if isinstance(field.widget, forms.Select)
                else "form-control"
            )
            field.widget.attrs["class"] = classe

    @staticmethod
    def competencia_atual():
        hoje = timezone.localdate()
        return {"mes": hoje.month, "ano": hoje.year}
