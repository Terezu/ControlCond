from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from condominios.models import VinculoUsuarioCondominio
from .services import papeis_gerenciaveis


class CadastrarUsuarioForm(forms.Form):
    first_name = forms.CharField(label="Nome", max_length=150)
    last_name = forms.CharField(label="Sobrenome", max_length=150)
    username = forms.CharField(label="Nome de usuário", max_length=150)
    email = forms.EmailField()
    senha_temporaria = forms.CharField(
        label="Senha temporária", widget=forms.PasswordInput
    )
    papel = forms.ChoiceField(
        label="Cargo",
        choices=VinculoUsuarioCondominio.Papel.choices,
    )
    ativo = forms.BooleanField(required=False, initial=True)
    justificativa = forms.CharField(
        required=False,
        label="Justificativa",
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def __init__(self, *args, executor, condominio, **kwargs):
        super().__init__(*args, **kwargs)
        permitidos = papeis_gerenciaveis(executor, condominio)
        self.fields["papel"].choices = [
            item for item in VinculoUsuarioCondominio.Papel.choices
            if item[0] in permitidos
        ]
        for field in self.fields.values():
            field.widget.attrs["class"] = (
                "form-select" if isinstance(field.widget, forms.Select)
                else "form-check-input" if isinstance(field.widget, forms.CheckboxInput)
                else "form-control"
            )

    def clean_senha_temporaria(self):
        senha = self.cleaned_data["senha_temporaria"]
        usuario = get_user_model()(
            username=self.cleaned_data.get("username", ""),
            email=self.cleaned_data.get("email", ""),
            first_name=self.cleaned_data.get("first_name", ""),
            last_name=self.cleaned_data.get("last_name", ""),
        )
        validate_password(senha, usuario)
        return senha


class EditarAcessoForm(forms.Form):
    papel = forms.ChoiceField(
        label="Cargo",
        choices=VinculoUsuarioCondominio.Papel.choices,
    )
    ativo = forms.BooleanField(required=False)
    conta_ativa = forms.BooleanField(
        required=False, label="Conta Django ativa"
    )
    justificativa = forms.CharField(
        required=False,
        label="Justificativa da alteração",
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def __init__(
        self, *args, executor, condominio, vinculo=None, **kwargs
    ):
        super().__init__(*args, **kwargs)
        permitidos = papeis_gerenciaveis(executor, condominio)
        self.fields["papel"].choices = [
            item for item in VinculoUsuarioCondominio.Papel.choices
            if item[0] in permitidos
        ]
        self.fields["papel"].widget.attrs["class"] = "form-select"
        self.fields["ativo"].widget.attrs["class"] = "form-check-input"
        self.fields["conta_ativa"].widget.attrs["class"] = "form-check-input"
        self.fields["conta_ativa"].disabled = True
        self.fields["conta_ativa"].help_text = (
            "A situação global da conta é alterada somente pela área global."
        )


class JustificativaContaForm(forms.Form):
    justificativa = forms.CharField(
        label="Justificativa",
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
    )

    def clean_justificativa(self):
        justificativa = self.cleaned_data["justificativa"].strip()
        if not justificativa:
            raise forms.ValidationError("A justificativa é obrigatória.")
        return justificativa


class RemocaoSeguraUsuarioForm(JustificativaContaForm):
    confirmacao = forms.CharField(
        label="Confirmação textual",
        widget=forms.TextInput(
            attrs={"class": "form-control", "autocomplete": "off"}
        ),
    )
    ciente = forms.BooleanField(
        label="Estou ciente de que esta ação é irreversível.",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def __init__(self, *args, confirmacao_exigida, **kwargs):
        super().__init__(*args, **kwargs)
        self.confirmacao_exigida = confirmacao_exigida
        self.fields["confirmacao"].help_text = (
            f'Digite exatamente: {confirmacao_exigida}'
        )

    def clean_confirmacao(self):
        confirmacao = self.cleaned_data["confirmacao"].strip()
        if confirmacao != self.confirmacao_exigida:
            raise forms.ValidationError(
                f'Digite exatamente "{self.confirmacao_exigida}".'
            )
        return confirmacao
