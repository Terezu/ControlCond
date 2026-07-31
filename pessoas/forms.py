from django import forms
from django.utils import timezone

from apartamentos.models import Apartamento

from .models import Pessoa, VinculoPessoaApartamento
from .services import normalizar_cpf


class PessoaForm(forms.ModelForm):
    cpf = forms.CharField(label="CPF", max_length=14)

    class Meta:
        model = Pessoa
        fields = (
            "nome_completo",
            "cpf",
            "rg",
            "email",
            "telefone",
            "data_nascimento",
            "situacao",
            "observacoes",
        )
        widgets = {
            "data_nascimento": forms.DateInput(attrs={"type": "date"}),
            "observacoes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = (
                "form-select"
                if isinstance(field.widget, forms.Select)
                else "form-control"
            )

    def clean_cpf(self):
        try:
            return normalizar_cpf(self.cleaned_data["cpf"])
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc

    def clean_data_nascimento(self):
        data = self.cleaned_data.get("data_nascimento")
        if data and data > timezone.localdate():
            raise forms.ValidationError(
                "A data de nascimento não pode estar no futuro."
            )
        return data


class FiltrarPessoasForm(forms.Form):
    busca = forms.CharField(
        required=False,
        label="Buscar",
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Nome, CPF, e-mail ou telefone",
            }
        ),
    )
    situacao = forms.ChoiceField(
        required=False,
        choices=(("", "Todas"), *Pessoa.Situacao.choices),
    )
    tipo_vinculo = forms.ChoiceField(
        required=False,
        label="Tipo de vínculo ativo",
        choices=(("", "Todos"), *VinculoPessoaApartamento.Tipo.choices),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = (
                "form-select"
                if isinstance(field.widget, forms.Select)
                else "form-control"
            )


class VinculoPessoaApartamentoForm(forms.ModelForm):
    class Meta:
        model = VinculoPessoaApartamento
        fields = ("apartamento", "tipo", "data_inicio")
        widgets = {
            "data_inicio": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, condominio, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["apartamento"].queryset = (
            Apartamento.objects.filter(
                condominio=condominio, ativo=True, arquivado=False
            )
            .order_by("bloco", "numero", "id")
        )
        self.fields["data_inicio"].initial = timezone.localdate()
        for field in self.fields.values():
            field.widget.attrs["class"] = (
                "form-select"
                if isinstance(field.widget, forms.Select)
                else "form-control"
            )


class EditarVinculoPessoaApartamentoForm(
    VinculoPessoaApartamentoForm
):
    def __init__(self, *args, condominio, **kwargs):
        super().__init__(*args, condominio=condominio, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["data_inicio"].initial = self.instance.data_inicio


class EncerrarVinculoForm(forms.Form):
    data_fim = forms.DateField(
        label="Data de fim",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )

    def __init__(self, *args, data_inicio=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.data_inicio = data_inicio
        self.fields["data_fim"].initial = timezone.localdate()

    def clean_data_fim(self):
        data_fim = self.cleaned_data["data_fim"]
        if self.data_inicio and data_fim < self.data_inicio:
            raise forms.ValidationError(
                "A data de fim não pode anteceder a data de início."
            )
        return data_fim
