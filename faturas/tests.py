from decimal import Decimal

from django.test import TestCase

from apartamentos.models import Apartamento
from leituras.models import Leitura

from .models import Fatura
from .services import gerar_fatura_mensal


class GerarFaturaMensalTests(TestCase):
    def setUp(self):
        self.apartamento = Apartamento.objects.create(
            numero="101",
            bloco="A",
        )

    def configurar_leituras_base(
        self,
        agua=Decimal("0.00"),
        gas=Decimal("0.00"),
    ):
        self.apartamento.leitura_base_agua = agua
        self.apartamento.leitura_base_gas = gas
        self.apartamento.save(
            update_fields=[
                "leitura_base_agua",
                "leitura_base_gas",
            ]
        )

    def criar_leitura(
        self,
        mes,
        ano,
        leitura_agua,
        leitura_gas,
    ):
        return Leitura.objects.create(
            apartamento=self.apartamento,
            mes=mes,
            ano=ano,
            leitura_agua=leitura_agua,
            leitura_gas=leitura_gas,
        )

    def test_gera_fatura_usando_leitura_anterior(self):
        self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=Decimal("100.50"),
            leitura_gas=Decimal("20.25"),
        )

        leitura_atual = self.criar_leitura(
            mes=2,
            ano=2026,
            leitura_agua=Decimal("108.20"),
            leitura_gas=Decimal("23.99"),
        )

        fatura = gerar_fatura_mensal(leitura_atual.id)

        # Água: 108,20 - 100,50 = 7,70
        # Gás: 23,99 - 20,25 = 3,74
        # As casas decimais do consumo são descartadas.
        self.assertEqual(fatura.consumo_agua, 7)
        self.assertEqual(fatura.consumo_gas, 3)

        self.assertEqual(
            fatura.valor_agua,
            Decimal("108.20"),
        )
        self.assertEqual(
            fatura.valor_gas,
            Decimal("63.06"),
        )
        self.assertEqual(
            fatura.valor_total,
            Decimal("171.26"),
        )

    def test_usa_a_leitura_anterior_mais_recente(self):
        self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=Decimal("100.00"),
            leitura_gas=Decimal("20.00"),
        )

        self.criar_leitura(
            mes=2,
            ano=2026,
            leitura_agua=Decimal("105.00"),
            leitura_gas=Decimal("22.00"),
        )

        leitura_atual = self.criar_leitura(
            mes=3,
            ano=2026,
            leitura_agua=Decimal("111.90"),
            leitura_gas=Decimal("25.80"),
        )

        fatura = gerar_fatura_mensal(leitura_atual.id)

        # Deve comparar março com fevereiro, não com janeiro.
        self.assertEqual(fatura.consumo_agua, 6)
        self.assertEqual(fatura.consumo_gas, 3)

    def test_ignora_leituras_futuras_ao_buscar_anterior(self):
        self.configurar_leituras_base(
            agua=Decimal("100.00"),
            gas=Decimal("20.00"),
        )

        leitura_atual = self.criar_leitura(
            mes=6,
            ano=2026,
            leitura_agua=Decimal("108.00"),
            leitura_gas=Decimal("23.00"),
        )

        self.criar_leitura(
            mes=7,
            ano=2026,
            leitura_agua=Decimal("115.00"),
            leitura_gas=Decimal("27.00"),
        )

        fatura = gerar_fatura_mensal(leitura_atual.id)

        # Deve ignorar julho e comparar junho com as leituras-base.
        self.assertEqual(fatura.consumo_agua, 8)
        self.assertEqual(fatura.consumo_gas, 3)

    def test_impede_gerar_fatura_duplicada(self):
        self.configurar_leituras_base(
            agua=Decimal("95.00"),
            gas=Decimal("18.00"),
        )

        leitura = self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=Decimal("100.00"),
            leitura_gas=Decimal("20.00"),
        )

        gerar_fatura_mensal(leitura.id)

        with self.assertRaisesMessage(
            ValueError,
            "Já existe uma fatura para este apartamento neste mês e ano.",
        ):
            gerar_fatura_mensal(leitura.id)

        self.assertEqual(Fatura.objects.count(), 1)

    def test_impede_fatura_sem_leitura_de_agua(self):
        leitura = self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=None,
            leitura_gas=Decimal("20.00"),
        )

        with self.assertRaisesMessage(
            ValueError,
            "A leitura precisa possuir valores de água e gás",
        ):
            gerar_fatura_mensal(leitura.id)

        self.assertEqual(Fatura.objects.count(), 0)

    def test_impede_fatura_sem_leitura_de_gas(self):
        leitura = self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=Decimal("100.00"),
            leitura_gas=None,
        )

        with self.assertRaisesMessage(
            ValueError,
            "A leitura precisa possuir valores de água e gás",
        ):
            gerar_fatura_mensal(leitura.id)

        self.assertEqual(Fatura.objects.count(), 0)

    def test_fatura_e_criada_com_status_pendente(self):
        self.configurar_leituras_base(
            agua=Decimal("95.00"),
            gas=Decimal("18.00"),
        )

        leitura = self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=Decimal("100.00"),
            leitura_gas=Decimal("20.00"),
        )

        fatura = gerar_fatura_mensal(leitura.id)

        self.assertEqual(
            fatura.status,
            Fatura.Status.PENDENTE,
        )

    def test_primeira_fatura_usa_leitura_base_do_apartamento(self):
        self.configurar_leituras_base(
            agua=Decimal("100.50"),
            gas=Decimal("20.25"),
        )

        leitura = self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=Decimal("108.20"),
            leitura_gas=Decimal("23.99"),
        )

        fatura = gerar_fatura_mensal(leitura.id)

        self.assertEqual(fatura.consumo_agua, 7)
        self.assertEqual(fatura.consumo_gas, 3)

        self.assertEqual(
            fatura.valor_agua,
            Decimal("108.20"),
        )
        self.assertEqual(
            fatura.valor_gas,
            Decimal("63.06"),
        )
        self.assertEqual(
            fatura.valor_total,
            Decimal("171.26"),
        )

    def test_primeira_fatura_pode_usar_leituras_base_zero(self):
        self.configurar_leituras_base()

        leitura = self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=Decimal("7.80"),
            leitura_gas=Decimal("3.40"),
        )

        fatura = gerar_fatura_mensal(leitura.id)

        self.assertEqual(fatura.consumo_agua, 7)
        self.assertEqual(fatura.consumo_gas, 3)

        self.assertEqual(
            fatura.valor_agua,
            Decimal("108.20"),
        )
        self.assertEqual(
            fatura.valor_gas,
            Decimal("63.06"),
        )
        self.assertEqual(
            fatura.valor_total,
            Decimal("171.26"),
        )

    def test_impede_primeira_fatura_sem_leituras_base(self):
        leitura = self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=Decimal("108.20"),
            leitura_gas=Decimal("23.99"),
        )

        with self.assertRaisesMessage(
            ValueError,
            "O apartamento não possui leituras-base configuradas.",
        ):
            gerar_fatura_mensal(leitura.id)

        self.assertEqual(Fatura.objects.count(), 0)
