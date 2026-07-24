from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse

from faturas.models import Fatura
from leituras.models import Leitura

from .models import Apartamento
from .forms import ApartamentoForm, FiltrarApartamentosForm
from .services import (
    ExclusaoApartamentoBloqueadaError,
    cadastrar_apartamento,
    editar_apartamento,
    excluir_apartamento,
    listar_apartamentos,
)


class ExclusaoApartamentoTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="operador-exclusao-apartamento",
            password="senha-de-teste",
            is_staff=True,
        )
        self.client.force_login(self.usuario)

    def test_confirmacao_nao_exclui_por_get_e_exibe_csrf(self):
        apartamento = Apartamento.objects.create(numero="901")
        resposta = self.client.get(
            reverse("apartamentos:excluir", args=[apartamento.id])
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(Apartamento.objects.filter(pk=apartamento.id).exists())
        self.assertContains(resposta, "Excluir permanentemente")
        self.assertContains(resposta, "Esta ação é irreversível")
        self.assertContains(resposta, "csrfmiddlewaretoken")

    def test_exclui_apartamento_vazio_por_post(self):
        apartamento = Apartamento.objects.create(numero="902")
        resposta = self.client.post(
            reverse("apartamentos:excluir", args=[apartamento.id]),
            follow=True,
        )

        self.assertRedirects(resposta, reverse("apartamentos:lista"))
        self.assertFalse(Apartamento.objects.filter(pk=apartamento.id).exists())
        self.assertContains(resposta, "excluído permanentemente")

    def test_bloqueia_apartamento_com_leitura_e_fatura_e_informa_quantidades(self):
        apartamento = Apartamento.objects.create(numero="903")
        leitura = Leitura.objects.create(
            apartamento=apartamento,
            mes=7,
            ano=2026,
            leitura_agua=Decimal("10"),
        )
        Fatura.objects.create(
            apartamento=apartamento,
            leitura=leitura,
            mes=7,
            ano=2026,
            consumo_agua=0,
            consumo_gas=0,
            apartamento_numero_emissao=apartamento.numero,
        )

        resposta = self.client.post(
            reverse("apartamentos:excluir", args=[apartamento.id])
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "1 leitura e 1 fatura")
        self.assertTrue(Apartamento.objects.filter(pk=apartamento.id).exists())
        self.assertTrue(Leitura.objects.filter(pk=leitura.id).exists())
        self.assertEqual(Fatura.objects.filter(apartamento=apartamento).count(), 1)

    def test_confirmacao_inexistente_retorna_404(self):
        resposta = self.client.get(
            reverse("apartamentos:excluir", args=[999999])
        )
        self.assertEqual(resposta.status_code, 404)

    def test_usuario_nao_staff_nao_pode_excluir(self):
        apartamento = Apartamento.objects.create(numero="904")
        usuario = get_user_model().objects.create_user(
            username="morador-exclusao-apartamento",
            password="senha-de-teste",
        )
        self.client.force_login(usuario)

        resposta = self.client.post(
            reverse("apartamentos:excluir", args=[apartamento.id])
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(Apartamento.objects.filter(pk=apartamento.id).exists())

    def test_service_bloqueia_diretamente_e_trata_plural(self):
        apartamento = Apartamento.objects.create(numero="905")
        for mes in (6, 7):
            Leitura.objects.create(
                apartamento=apartamento,
                mes=mes,
                ano=2026,
                leitura_agua=Decimal("10"),
            )

        with self.assertRaisesRegex(
            ExclusaoApartamentoBloqueadaError,
            "2 leituras e 0 faturas",
        ):
            excluir_apartamento(apartamento.id)

        self.assertTrue(Apartamento.objects.filter(pk=apartamento.id).exists())


class ApartamentoFormTests(TestCase):
    def test_widgets_preservam_restricoes_e_recebem_estilo_bootstrap(self):
        form = ApartamentoForm()

        self.assertEqual(form.fields["leitura_base_agua"].widget.attrs["min"], "0")
        self.assertEqual(form.fields["leitura_base_agua"].widget.attrs["step"], "0.01")
        self.assertEqual(form.fields["observacoes"].widget.attrs["rows"], 4)
        self.assertEqual(form.fields["numero"].widget.attrs["class"], "form-control")

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

    def test_formulario_de_filtros_mantem_valores_informados(self):
        form = FiltrarApartamentosForm({"numero": "10", "bloco": "A"})

        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["numero"], "10")
        self.assertEqual(form.cleaned_data["bloco"], "A")


class FiltrosApartamentoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.apartamento_101a = Apartamento.objects.create(numero="101", bloco="A")
        cls.apartamento_102a = Apartamento.objects.create(numero="102", bloco="A")
        cls.apartamento_101b = Apartamento.objects.create(numero="101", bloco="B")

    def test_servico_combina_numero_e_bloco(self):
        resultados = list(
            listar_apartamentos(numero="101", bloco="A")
        )

        self.assertEqual(resultados, [self.apartamento_101a])

    def test_filtro_de_numero_permite_correspondencia_parcial(self):
        resultados = list(listar_apartamentos(numero="02"))

        self.assertEqual(resultados, [self.apartamento_102a])

    def test_aceita_leituras_base_zero(self):
        form = ApartamentoForm(
            data={
                "numero": "101",
                "leitura_base_agua": "0",
                "leitura_base_gas": "0",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_aluguel_vazio_vira_zero_e_negativo_e_rejeitado(self):
        dados = {
            "numero": "101",
            "leitura_base_agua": "0",
            "leitura_base_gas": "0",
            "valor_aluguel": "",
        }
        form_sem_aluguel = ApartamentoForm(data=dados)
        self.assertTrue(form_sem_aluguel.is_valid(), form_sem_aluguel.errors)
        self.assertEqual(
            form_sem_aluguel.cleaned_data["valor_aluguel"],
            Decimal("0.00"),
        )

        form_negativo = ApartamentoForm(
            data={**dados, "valor_aluguel": "-0.01"}
        )
        self.assertFalse(form_negativo.is_valid())
        self.assertIn("valor_aluguel", form_negativo.errors)

    def test_rejeita_leituras_base_acima_do_limite(self):
        form = ApartamentoForm(
            data={
                "numero": "101",
                "leitura_base_agua": "1000000.00",
                "leitura_base_gas": "1000000.00",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("leitura_base_agua", form.errors)
        self.assertIn("leitura_base_gas", form.errors)

    def test_valida_a_primeira_leitura_de_cada_medidor_separadamente(self):
        apartamento = Apartamento.objects.create(
            numero="101",
            leitura_base_agua=Decimal("0.00"),
            leitura_base_gas=Decimal("0.00"),
        )
        Leitura.objects.create(
            apartamento=apartamento,
            mes=1,
            ano=2026,
            leitura_agua=None,
            leitura_gas=Decimal("5.00"),
        )
        Leitura.objects.create(
            apartamento=apartamento,
            mes=2,
            ano=2026,
            leitura_agua=Decimal("10.00"),
            leitura_gas=None,
        )

        form = ApartamentoForm(
            instance=apartamento,
            data={
                "numero": "101",
                "leitura_base_agua": "10.01",
                "leitura_base_gas": "5.01",
            },
        )

        self.assertFalse(form.is_valid())
        self.assertIn("leitura_base_agua", form.errors)
        self.assertIn("leitura_base_gas", form.errors)


class FluxoApartamentoTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="operador",
            password="senha-de-teste",
            is_staff=True,
        )
        self.client.force_login(usuario)

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

    def test_nao_edita_bases_acima_da_primeira_leitura(self):
        apartamento = cadastrar_apartamento(
            numero="202",
            leitura_base_agua=Decimal("100.00"),
            leitura_base_gas=Decimal("20.00"),
        )
        Leitura.objects.create(
            apartamento=apartamento,
            mes=1,
            ano=2026,
            leitura_agua=Decimal("110.00"),
            leitura_gas=Decimal("25.00"),
        )

        with self.assertRaisesRegex(ValueError, "água"):
            editar_apartamento(
                apartamento.id,
                numero="202",
                leitura_base_agua=Decimal("110.01"),
                leitura_base_gas=Decimal("25.00"),
            )

        with self.assertRaisesRegex(ValueError, "gás"):
            editar_apartamento(
                apartamento.id,
                numero="202",
                leitura_base_agua=Decimal("110.00"),
                leitura_base_gas=Decimal("25.01"),
            )

    def test_servico_normaliza_entradas_e_rejeita_valores_nao_finitos(self):
        apartamento = cadastrar_apartamento(
            numero=" 202 ",
            bloco=" B ",
            leitura_base_agua="100.00",
            leitura_base_gas="20.00",
        )

        self.assertEqual(apartamento.numero, "202")
        self.assertEqual(apartamento.bloco, "B")
        self.assertEqual(apartamento.leitura_base_agua, Decimal("100.00"))

        for valor in ("NaN", "Infinity", True):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                cadastrar_apartamento(
                    numero="303",
                    leitura_base_agua=valor,
                    leitura_base_gas="0",
                )

    def test_cadastro_normaliza_aluguel_e_aplica_zero_quando_ausente(self):
        com_aluguel = cadastrar_apartamento(
            numero="501",
            leitura_base_agua=0,
            leitura_base_gas=0,
            valor_aluguel="1200.5",
        )
        sem_aluguel = cadastrar_apartamento(
            numero="502",
            leitura_base_agua=0,
            leitura_base_gas=0,
        )

        self.assertEqual(com_aluguel.valor_aluguel, Decimal("1200.50"))
        self.assertEqual(sem_aluguel.valor_aluguel, Decimal("0.00"))

    @patch(
        "apartamentos.views._salvar_formulario",
        side_effect=ValueError("Falha concorrente de validação."),
    )
    def test_erro_de_dominio_no_salvamento_volta_ao_formulario(self, _salvar):
        resposta = self.client.post(
            reverse("apartamentos:novo"),
            {
                "numero": "404",
                "leitura_base_agua": "0",
                "leitura_base_gas": "0",
            },
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Falha concorrente de validação.")


class ApresentacaoApartamentoTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="operador-apresentacao",
            password="senha-de-teste",
            is_staff=True,
        )
        self.client.force_login(usuario)

    def test_lista_usa_layout_padrao_e_exibe_estado_vazio(self):
        resposta = self.client.get(reverse("apartamentos:lista"))

        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, "apartamentos/lista.html")
        self.assertTemplateUsed(resposta, "base.html")
        self.assertContains(resposta, "Nenhum apartamento cadastrado")
        self.assertContains(resposta, reverse("apartamentos:novo"))

    def test_lista_exibe_apartamento_e_link_de_detalhes(self):
        apartamento = Apartamento.objects.create(
            numero="101",
            bloco="A",
            leitura_base_agua=Decimal("10.00"),
            leitura_base_gas=Decimal("5.00"),
        )

        resposta = self.client.get(reverse("apartamentos:lista"))

        self.assertContains(resposta, "Apartamento 101")
        self.assertContains(
            resposta,
            reverse("apartamentos:detalhes", args=[apartamento.id]),
        )

    def test_lista_filtra_e_mantem_parametros_preenchidos(self):
        Apartamento.objects.create(numero="101", bloco="A")
        Apartamento.objects.create(numero="202", bloco="B")

        resposta = self.client.get(
            reverse("apartamentos:lista"),
            {"numero": "101", "bloco": "A"},
        )

        self.assertContains(resposta, "Apartamento 101")
        self.assertNotContains(resposta, "Apartamento 202")
        self.assertContains(resposta, 'value="101"')
        self.assertContains(resposta, 'value="A"')
        self.assertContains(resposta, "Limpar filtros")

    def test_formulario_usa_componente_de_campo_e_mantem_cancelamento(self):
        resposta = self.client.get(reverse("apartamentos:novo"))

        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, "apartamentos/formulario.html")
        self.assertTemplateUsed(resposta, "components/form_field.html")
        self.assertContains(resposta, "Salvar apartamento")
        self.assertContains(resposta, reverse("apartamentos:lista"))

    @patch("apartamentos.views.consultar_detalhes_apartamento")
    def test_detalhes_exibe_secoes_e_estados_vazios(self, consultar):
        registros_vazios = SimpleNamespace(all=lambda: [])
        consultar.return_value = SimpleNamespace(
            id=1,
            numero="101",
            bloco="A",
            leitura_base_agua=Decimal("10.00"),
            leitura_base_gas=Decimal("5.00"),
            observacoes="",
            leituras=registros_vazios,
            faturas=registros_vazios,
        )

        resposta = self.client.get(
            reverse("apartamentos:detalhes", args=[1]),
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, "apartamentos/detalhes.html")
        self.assertContains(resposta, "Histórico de leituras")
        self.assertContains(resposta, "Histórico de faturas")
        self.assertContains(resposta, "Nenhuma leitura cadastrada")
        self.assertContains(resposta, "Nenhuma fatura cadastrada")
        self.assertContains(resposta, reverse("leituras:nova", args=[1]))


class ProtecaoApartamentoTest(TestCase):
    def setUp(self):
        self.apartamento = Apartamento.objects.create(numero="101")

    def test_nao_exclui_apartamento_com_leitura(self):
        leitura = Leitura.objects.create(
            apartamento=self.apartamento,
            mes=7,
            ano=2026,
            leitura_agua=Decimal("1.00"),
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


class IntegridadeApartamentoTests(TestCase):
    def test_banco_impede_numero_duplicado_sem_bloco(self):
        Apartamento.objects.create(numero="101", bloco=None)

        with self.assertRaises(IntegrityError), transaction.atomic():
            Apartamento.objects.create(numero="101", bloco=None)

    def test_banco_impede_duplicidade_independente_de_maiusculas(self):
        Apartamento.objects.create(numero="101", bloco="A")

        with self.assertRaises(IntegrityError), transaction.atomic():
            Apartamento.objects.create(numero="101", bloco="a")

    def test_banco_rejeita_numero_e_textos_nao_normalizados(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Apartamento.objects.create(numero=" 101 ")

        with self.assertRaises(IntegrityError), transaction.atomic():
            Apartamento.objects.create(numero="101", bloco=" ")

    def test_service_normaliza_textos_e_rejeita_duplicidade(self):
        apartamento = cadastrar_apartamento(
            numero=" 101 ",
            bloco=" A ",
            observacoes=" Medidor externo ",
            leitura_base_agua=0,
            leitura_base_gas=0,
        )

        self.assertEqual(apartamento.numero, "101")
        self.assertEqual(apartamento.bloco, "A")
        self.assertEqual(apartamento.observacoes, "Medidor externo")

        with self.assertRaisesRegex(ValueError, "Já existe"):
            cadastrar_apartamento(
                numero="101",
                bloco="a",
                leitura_base_agua=0,
                leitura_base_gas=0,
            )

    def test_banco_rejeita_aluguel_negativo(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Apartamento.objects.create(
                numero="999",
                valor_aluguel=Decimal("-0.01"),
            )


class SegurancaViewsApartamentoTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="operador-seguranca",
            password="senha-de-teste",
            is_staff=True,
        )

    def test_todas_as_telas_operacionais_exigem_autenticacao(self):
        urls = [
            reverse("apartamentos:lista"),
            reverse("apartamentos:novo"),
            reverse("apartamentos:editar", args=[999]),
            reverse("apartamentos:detalhes", args=[999]),
            reverse("leituras:nova", args=[999]),
            reverse("faturas:lista"),
            reverse("faturas:gerar"),
            reverse("faturas:fechamento_mensal"),
            reverse("faturas:valor_aluguel_leitura"),
            reverse("faturas:detalhes", args=[999]),
            reverse("faturas:alterar_valores", args=[999]),
            reverse("faturas:baixar_pdf", args=[999]),
        ]

        for url in urls:
            with self.subTest(url=url):
                resposta = self.client.get(url)
                self.assertRedirects(
                    resposta,
                    f"/admin/login/?next={url}",
                )

    def test_usuario_sem_perfil_de_equipe_nao_acessa_dados(self):
        usuario_comum = get_user_model().objects.create_user(
            username="usuario-comum",
            password="senha-de-teste",
        )
        self.client.force_login(usuario_comum)

        resposta = self.client.get(reverse("faturas:lista"))

        self.assertRedirects(
            resposta,
            f"/admin/login/?next={reverse('faturas:lista')}",
        )

    def test_next_perigoso_nao_e_renderizado(self):
        self.client.force_login(self.usuario)
        payload = "javascript:alert(document.domain)"

        resposta = self.client.get(
            reverse("apartamentos:novo"),
            {"next": payload},
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, payload)
        self.assertContains(resposta, reverse("apartamentos:lista"))

    def test_next_interno_continua_funcionando(self):
        self.client.force_login(self.usuario)
        destino = reverse("faturas:gerar")

        resposta = self.client.get(
            reverse("apartamentos:novo"),
            {"next": destino},
        )

        self.assertContains(resposta, f'href="{destino}"')

    def test_dados_operacionais_nao_sao_armazenados_em_cache(self):
        self.client.force_login(self.usuario)
        apartamento = Apartamento.objects.create(numero="303")
        fatura = Fatura.objects.create(
            apartamento=apartamento,
            mes=7,
            ano=2026,
            consumo_agua=0,
            consumo_gas=0,
            apartamento_numero_emissao=apartamento.numero,
        )
        urls = [
            reverse("apartamentos:lista"),
            reverse("apartamentos:novo"),
            reverse("apartamentos:editar", args=[apartamento.id]),
            reverse("apartamentos:detalhes", args=[apartamento.id]),
            reverse("leituras:nova", args=[apartamento.id]),
            reverse("faturas:lista"),
            reverse("faturas:gerar"),
            reverse("faturas:detalhes", args=[fatura.id]),
            reverse("faturas:baixar_pdf", args=[fatura.id]),
        ]

        for url in urls:
            with self.subTest(url=url):
                resposta = self.client.get(url)
                self.assertEqual(resposta.status_code, 200)
                self.assertIn("no-store", resposta["Cache-Control"])
                self.assertIn("private", resposta["Cache-Control"])
                politica = resposta["Content-Security-Policy"]
                self.assertIn("default-src 'self'", politica)
                self.assertIn("object-src 'none'", politica)

    def test_endpoints_rejeitam_metodos_http_inesperados(self):
        self.client.force_login(self.usuario)

        respostas = [
            self.client.put(reverse("apartamentos:novo")),
            self.client.delete(reverse("faturas:gerar")),
            self.client.post(reverse("apartamentos:lista")),
        ]

        for resposta in respostas:
            with self.subTest(url=resposta.request["PATH_INFO"]):
                self.assertEqual(resposta.status_code, 405)
