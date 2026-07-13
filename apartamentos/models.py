from django.db import models


class Apartamento(models.Model):
    numero = models.CharField(max_length=20)
    bloco = models.CharField(max_length=50, blank=True, null=True)
    observacoes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "apartamentos"
        ordering = ["bloco", "numero"]

    def __str__(self):
        if self.bloco:
            return f"Apartamento {self.numero} - Bloco {self.bloco}"
        return f"Apartamento {self.numero}"