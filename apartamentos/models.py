from django.db import models


class Apartamento(models.Model):
    numero = models.TextField()
    bloco = models.TextField(blank=True, null=True)
    observacoes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "apartamentos"

    def __str__(self):
        if self.bloco:
            return f"Apartamento {self.numero} - Bloco {self.bloco}"
        return f"Apartamento {self.numero}"