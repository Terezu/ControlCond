from django import forms
from django.db.models import Exists, OuterRef

from apartamentos.models import Apartamento
from leituras.models import Leitura

from .models import Fatura, ANO_MAXIMO


class GerarFaturaForm(forms.Form):
    leitura = forms.ModelChoiceField(
        queryset=Leitura.objects.none(),
        label="Leitura",
        empty_label="Selecione uma leitura",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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

class AlterarStatusFaturaForm(forms.Form):
    status = forms.ChoiceField(
        choices=Fatura.Status.choices,
        label="Novo status",
    )

    def __init__(self, *args, fatura=None, **kwargs):
        super().__init__(*args, **kwargs)

        if fatura is not None:
            self.fields["status"].initial = fatura.status


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

        self.fields["apartamento"].queryset = (
            Apartamento.objects
            .order_by("bloco", "numero", "id")
        )