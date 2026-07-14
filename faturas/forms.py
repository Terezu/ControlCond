from django import forms

from leituras.models import Leitura


class GerarFaturaForm(forms.Form):
    leitura = forms.ModelChoiceField(
        queryset=Leitura.objects.none(),
        label="Leitura",
        empty_label="Selecione uma leitura",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["leitura"].queryset = (
            Leitura.objects
            .select_related("apartamento")
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
    