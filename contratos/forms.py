from django import forms

from apartamentos.models import Apartamento
from pessoas.models import Pessoa

from .models import Contrato


class ContratoForm(forms.ModelForm):
    class Meta:
        model = Contrato
        fields = (
            "apartamento",
            "pessoa_contratante",
            "responsavel_financeiro",
            "data_inicio",
            "data_termino",
            "observacoes",
        )
        widgets = {
            "data_inicio": forms.DateInput(attrs={"type": "date"}),
            "data_termino": forms.DateInput(attrs={"type": "date"}),
            "observacoes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, condominio, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["apartamento"].queryset = Apartamento.objects.filter(
            condominio=condominio, ativo=True, arquivado=False
        )
        pessoas = Pessoa.objects.filter(
            condominio=condominio, situacao=Pessoa.Situacao.ATIVA
        )
        self.fields["pessoa_contratante"].queryset = pessoas
        self.fields["responsavel_financeiro"].queryset = pessoas
        for field in self.fields.values():
            field.widget.attrs["class"] = (
                "form-select"
                if isinstance(field.widget, forms.Select)
                else "form-control"
            )

    def clean(self):
        dados = super().clean()
        inicio = dados.get("data_inicio")
        termino = dados.get("data_termino")
        if inicio and termino and termino <= inicio:
            self.add_error(
                "data_termino",
                "A data de término deve ser posterior à data de início.",
            )
        return dados


class FiltrarContratosForm(forms.Form):
    busca = forms.CharField(
        required=False,
        label="Buscar",
        widget=forms.TextInput(
            attrs={"placeholder": "Nome, CPF, apartamento ou bloco"}
        ),
    )
    situacao = forms.ChoiceField(
        required=False,
        choices=(("", "Todas"), *Contrato.Situacao.choices),
    )
    apartamento = forms.ModelChoiceField(
        required=False, queryset=Apartamento.objects.none()
    )
    inicio_de = forms.DateField(
        required=False, label="Início de",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    inicio_ate = forms.DateField(
        required=False, label="Início até",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    termino_de = forms.DateField(
        required=False, label="Término de",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    termino_ate = forms.DateField(
        required=False, label="Término até",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    proximos = forms.BooleanField(
        required=False, label="Próximos do vencimento"
    )
    encerrados = forms.BooleanField(required=False)
    rescindidos = forms.BooleanField(required=False)

    def __init__(self, *args, condominio, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["apartamento"].queryset = Apartamento.objects.filter(
            condominio=condominio, ativo=True, arquivado=False
        )
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "form-check-input"
            else:
                field.widget.attrs["class"] = (
                    "form-select"
                    if isinstance(field.widget, forms.Select)
                    else "form-control"
                )


class RescindirContratoForm(forms.Form):
    data_rescisao = forms.DateField(
        label="Data da rescisão",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    justificativa = forms.CharField(
        label="Justificativa",
        widget=forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
        error_messages={
            "required": "Informe a justificativa da rescisão."
        },
    )

    def clean_justificativa(self):
        justificativa = self.cleaned_data["justificativa"].strip()
        if not justificativa:
            raise forms.ValidationError(
                "Informe a justificativa da rescisão."
            )
        return justificativa
