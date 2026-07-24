from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apartamentos.models import Apartamento
from faturas.models import Fatura

from .forms import FiltrarLeiturasForm, LeituraForm
from .models import Leitura
from .services import (
    ExclusaoLeituraBloqueadaError,
    cadastrar_leitura,
    excluir_leitura,
    listar_leituras,
)


class ExclusaoLeituraTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="operador-exclusao-leitura",
            password="senha-de-teste",
            is_staff=True,
        )
        self.client.force_login(self.usuario)
        self.apartamento = Apartamento.objects.create(numero="801")

    def criar_leitura(self, mes=7):
        return Leitura.objects.create(
            apartamento=self.apartamento,
            mes=mes,
            ano=2026,
            leitura_agua=Decimal("10"),
        )

    def test_confirmacao_nao_exclui_por_get(self):
        leitura = self.criar_leitura()
        resposta = self.client.get(
            reverse("leituras:excluir", args=[leitura.id])
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(Leitura.objects.filter(pk=leitura.id).exists())
        self.assertContains(resposta, "Excluir permanentemente")
        self.assertContains(resposta, "futuros cálculos")

    def test_exclui_leitura_sem_fatura_e_nao_recalcula_outros_registros(self):
        leitura = self.criar_leitura(6)
        posterior = self.criar_leitura(7)

        resposta = self.client.post(
            reverse("leituras:excluir", args=[leitura.id]),
            follow=True,
        )

        self.assertRedirects(resposta, reverse("leituras:lista"))
        self.assertFalse(Leitura.objects.filter(pk=leitura.id).exists())
        self.assertTrue(Leitura.objects.filter(pk=posterior.id).exists())
        self.assertContains(resposta, "excluída permanentemente")

    def test_bloqueia_leitura_com_fatura_e_preserva_registros(self):
        leitura = self.criar_leitura()
        fatura = Fatura.objects.create(
            apartamento=self.apartamento,
            leitura=leitura,
            mes=7,
            ano=2026,
            consumo_agua=0,
            consumo_gas=0,
            apartamento_numero_emissao=self.apartamento.numero,
        )

        resposta = self.client.post(
            reverse("leituras:excluir", args=[leitura.id])
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Exclua primeiro a fatura correspondente")
        self.assertNotContains(resposta, "Excluir permanentemente")
        self.assertTrue(Leitura.objects.filter(pk=leitura.id).exists())
        self.assertTrue(Fatura.objects.filter(pk=fatura.id).exists())

    def test_id_inexistente_retorna_404(self):
        resposta = self.client.get(reverse("leituras:excluir", args=[999999]))
        self.assertEqual(resposta.status_code, 404)

    def test_usuario_nao_staff_nao_pode_excluir(self):
        leitura = self.criar_leitura()
        usuario = get_user_model().objects.create_user(
            username="morador-exclusao-leitura",
            password="senha-de-teste",
        )
        self.client.force_login(usuario)

        resposta = self.client.post(
            reverse("leituras:excluir", args=[leitura.id])
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(Leitura.objects.filter(pk=leitura.id).exists())

    def test_service_bloqueia_chamada_direta(self):
        leitura = self.criar_leitura()
        Fatura.objects.create(
            apartamento=self.apartamento,
            leitura=leitura,
            mes=7,
            ano=2026,
            consumo_agua=0,
            consumo_gas=0,
            apartamento_numero_emissao=self.apartamento.numero,
        )

        with self.assertRaises(ExclusaoLeituraBloqueadaError):
            excluir_leitura(leitura.id)

        self.assertTrue(Leitura.objects.filter(pk=leitura.id).exists())


class LeituraFormPresentationTests(TestCase):
    def test_widgets_preservam_restricoes_e_recebem_estilo_bootstrap(self):
        form = LeituraForm()

        self.assertEqual(form.fields["mes"].widget.attrs["min"], 1)
        self.assertEqual(form.fields["mes"].widget.attrs["max"], 12)
        self.assertEqual(form.fields["leitura_agua"].widget.attrs["step"], "0.01")
        self.assertEqual(form.fields["ano"].widget.attrs["class"], "form-control")

    def test_formulario_de_filtros_usa_componentes_bootstrap(self):
        form = FiltrarLeiturasForm()

        self.assertEqual(
            form.fields["apartamento"].widget.attrs["class"],
            "form-select",
        )
        self.assertEqual(form.fields["mes"].widget.attrs["class"], "form-select")
        self.assertEqual(form.fields["ano"].widget.attrs["class"], "form-control")


class FiltrosLeituraTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.apartamento_a = Apartamento.objects.create(numero="101", bloco="A")
        cls.apartamento_b = Apartamento.objects.create(numero="202", bloco="B")
        cls.leitura_alvo = Leitura.objects.create(
            apartamento=cls.apartamento_a,
            mes=7,
            ano=2026,
            leitura_agua=Decimal("10.00"),
        )
        Leitura.objects.create(
            apartamento=cls.apartamento_a,
            mes=6,
            ano=2026,
            leitura_agua=Decimal("9.00"),
        )
        Leitura.objects.create(
            apartamento=cls.apartamento_b,
            mes=7,
            ano=2026,
            leitura_agua=Decimal("8.00"),
        )

    def test_servico_combina_todos_os_filtros(self):
        resultados = list(
            listar_leituras(
                apartamento_id=self.apartamento_a.id,
                bloco="A",
                mes=7,
                ano=2026,
            )
        )

        self.assertEqual(resultados, [self.leitura_alvo])

    def test_listagem_preserva_ordenacao_e_resolve_faturas_sem_n_mais_um(self):
        Fatura.objects.create(
            apartamento=self.apartamento_a,
            leitura=self.leitura_alvo,
            mes=7,
            ano=2026,
            consumo_agua=0,
            consumo_gas=0,
        )

        with self.assertNumQueries(1):
            resultados = list(listar_leituras())
            competencias = [
                (
                    leitura.ano,
                    leitura.mes,
                    leitura.id,
                    leitura.apartamento.numero,
                    leitura.fatura_competencia_id,
                )
                for leitura in resultados
            ]

        self.assertEqual(
            [(ano, mes) for ano, mes, _, _, _ in competencias],
            [(2026, 7), (2026, 7), (2026, 6)],
        )
        fatura_por_leitura = {
            leitura_id: fatura_id
            for _, _, leitura_id, _, fatura_id in competencias
        }
        self.assertIsNotNone(fatura_por_leitura[self.leitura_alvo.id])


class IntegridadeLeituraTests(TestCase):
    def setUp(self):
        self.apartamento = Apartamento.objects.create(
            numero="101",
            leitura_base_agua=Decimal("10.00"),
            leitura_base_gas=Decimal("5.00"),
        )

    def test_banco_rejeita_periodo_medicao_e_duplicidade_invalidos(self):
        casos = [
            {"mes": 13, "ano": 2026, "leitura_agua": Decimal("10.00")},
            {"mes": 1, "ano": 1999, "leitura_agua": Decimal("10.00")},
            {"mes": 1, "ano": 2026, "leitura_agua": Decimal("-1.00")},
            {"mes": 1, "ano": 2026, "leitura_agua": Decimal("1000000.00")},
            {"mes": 1, "ano": 2026, "leitura_agua": None, "leitura_gas": None},
        ]
        for dados in casos:
            with self.subTest(dados=dados):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Leitura.objects.create(
                        apartamento=self.apartamento,
                        **dados,
                    )

        Leitura.objects.create(
            apartamento=self.apartamento,
            mes=1,
            ano=2026,
            leitura_agua=Decimal("10.00"),
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            Leitura.objects.create(
                apartamento=self.apartamento,
                mes=1,
                ano=2026,
                leitura_gas=Decimal("5.00"),
            )

    def test_service_rejeita_regressao_em_relacao_a_leitura_anterior(self):
        cadastrar_leitura(
            apartamento=self.apartamento,
            mes=1,
            ano=2026,
            leitura_agua=Decimal("20.00"),
            leitura_gas=Decimal("10.00"),
        )

        with self.assertRaisesRegex(ValueError, "medição anterior"):
            cadastrar_leitura(
                apartamento=self.apartamento,
                mes=2,
                ano=2026,
                leitura_agua=Decimal("19.99"),
                leitura_gas=Decimal("10.00"),
            )


class LeituraPresentationTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="operador-leituras",
            password="senha-de-teste",
            is_staff=True,
        )
        self.client.force_login(usuario)
        self.apartamento = Apartamento.objects.create(
            numero="101",
            bloco="A",
            leitura_base_agua=Decimal("0.00"),
            leitura_base_gas=Decimal("0.00"),
        )

    def test_lista_usa_layout_padrao_e_exibe_estado_vazio(self):
        resposta = self.client.get(reverse("leituras:lista"))

        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, "leituras/lista.html")
        self.assertTemplateUsed(resposta, "base.html")
        self.assertContains(resposta, "Nenhuma leitura cadastrada")
        self.assertContains(resposta, reverse("apartamentos:lista"))

    def test_lista_exibe_leitura_e_link_explicito_para_apartamento(self):
        leitura = Leitura.objects.create(
            apartamento=self.apartamento,
            mes=7,
            ano=2026,
            leitura_agua=Decimal("12.50"),
            leitura_gas=Decimal("4.25"),
        )

        resposta = self.client.get(reverse("leituras:lista"))

        self.assertContains(resposta, "07/2026")
        self.assertContains(resposta, "12,50")
        self.assertContains(
            resposta,
            reverse("apartamentos:detalhes", args=[self.apartamento.id]),
        )
        self.assertContains(resposta, "Ações")
        self.assertContains(resposta, "Gerar fatura")
        self.assertContains(
            resposta,
            f"{reverse('faturas:gerar')}?leitura={leitura.id}",
        )

    def test_lista_exibe_acao_para_visualizar_fatura_existente(self):
        leitura = Leitura.objects.create(
            apartamento=self.apartamento,
            mes=7,
            ano=2026,
            leitura_agua=Decimal("12.50"),
            leitura_gas=Decimal("4.25"),
        )
        fatura = Fatura.objects.create(
            apartamento=self.apartamento,
            leitura=leitura,
            mes=7,
            ano=2026,
            consumo_agua=0,
            consumo_gas=0,
        )

        resposta = self.client.get(reverse("leituras:lista"))

        self.assertContains(resposta, "Ver fatura")
        self.assertContains(
            resposta,
            reverse("faturas:detalhes", args=[fatura.id]),
        )
        self.assertNotContains(
            resposta,
            f"{reverse('faturas:gerar')}?leitura={leitura.id}",
        )

    def test_lista_filtra_e_mantem_parametros_preenchidos(self):
        outra_unidade = Apartamento.objects.create(numero="202", bloco="B")
        Leitura.objects.create(
            apartamento=self.apartamento,
            mes=7,
            ano=2026,
            leitura_agua=Decimal("12.50"),
        )
        Leitura.objects.create(
            apartamento=outra_unidade,
            mes=6,
            ano=2025,
            leitura_agua=Decimal("8.00"),
        )

        resposta = self.client.get(
            reverse("leituras:lista"),
            {
                "apartamento": self.apartamento.id,
                "bloco": "A",
                "mes": "7",
                "ano": "2026",
            },
        )

        self.assertContains(resposta, "07/2026")
        self.assertNotContains(resposta, "06/2025")
        self.assertContains(
            resposta,
            f'<option value="{self.apartamento.id}" selected>',
            html=False,
        )
        self.assertContains(resposta, 'value="A"')
        self.assertContains(resposta, 'value="2026"')
        self.assertContains(resposta, "Limpar filtros")

    def test_nova_leitura_usa_formulario_padrao_e_link_de_cancelamento(self):
        resposta = self.client.get(
            reverse("leituras:nova", args=[self.apartamento.id]),
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, "leituras/nova.html")
        self.assertTemplateUsed(resposta, "components/form_field.html")
        self.assertContains(resposta, "Salvar leitura")
        self.assertContains(
            resposta,
            reverse("apartamentos:detalhes", args=[self.apartamento.id]),
        )

    def test_nova_leitura_exibe_erro_essencial_sem_medicoes(self):
        resposta = self.client.post(
            reverse("leituras:nova", args=[self.apartamento.id]),
            {"mes": "7", "ano": "2026", "leitura_agua": "", "leitura_gas": ""},
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Informe pelo menos uma leitura")
