from django import forms
from django.utils import timezone

from apartamentos.models import Apartamento
from faturas.models import ANO_MAXIMO
from faturas.models import Fatura


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


class FiltroDashboardFinanceiroForm(FiltroCompetenciaDashboardForm):
    apartamento = forms.ModelChoiceField(
        queryset=Apartamento.objects.none(),
        required=False,
        label="Apartamento",
        empty_label="Todos os apartamentos",
    )
    status = forms.ChoiceField(
        required=False,
        label="Status da fatura",
        choices=(("", "Todos os status"), *Fatura.Status.choices),
    )

    def __init__(self, *args, condominio, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["apartamento"].queryset = (
            Apartamento.objects.filter(
                condominio=condominio,
                arquivado=False,
            ).order_by("bloco", "numero", "id")
        )
