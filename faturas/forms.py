from decimal import Decimal

from django import forms
from django.db.models import Exists, OuterRef

from apartamentos.models import Apartamento
from leituras.models import Leitura

from .models import ANO_MAXIMO, LIMITE_VALOR_FINANCEIRO, Fatura
from .services import (
    RegraNegocioFaturaError,
    validar_edicao_financeira,
)


def _aplicar_estilo_bootstrap(fields):
    for field in fields.values():
        classe = (
            "form-select"
            if isinstance(field.widget, forms.Select)
            else "form-control"
        )
        field.widget.attrs.update({"class": classe})


class GerarFaturaForm(forms.Form):
    leitura = forms.ModelChoiceField(
        queryset=Leitura.objects.none(),
        label="Leitura",
        empty_label="Selecione uma leitura",
    )
    valor_aluguel = forms.DecimalField(
        required=False,
        label="Valor do aluguel",
        min_value=0,
        max_value=LIMITE_VALOR_FINANCEIRO,
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={"min": "0", "step": "0.01"}
        ),
    )
    desconto = forms.DecimalField(
        required=False,
        label="Desconto",
        min_value=0,
        max_value=LIMITE_VALOR_FINANCEIRO,
        max_digits=10,
        decimal_places=2,
        initial=Decimal("0.00"),
        widget=forms.NumberInput(
            attrs={"min": "0", "step": "0.01"}
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _aplicar_estilo_bootstrap(self.fields)

        fatura_do_periodo = Fatura.objects.filter(
            apartamento_id=OuterRef("apartamento_id"),
            mes=OuterRef("mes"),
            ano=OuterRef("ano"),
        )
        self.fields["leitura"].queryset = (
            Leitura.objects
            .select_related("apartamento")
            .annotate(fatura_existente=Exists(fatura_do_periodo))
            .filter(
                leitura_agua__isnull=False,
                leitura_gas__isnull=False,
                fatura_existente=False,
            )
            .order_by("-ano", "-mes", "apartamento__numero")
        )

        self.fields["leitura"].label_from_instance = self.descrever_leitura

    def clean_desconto(self):
        return self.cleaned_data["desconto"] or Decimal("0.00")

    @staticmethod
    def descrever_leitura(leitura):
        bloco = leitura.apartamento.bloco

        apartamento = f"Apartamento {leitura.apartamento.numero}"

        if bloco:
            apartamento += f" - Bloco {bloco}"

        return (
            f"{apartamento} | "
            f"{leitura.mes:02d}/{leitura.ano} | "
            f"Água: {leitura.leitura_agua} | "
            f"Gás: {leitura.leitura_gas}"
        )

class MotivoAlteracaoStatusForm(forms.Form):
    motivo = forms.CharField(
        label="Motivo",
        min_length=5,
        max_length=500,
        strip=True,
        widget=forms.Textarea(attrs={"rows": 4}),
        error_messages={
            "min_length": "O motivo deve ter pelo menos 5 caracteres.",
            "max_length": "O motivo deve ter no máximo 500 caracteres.",
        },
    )

    def __init__(self, *args, acao=None, **kwargs):
        super().__init__(*args, **kwargs)
        _aplicar_estilo_bootstrap(self.fields)
        descricao = (
            "estorno"
            if acao == "estornar_pagamento"
            else "reabertura"
        )
        artigo = "do" if descricao == "estorno" else "da"
        self.fields["motivo"].error_messages["required"] = (
            f"Informe o motivo {artigo} {descricao}."
        )


class EditarValoresFaturaForm(forms.Form):
    valor_aluguel = forms.DecimalField(
        label="Valor do aluguel",
        min_value=0,
        max_value=LIMITE_VALOR_FINANCEIRO,
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={"min": "0", "step": "0.01"}
        ),
    )
    desconto = forms.DecimalField(
        required=False,
        label="Desconto",
        min_value=0,
        max_value=LIMITE_VALOR_FINANCEIRO,
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={"min": "0", "step": "0.01"}
        ),
    )

    def __init__(self, *args, fatura=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fatura = fatura
        _aplicar_estilo_bootstrap(self.fields)
        if fatura is not None:
            self.fields["valor_aluguel"].initial = fatura.valor_aluguel
            self.fields["desconto"].initial = fatura.desconto

    def clean_desconto(self):
        return self.cleaned_data["desconto"] or Decimal("0.00")

    def clean(self):
        cleaned_data = super().clean()
        if self.fatura is not None:
            try:
                validar_edicao_financeira(self.fatura)
            except RegraNegocioFaturaError as exc:
                raise forms.ValidationError(exc.messages[0]) from exc
        return cleaned_data


class FiltrarFaturasForm(forms.Form):
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
            *[
                (numero, f"{numero:02d}")
                for numero in range(1, 13)
            ],
        ],
    )

    ano = forms.IntegerField(
        required=False,
        label="Ano",
        min_value=2000,
        max_value=ANO_MAXIMO,
    )

    status = forms.ChoiceField(
        required=False,
        label="Status",
        choices=[
            ("", "Todos os status"),
            *Fatura.Status.choices,
        ],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _aplicar_estilo_bootstrap(self.fields)

        self.fields["apartamento"].queryset = (
            Apartamento.objects
            .order_by("bloco", "numero", "id")
        )
