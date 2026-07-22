from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apartamentos.models import Apartamento
from faturas.models import Fatura


class DashboardTemplateTests(TestCase):
    def test_cards_e_valores_usam_as_classes_do_dashboard(self):
        resposta = self.client.get(reverse("dashboard:inicio"))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "card card-dashboard shadow-sm h-100", 4)
        self.assertContains(resposta, "dashboard-value mb-0", 4)
        self.assertContains(
            resposta,
            'class="fs-5 fw-semibold dashboard-value mb-0"',
            1,
        )
        self.assertContains(resposta, 'class="card shadow-sm mt-5"', 1)
        self.assertContains(resposta, 'class="card-header bg-light py-3"', 1)

    def test_exibe_valor_total_das_faturas_pendentes(self):
        apartamento = Apartamento.objects.create(numero="101")
        Fatura.objects.create(
            apartamento=apartamento,
            mes=1,
            ano=2026,
            consumo_agua=Decimal("0.00"),
            consumo_gas=Decimal("0.00"),
            valor_agua=Decimal("123.45"),
            valor_gas=Decimal("0.00"),
            valor_total=Decimal("123.45"),
            status=Fatura.Status.PENDENTE,
        )

        resposta = self.client.get(reverse("dashboard:inicio"))

        self.assertContains(resposta, "R$ 123,45")
        self.assertContains(
            resposta,
            f'href="{reverse("faturas:detalhes", args=[1])}"',
        )
        self.assertContains(resposta, 'class="clickable-row"', 1)
