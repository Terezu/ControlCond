from django.db import models
from apartamentos.models import Apartamento


class Leitura(models.Model):
    apartamento = models.ForeignKey(Apartamento, on_delete=models.CASCADE)
    mes = models.IntegerField()
    ano = models.IntegerField()
    leitura_agua = models.FloatField(blank=True, null=True)
    leitura_gas = models.FloatField(blank=True, null=True)
    data_registro = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "leituras"

    def __str__(self):
        return f"Leitura {self.mes}/{self.ano} - {self.apartamento}"