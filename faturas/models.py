from django.db import models
from apartamentos.models import Apartamento
from leituras.models import Leitura


class Fatura(models.Model):
    apartamento = models.ForeignKey(Apartamento, on_delete=models.CASCADE)
    leitura = models.ForeignKey(
        Leitura,
        on_delete=models.SET_NULL,
        blank=True,
        null=True
    )
    mes = models.IntegerField()
    ano = models.IntegerField()
    consumo_agua = models.FloatField()
    consumo_gas = models.FloatField()
    valor_agua = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    valor_gas = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    valor_total = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    status = models.TextField(blank=True, null=True)
    data_geracao = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "faturas"

    def __str__(self):
        return f"Fatura {self.mes}/{self.ano} - {self.apartamento}"
