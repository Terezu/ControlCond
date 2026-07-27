from decimal import Decimal

from django import forms
from django.db.models import Exists, OuterRef
from django.utils import timezone

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


def _validar_bonificacao(cleaned_data, adicionar_erro):
    modo = (
        cleaned_data.get("modo_bonificacao")
        or Fatura.OrigemBonificacao.CONDOMINIO
    )
    cleaned_data["modo_bonificacao"] = modo
    tipo = cleaned_data.get("tipo_bonificacao")
    valor = cleaned_data.get("bonificacao_especifica")
    if modo == Fatura.OrigemBonificacao.ESPECIFICA:
        if not tipo:
            adicionar_erro(
                "tipo_bonificacao",
                "Informe o tipo da bonificação específica.",
            )
        if valor is None or valor <= 0:
            adicionar_erro(
                "bonificacao_especifica",
                "Informe uma bonificação específica maior que zero.",
            )
        elif (
            tipo == Fatura.TipoBonificacao.PERCENTUAL
            and valor > Decimal("100")
        ):
            adicionar_erro(
                "bonificacao_especifica",
                "O percentual deve estar entre 0 e 100.",
            )
    else:
        cleaned_data["tipo_bonificacao"] = None
        cleaned_data["bonificacao_especifica"] = None


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
    valor_condominio = forms.DecimalField(
        required=False, label="Condomínio", min_value=0,
        max_value=LIMITE_VALOR_FINANCEIRO, max_digits=10, decimal_places=2,
        widget=forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
    )
    valor_iptu = forms.DecimalField(
        required=False, label="IPTU", min_value=0,
        max_value=LIMITE_VALOR_FINANCEIRO, max_digits=10, decimal_places=2,
        widget=forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
    )
    valor_outros = forms.DecimalField(
        required=False, label="Outros",
        min_value=-LIMITE_VALOR_FINANCEIRO,
        max_value=LIMITE_VALOR_FINANCEIRO,
        max_digits=10, decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01"}),
    )
    observacao_outros = forms.CharField(
        required=False,
        label="Motivo de Outros",
        max_length=255,
    )
    modo_bonificacao = forms.ChoiceField(
        required=False,
        label="Bonificação",
        choices=Fatura.OrigemBonificacao.choices,
        initial=Fatura.OrigemBonificacao.CONDOMINIO,
    )
    tipo_bonificacao = forms.ChoiceField(
        required=False,
        label="Tipo da bonificação específica",
        choices=(
            ("", "Selecione o tipo"),
            *[
                escolha
                for escolha in Fatura.TipoBonificacao.choices
                if escolha[0] != Fatura.TipoBonificacao.NENHUMA
            ],
        ),
    )
    bonificacao_especifica = forms.DecimalField(
        required=False,
        label="Percentual ou valor específico",
        min_value=0,
        max_value=LIMITE_VALOR_FINANCEIRO,
        max_digits=11,
        decimal_places=3,
        widget=forms.NumberInput(attrs={"min": "0", "step": "0.001"}),
    )

    def __init__(self, *args, **kwargs):
        condominio = kwargs.pop("condominio", None)
        if condominio is None:
            from condominios.models import Condominio
            condominio = Condominio.objects.order_by("id").first()
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
                apartamento__condominio=condominio,
                leitura_agua__isnull=False,
                leitura_gas__isnull=False,
                fatura_existente=False,
            )
            .order_by("-ano", "-mes", "apartamento__numero")
        )

        self.fields["leitura"].label_from_instance = self.descrever_leitura

    def clean_desconto(self):
        return self.cleaned_data["desconto"] or Decimal("0.00")

    def clean(self):
        cleaned_data = super().clean()
        for campo in (
            "valor_condominio",
            "valor_iptu",
            "valor_outros",
        ):
            if campo in cleaned_data:
                cleaned_data[campo] = cleaned_data[campo] or Decimal("0.00")
        if (
            cleaned_data.get("valor_outros", Decimal("0.00")) != 0
            and not cleaned_data.get("observacao_outros", "").strip()
        ):
            self.add_error(
                "observacao_outros",
                "Informe o motivo quando Outros for diferente de zero.",
            )
        _validar_bonificacao(cleaned_data, self.add_error)
        return cleaned_data

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


class FechamentoMensalForm(forms.Form):
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
        _aplicar_estilo_bootstrap(self.fields)
        hoje = timezone.localdate()
        self.fields["mes"].initial = hoje.month
        self.fields["ano"].initial = hoje.year


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


class RegistrarPagamentoForm(forms.Form):
    data_pagamento = forms.DateField(
        required=False,
        label="Data do pagamento",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    forma_pagamento = forms.ChoiceField(
        label="Forma de pagamento",
        choices=tuple(
            escolha
            for escolha in Fatura.FormaPagamento.choices
            if escolha[0] != Fatura.FormaPagamento.NAO_INFORMADA
        ),
    )
    observacoes_pagamento = forms.CharField(
        required=False,
        label="Observações",
        max_length=500,
        strip=True,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _aplicar_estilo_bootstrap(self.fields)
        self.fields["data_pagamento"].initial = timezone.localdate()

    def clean_data_pagamento(self):
        return self.cleaned_data["data_pagamento"] or timezone.localdate()


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
    valor_condominio = forms.DecimalField(
        required=False, label="Condomínio", min_value=0,
        max_value=LIMITE_VALOR_FINANCEIRO,
        max_digits=10, decimal_places=2,
        widget=forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
    )
    valor_iptu = forms.DecimalField(
        required=False, label="IPTU", min_value=0,
        max_value=LIMITE_VALOR_FINANCEIRO,
        max_digits=10, decimal_places=2,
        widget=forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
    )
    valor_outros = forms.DecimalField(
        required=False, label="Outros",
        min_value=-LIMITE_VALOR_FINANCEIRO,
        max_value=LIMITE_VALOR_FINANCEIRO,
        max_digits=10, decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01"}),
    )
    observacao_outros = forms.CharField(
        required=False, label="Motivo de Outros", max_length=255,
    )
    modo_bonificacao = forms.ChoiceField(
        required=False,
        label="Bonificação",
        choices=Fatura.OrigemBonificacao.choices,
    )
    tipo_bonificacao = forms.ChoiceField(
        required=False,
        label="Tipo da bonificação específica",
        choices=(
            ("", "Selecione o tipo"),
            *[
                escolha
                for escolha in Fatura.TipoBonificacao.choices
                if escolha[0] != Fatura.TipoBonificacao.NENHUMA
            ],
        ),
    )
    bonificacao_especifica = forms.DecimalField(
        required=False,
        label="Percentual ou valor específico",
        min_value=0,
        max_value=LIMITE_VALOR_FINANCEIRO,
        max_digits=11,
        decimal_places=3,
        widget=forms.NumberInput(attrs={"min": "0", "step": "0.001"}),
    )

    def __init__(self, *args, fatura=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fatura = fatura
        _aplicar_estilo_bootstrap(self.fields)
        if fatura is not None:
            self.fields["valor_aluguel"].initial = fatura.valor_aluguel
            self.fields["desconto"].initial = fatura.desconto
            for campo in (
                "valor_condominio", "valor_iptu", "valor_outros",
                "observacao_outros",
            ):
                self.fields[campo].initial = getattr(
                    fatura,
                    campo,
                    None,
                )
            self.fields["modo_bonificacao"].initial = (
                getattr(
                    fatura,
                    "origem_bonificacao_emissao",
                    Fatura.OrigemBonificacao.CONDOMINIO,
                )
            )
            tipo_emissao = getattr(
                fatura,
                "tipo_bonificacao_emissao",
                Fatura.TipoBonificacao.NENHUMA,
            )
            self.fields["tipo_bonificacao"].initial = (
                tipo_emissao
                if tipo_emissao != Fatura.TipoBonificacao.NENHUMA
                else ""
            )
            self.fields["bonificacao_especifica"].initial = (
                getattr(fatura, "percentual_bonificacao_emissao", None)
                if tipo_emissao
                == Fatura.TipoBonificacao.PERCENTUAL
                else getattr(
                    fatura,
                    "valor_bonificacao_fixa_emissao",
                    None,
                )
            )

    def clean_desconto(self):
        return self.cleaned_data["desconto"] or Decimal("0.00")

    def clean(self):
        cleaned_data = super().clean()
        valor_outros = cleaned_data.get("valor_outros")
        if (
            valor_outros not in (None, Decimal("0.00"))
            and not cleaned_data.get("observacao_outros", "").strip()
        ):
            self.add_error(
                "observacao_outros",
                "Informe o motivo quando Outros for diferente de zero.",
            )
        _validar_bonificacao(cleaned_data, self.add_error)
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
        condominio = kwargs.pop("condominio", None)
        if condominio is None:
            from condominios.models import Condominio
            condominio = Condominio.objects.order_by("id").first()
        super().__init__(*args, **kwargs)
        _aplicar_estilo_bootstrap(self.fields)

        self.fields["apartamento"].queryset = (
            Apartamento.objects
            .filter(condominio=condominio)
            .order_by("bloco", "numero", "id")
        )
