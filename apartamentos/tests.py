from decimal import Decimal

from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse

from faturas.models import Fatura
from leituras.models import Leitura

from .models import Apartamento
from .forms import ApartamentoForm
from .services import cadastrar_apartamento, editar_apartamento


class ApartamentoFormTests(TestCase):
    def test_exige_as_duas_leituras_base(self):
        form = ApartamentoForm(
            data={
                "numero": "101",
                "bloco": "A",
                "leitura_base_agua": "",
                "leitura_base_gas": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("leitura_base_agua", form.errors)
        self.assertIn("leitura_base_gas", form.errors)

    def test_aceita_leituras_base_zero(self):
        form = ApartamentoForm(
            data={
                "numero": "101",
                "leitura_base_agua": "0",
                "leitura_base_gas": "0",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)


class FluxoApartamentoTests(TestCase):
    def test_cadastra_apartamento_com_leituras_base(self):
        resposta = self.client.post(
            reverse("apartamentos:novo"),
            {
                "numero": "202",
                "bloco": "B",
                "leitura_base_agua": "100.50",
                "leitura_base_gas": "20.25",
                "observacoes": "Medidores conferidos",
            },
        )

        apartamento = Apartamento.objects.get(numero="202")
        self.assertRedirects(
            resposta,
            reverse("apartamentos:detalhes", args=[apartamento.id]),
        )
        self.assertEqual(apartamento.leitura_base_agua, Decimal("100.50"))
        self.assertEqual(apartamento.leitura_base_gas, Decimal("20.25"))

    def test_edita_as_leituras_base(self):
        apartamento = cadastrar_apartamento(
            numero="202",
            leitura_base_agua=Decimal("100.00"),
            leitura_base_gas=Decimal("20.00"),
        )

        editar_apartamento(
            apartamento.id,
            numero="202",
            leitura_base_agua=Decimal("101.00"),
            leitura_base_gas=Decimal("21.00"),
        )

        apartamento.refresh_from_db()
        self.assertEqual(apartamento.leitura_base_agua, Decimal("101.00"))
        self.assertEqual(apartamento.leitura_base_gas, Decimal("21.00"))


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
