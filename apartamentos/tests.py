from django.db.models.deletion import ProtectedError
from django.test import TestCase

from faturas.models import Fatura
from leituras.models import Leitura

from .models import Apartamento


class ProtecaoApartamentoTest(TestCase):
    def setUp(self):
        self.apartamento = Apartamento.objects.create(numero="101")

    def test_nao_exclui_apartamento_com_leitura(self):
        leitura = Leitura.objects.create(
            apartamento=self.apartamento,
            mes=7,
            ano=2026,
        )

        with self.assertRaises(ProtectedError):
            self.apartamento.delete()

        self.assertTrue(Leitura.objects.filter(pk=leitura.pk).exists())

    def test_nao_exclui_apartamento_com_fatura(self):
        fatura = Fatura.objects.create(
            apartamento=self.apartamento,
            mes=7,
            ano=2026,
            consumo_agua=0,
            consumo_gas=0,
        )

        with self.assertRaises(ProtectedError):
            self.apartamento.delete()

        self.assertTrue(Fatura.objects.filter(pk=fatura.pk).exists())
