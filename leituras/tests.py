from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apartamentos.models import Apartamento
from faturas.models import Fatura

from .models import Leitura
from .services import (
    buscar_ultimas_leituras,
    cadastrar_leitura,
    editar_leitura,
    listar_leituras,
)


class ValidacaoLeituraTests(TestCase):
    def setUp(self):
        self.apartamento = Apartamento.objects.create(
            numero="101",
            leitura_base_agua=Decimal("0.00"),
            leitura_base_gas=Decimal("0.00"),
        )

    def test_servico_rejeita_ano_invalido_e_valor_negativo(self):
        with self.assertRaises(ValueError):
            cadastrar_leitura(
                self.apartamento,
                mes=1,
                ano=1999,
                leitura_agua=Decimal("1.00"),
            )

        with self.assertRaises(ValueError):
            cadastrar_leitura(
                self.apartamento,
                mes=1,
                ano=2026,
                leitura_gas=Decimal("-1.00"),
            )

        with self.assertRaises(ValueError):
            cadastrar_leitura(
                self.apartamento,
                mes=1,
                ano=10000,
                leitura_agua=Decimal("1.00"),
            )

        self.assertEqual(Leitura.objects.count(), 0)

    def test_edicao_aplica_as_mesmas_validacoes_do_cadastro(self):
        leitura = cadastrar_leitura(
            self.apartamento,
            mes=1,
            ano=2026,
            leitura_agua=Decimal("1.00"),
        )

        with self.assertRaises(ValueError):
            editar_leitura(
                leitura.id,
                mes=13,
                ano=2026,
                leitura_agua=Decimal("1.00"),
            )

        leitura.refresh_from_db()
        self.assertEqual(leitura.mes, 1)


    def test_banco_rejeita_leitura_sem_agua_e_sem_gas(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Leitura.objects.create(
                apartamento=self.apartamento,
                mes=1,
                ano=2026,
            )

    def test_banco_rejeita_ano_fora_do_intervalo_de_datas(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Leitura.objects.create(
                apartamento=self.apartamento,
                mes=1,
                ano=10000,
                leitura_agua=Decimal("1.00"),
            )

    def test_servico_rejeita_booleano_como_mes(self):
        with self.assertRaisesRegex(ValueError, "mês"):
            cadastrar_leitura(
                self.apartamento,
                mes=True,
                ano=2026,
                leitura_agua=Decimal("1.00"),
            )

    def test_busca_rejeita_limite_invalido(self):
        for limite in (-1, True, "12"):
            with self.subTest(limite=limite), self.assertRaises(ValueError):
                buscar_ultimas_leituras(self.apartamento.id, limite)

    def test_rejeita_leitura_menor_que_a_base(self):
        self.apartamento.leitura_base_agua = Decimal("10.00")
        self.apartamento.save(update_fields=["leitura_base_agua"])

        with self.assertRaisesRegex(ValueError, "leitura-base"):
            cadastrar_leitura(
                self.apartamento,
                mes=1,
                ano=2026,
                leitura_agua=Decimal("9.99"),
            )

    def test_rejeita_leitura_menor_que_a_medicao_anterior(self):
        cadastrar_leitura(
            self.apartamento,
            mes=1,
            ano=2026,
            leitura_agua=Decimal("10.00"),
        )

        with self.assertRaisesRegex(ValueError, "medição anterior"):
            cadastrar_leitura(
                self.apartamento,
                mes=2,
                ano=2026,
                leitura_agua=Decimal("9.99"),
            )

    def test_rejeita_leitura_retroativa_maior_que_a_posterior(self):
        cadastrar_leitura(
            self.apartamento,
            mes=3,
            ano=2026,
            leitura_gas=Decimal("20.00"),
        )

        with self.assertRaisesRegex(ValueError, "medição posterior"):
            cadastrar_leitura(
                self.apartamento,
                mes=2,
                ano=2026,
                leitura_gas=Decimal("20.01"),
            )

    def test_compara_historicos_de_agua_e_gas_separadamente(self):
        cadastrar_leitura(
            self.apartamento,
            mes=1,
            ano=2026,
            leitura_agua=Decimal("10.00"),
        )
        cadastrar_leitura(
            self.apartamento,
            mes=2,
            ano=2026,
            leitura_gas=Decimal("5.00"),
        )

        leitura = cadastrar_leitura(
            self.apartamento,
            mes=3,
            ano=2026,
            leitura_agua=Decimal("11.00"),
            leitura_gas=Decimal("6.00"),
        )

        self.assertEqual(leitura.leitura_agua, Decimal("11.00"))
        self.assertEqual(leitura.leitura_gas, Decimal("6.00"))

    def test_nao_altera_periodo_de_leitura_ja_faturada(self):
        leitura = cadastrar_leitura(
            self.apartamento,
            mes=1,
            ano=2026,
            leitura_agua=Decimal("10.00"),
            leitura_gas=Decimal("5.00"),
        )
        Fatura.objects.create(
            apartamento=self.apartamento,
            leitura=leitura,
            mes=1,
            ano=2026,
            consumo_agua=10,
            consumo_gas=5,
            valor_agua=Decimal("10.00"),
            valor_gas=Decimal("5.00"),
            valor_total=Decimal("15.00"),
        )

        with self.assertRaisesRegex(ValueError, "já faturada"):
            editar_leitura(
                leitura.id,
                mes=2,
                ano=2026,
                leitura_agua=Decimal("10.00"),
                leitura_gas=Decimal("5.00"),
            )

        leitura.refresh_from_db()
        self.assertEqual(leitura.mes, 1)


class ListaLeiturasTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        self.usuario = get_user_model().objects.create_user(
            username="funcionario",
            password="senha-segura",
            is_staff=True,
        )
        self.apartamento = Apartamento.objects.create(numero="101")

    def test_lista_exige_usuario_staff(self):
        resposta = self.client.get(reverse("leituras:lista"))

        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("admin:login"), resposta.url)

    def test_lista_exibe_leituras_mais_recentes_primeiro(self):
        antiga = cadastrar_leitura(
            self.apartamento,
            mes=12,
            ano=2025,
            leitura_agua=Decimal("10.00"),
        )
        recente = cadastrar_leitura(
            self.apartamento,
            mes=1,
            ano=2026,
            leitura_agua=Decimal("11.00"),
        )
        self.client.force_login(self.usuario)

        resposta = self.client.get(reverse("leituras:lista"))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(list(resposta.context["leituras"]), [recente, antiga])
        self.assertContains(resposta, "01/2026")

    def test_servico_ainda_permite_filtrar_por_apartamento(self):
        outra = Apartamento.objects.create(numero="102")
        esperada = cadastrar_leitura(
            self.apartamento,
            mes=1,
            ano=2026,
            leitura_agua=Decimal("1.00"),
        )
        cadastrar_leitura(
            outra,
            mes=1,
            ano=2026,
            leitura_agua=Decimal("1.00"),
        )

        self.assertEqual(list(listar_leituras(self.apartamento)), [esperada])
