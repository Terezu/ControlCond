from django import forms

from .models import (
    ConfiguracaoCondominio,
    FaixaTarifaAgua,
    TabelaTarifariaAgua,
    TarifaGas,
)
from .validators import formatar_cep, formatar_cnpj


class ConfiguracaoCondominioForm(forms.ModelForm):
    TAMANHO_MAXIMO_LOGO = 5 * 1024 * 1024

    class Meta:
        model = ConfiguracaoCondominio
        fields = (
            "nome",
            "razao_social",
            "cnpj",
            "endereco",
            "numero",
            "complemento",
            "bairro",
            "cep",
            "cidade",
            "estado",
            "pais",
            "telefone",
            "celular",
            "email",
            "website",
            "nome_sindico",
            "administrador",
            "mensagem_institucional_rodape",
            "administradora_nome",
            "administradora_responsavel",
            "administradora_telefone",
            "administradora_email",
            "valor_m3_gas",
            "logo",
            "favicon",
            "cor_primaria",
            "cor_secundaria",
            "cor_destaque",
            "moeda",
            "dia_vencimento_padrao",
            "dias_tolerancia_pagamento",
            "dias_vencimento_padrao",
            "mensagem_cobranca_padrao",
            "mensagem_pagamento_antecipado",
            "percentual_multa_padrao",
            "percentual_juros_padrao",
            "tipo_juros",
            "percentual_bonificacao_padrao",
            "dias_antecedencia_bonificacao",
            "valor_bonificacao_padrao",
            "dia_bonificacao_padrao",
            "pix",
            "favorecido_nome",
            "favorecido_documento",
            "banco",
            "agencia",
            "conta",
            "tipo_conta",
            "codigo_barras_padrao",
            "instrucoes_pagamento",
            "mensagem_cabecalho",
            "observacoes_padrao",
            "texto_rodape",
            "texto_juridico",
            "cidade_assinatura",
            "responsavel_emissao",
            "cargo_responsavel",
            "mostrar_grafico_financeiro",
            "mostrar_ultimos_pagamentos",
            "mostrar_ultimos_cadastros",
            "mostrar_resumo_financeiro",
        )
        widgets = {
            "valor_m3_gas": forms.HiddenInput(),
            "observacoes_padrao": forms.Textarea(attrs={"rows": 4}),
            "texto_rodape": forms.Textarea(attrs={"rows": 3}),
            "mensagem_institucional_rodape": forms.Textarea(attrs={"rows": 3}),
            "mensagem_cobranca_padrao": forms.Textarea(attrs={"rows": 3}),
            "mensagem_pagamento_antecipado": forms.Textarea(attrs={"rows": 3}),
            "instrucoes_pagamento": forms.Textarea(attrs={"rows": 3}),
            "mensagem_cabecalho": forms.Textarea(attrs={"rows": 3}),
            "texto_juridico": forms.Textarea(attrs={"rows": 3}),
            "cor_primaria": forms.TextInput(attrs={"type": "color"}),
            "cor_secundaria": forms.TextInput(attrs={"type": "color"}),
            "cor_destaque": forms.TextInput(attrs={"type": "color"}),
            "dia_vencimento_padrao": forms.NumberInput(
                attrs={"min": "1", "max": "31"}
            ),
            "dias_tolerancia_pagamento": forms.NumberInput(
                attrs={"min": "0", "max": "365"}
            ),
            "percentual_multa_padrao": forms.NumberInput(
                attrs={"min": "0", "step": "0.001"}
            ),
            "percentual_juros_padrao": forms.NumberInput(
                attrs={"min": "0", "step": "0.001"}
            ),
            "percentual_bonificacao_padrao": forms.NumberInput(
                attrs={"min": "0", "max": "100", "step": "0.001"}
            ),
            "dias_antecedencia_bonificacao": forms.NumberInput(
                attrs={"min": "0", "max": "365"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                classe = "form-check-input"
            elif isinstance(field.widget, forms.Select):
                classe = "form-select"
            else:
                classe = "form-control"
            field.widget.attrs.update({"class": classe})

    def clean_logo(self):
        logo = self.cleaned_data.get("logo")
        if logo and getattr(logo, "size", 0) > self.TAMANHO_MAXIMO_LOGO:
            raise forms.ValidationError(
                "O logo deve possuir no máximo 5 MB."
            )
        return logo

    def clean_cnpj(self):
        return formatar_cnpj(self.cleaned_data["cnpj"])

    def clean_cep(self):
        return formatar_cep(self.cleaned_data["cep"])


class FaixaTarifaAguaForm(forms.ModelForm):
    class Meta:
        model = FaixaTarifaAgua
        fields = (
            "consumo_inicial",
            "consumo_final",
            "valor",
            "ordem",
            "ativa",
            "descricao",
        )
        widgets = {
            "consumo_inicial": forms.NumberInput(attrs={"min": "0"}),
            "consumo_final": forms.NumberInput(attrs={"min": "0"}),
            "valor": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "ordem": forms.NumberInput(attrs={"min": "1"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["percentual_bonificacao_padrao"].label = (
            "Bonificação padrão"
        )
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "form-check-input"
            else:
                field.widget.attrs["class"] = "form-control"


class BaseFaixaTarifaAguaFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        faixas = sorted(
            (
                form.cleaned_data
                for form in self.forms
                if form.cleaned_data
                and not form.cleaned_data.get("DELETE")
                and form.cleaned_data.get("ativa")
            ),
            key=lambda dados: dados["ordem"],
        )
        if not faixas:
            return
        if faixas[0]["consumo_inicial"] != 0:
            raise forms.ValidationError(
                "A primeira faixa ativa deve começar no consumo zero."
            )
        for indice, faixa in enumerate(faixas):
            final = faixa["consumo_final"]
            if final is None and indice != len(faixas) - 1:
                raise forms.ValidationError(
                    "Somente a última faixa ativa pode ter final aberto."
                )
            if indice:
                anterior = faixas[indice - 1]["consumo_final"]
                if anterior is None or faixa["consumo_inicial"] != anterior + 1:
                    raise forms.ValidationError(
                        "As faixas ativas devem ser contínuas e sem sobreposição."
                    )


FaixaTarifaAguaFormSet = forms.inlineformset_factory(
    TabelaTarifariaAgua,
    FaixaTarifaAgua,
    form=FaixaTarifaAguaForm,
    formset=BaseFaixaTarifaAguaFormSet,
    extra=1,
    can_delete=True,
)


class FormBootstrapMixin:
    def aplicar_bootstrap(self):
        for field in self.fields.values():
            field.widget.attrs["class"] = (
                "form-check-input"
                if isinstance(field.widget, forms.CheckboxInput)
                else "form-control"
            )


class TabelaTarifariaAguaForm(FormBootstrapMixin, forms.ModelForm):
    class Meta:
        model = TabelaTarifariaAgua
        fields = (
            "nome", "data_inicio_vigencia", "data_fim_vigencia",
            "ativa", "observacoes",
        )
        widgets = {
            "data_inicio_vigencia": forms.DateInput(attrs={"type": "date"}),
            "data_fim_vigencia": forms.DateInput(attrs={"type": "date"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_bootstrap()


class TarifaGasForm(FormBootstrapMixin, forms.ModelForm):
    class Meta:
        model = TarifaGas
        fields = (
            "nome", "valor_por_m3", "data_inicio_vigencia",
            "data_fim_vigencia", "ativa", "observacoes",
        )
        widgets = {
            "valor_por_m3": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "data_inicio_vigencia": forms.DateInput(attrs={"type": "date"}),
            "data_fim_vigencia": forms.DateInput(attrs={"type": "date"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_bootstrap()


class DuplicarRegraForm(forms.Form):
    nome = forms.CharField(max_length=150)
    data_inicio_vigencia = forms.DateField(
        label="Início da nova vigência",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["nome"].widget.attrs["class"] = "form-control"


class EncerrarVigenciaForm(forms.Form):
    data_fim_vigencia = forms.DateField(
        label="Último dia da vigência",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
