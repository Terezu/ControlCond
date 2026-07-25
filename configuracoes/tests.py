from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib import admin
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .forms import ConfiguracaoCondominioForm
from .admin import ConfiguracaoCondominioAdmin
from .models import (
    CHAVE_CONFIGURACAO,
    ConfiguracaoCondominio,
    FaixaTarifaAgua,
)
from .services import (
    atualizar_configuracao,
    obter_configuracao,
    obter_configuracoes,
    obter_faixas_agua_ativas,
)


class ConfiguracaoCondominioModelTests(TestCase):
    def test_banco_garante_registro_unico(self):
        configuracao = obter_configuracao()

        with self.assertRaises(IntegrityError), transaction.atomic():
            ConfiguracaoCondominio.objects.create(
                chave=CHAVE_CONFIGURACAO,
            )

        with self.assertRaises(IntegrityError), transaction.atomic():
            ConfiguracaoCondominio.objects.create(chave=2)

        self.assertEqual(ConfiguracaoCondominio.objects.count(), 1)
        self.assertEqual(configuracao.chave, CHAVE_CONFIGURACAO)

    def test_banco_rejeita_valor_de_gas_negativo(self):
        configuracao = obter_configuracao()
        configuracao.valor_m3_gas = Decimal("-0.01")

        with self.assertRaises(IntegrityError), transaction.atomic():
            configuracao.save(update_fields=["valor_m3_gas"])


class ConfiguracaoCondominioServiceTests(TestCase):
    def test_alias_plural_retorna_singleton_com_defaults_seguros(self):
        ConfiguracaoCondominio.objects.all().delete()
        configuracao = obter_configuracoes()
        self.assertEqual(configuracao.nome, "ControlCond")
        self.assertEqual(configuracao.moeda, "BRL")
        self.assertEqual(configuracao.valor_m3_gas, Decimal("21.02"))

    def test_consulta_reutiliza_o_mesmo_registro(self):
        primeira = obter_configuracao()
        segunda = obter_configuracao()

        self.assertEqual(primeira.pk, segunda.pk)
        self.assertEqual(ConfiguracaoCondominio.objects.count(), 1)

    def test_obter_configuracao_recria_registro_ausente(self):
        ConfiguracaoCondominio.objects.all().delete()

        configuracao = obter_configuracao()

        self.assertEqual(configuracao.chave, CHAVE_CONFIGURACAO)
        self.assertEqual(configuracao.valor_m3_gas, Decimal("21.02"))
        self.assertEqual(ConfiguracaoCondominio.objects.count(), 1)

    def test_atualizacao_normaliza_e_persiste_dados(self):
        configuracao = atualizar_configuracao(
            {
                "nome": " Condomínio ControlCond ",
                "cnpj": "04252011000110",
                "cep": "80000000",
                "estado": "pr",
                "valor_m3_gas": Decimal("22.50"),
            }
        )

        self.assertEqual(configuracao.nome, "Condomínio ControlCond")
        self.assertEqual(configuracao.cnpj, "04.252.011/0001-10")
        self.assertEqual(configuracao.cep, "80000-000")
        self.assertEqual(configuracao.estado, "PR")
        self.assertEqual(configuracao.valor_m3_gas, Decimal("22.50"))

    def test_migracao_preserva_tarifa_historica_da_agua(self):
        faixas = obter_faixas_agua_ativas()
        self.assertEqual(len(faixas), 6)
        self.assertEqual(faixas[0].consumo_inicial, 0)
        self.assertEqual(faixas[0].consumo_final, 5)
        self.assertEqual(faixas[0].valor, Decimal("101.91"))
        self.assertIsNone(faixas[-1].consumo_final)
        self.assertEqual(faixas[-1].valor, Decimal("30.12"))


class ConfiguracaoCondominioFormTests(TestCase):
    def test_formulario_normaliza_cnpj_e_cep(self):
        form = ConfiguracaoCondominioForm(
            data={
                "nome": "ControlCond",
                "cnpj": "04252011000110",
                "cep": "80000000",
                "valor_m3_gas": "21.02",
                "cor_primaria": "#1F4E5F",
                "cor_secundaria": "#64748B",
                "cor_destaque": "#E8F1F4",
                "moeda": "BRL",
                "dias_vencimento_padrao": "10",
                "percentual_multa_padrao": "0",
                "percentual_juros_padrao": "0",
                "valor_bonificacao_padrao": "0",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["cnpj"], "04.252.011/0001-10")
        self.assertEqual(form.cleaned_data["cep"], "80000-000")

    def test_formulario_rejeita_cnpj_email_e_valor_invalidos(self):
        form = ConfiguracaoCondominioForm(
            data={
                "nome": "ControlCond",
                "cnpj": "11.111.111/1111-11",
                "email": "email-invalido",
                "valor_m3_gas": "-1",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("cnpj", form.errors)
        self.assertIn("email", form.errors)
        self.assertIn("valor_m3_gas", form.errors)

    def test_formulario_rejeita_logo_maior_que_cinco_mb(self):
        logo = SimpleUploadedFile(
            "logo.png",
            b"x" * (5 * 1024 * 1024 + 1),
            content_type="image/png",
        )
        form = ConfiguracaoCondominioForm(
            data={
                "nome": "ControlCond",
                "valor_m3_gas": "21.02",
                "cor_primaria": "#1F4E5F",
                "cor_secundaria": "#64748B",
                "cor_destaque": "#E8F1F4",
                "moeda": "BRL",
                "dias_vencimento_padrao": "10",
                "percentual_multa_padrao": "0",
                "percentual_juros_padrao": "0",
                "valor_bonificacao_padrao": "0",
            },
            files={"logo": logo},
        )

        self.assertFalse(form.is_valid())
        self.assertIn("logo", form.errors)


class ConfiguracaoCondominioViewTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="operador-configuracoes",
            password="senha-de-teste",
            is_staff=True,
        )

    def test_telas_exigem_usuario_staff(self):
        for url in (
            reverse("configuracoes:detalhes"),
            reverse("configuracoes:editar"),
        ):
            with self.subTest(url=url):
                resposta = self.client.get(url)
                self.assertRedirects(
                    resposta,
                    f"/admin/login/?next={url}",
                )

    def test_detalhes_e_formulario_seguem_layout_padrao(self):
        self.client.force_login(self.usuario)

        detalhes = self.client.get(reverse("configuracoes:detalhes"))
        formulario = self.client.get(reverse("configuracoes:editar"))

        self.assertEqual(detalhes.status_code, 200)
        self.assertTemplateUsed(detalhes, "configuracoes/detalhes.html")
        self.assertContains(detalhes, "Editar configurações")
        self.assertTemplateUsed(formulario, "components/form_field.html")
        self.assertContains(formulario, "Salvar configurações")
        self.assertContains(
            formulario,
            'enctype="multipart/form-data"',
        )

    def test_edicao_atualiza_sem_criar_novo_registro(self):
        self.client.force_login(self.usuario)

        resposta = self.client.post(
            reverse("configuracoes:editar"),
            {
                "nome": "Residencial Teste",
                "valor_m3_gas": "23.40",
                "cor_primaria": "#1F4E5F",
                "cor_secundaria": "#64748B",
                "cor_destaque": "#E8F1F4",
                "moeda": "BRL",
                "dias_vencimento_padrao": "10",
                "percentual_multa_padrao": "0",
                "percentual_juros_padrao": "0",
                "valor_bonificacao_padrao": "0",
            },
        )

        self.assertRedirects(
            resposta,
            reverse("configuracoes:detalhes"),
        )
        configuracao = ConfiguracaoCondominio.objects.get()
        self.assertEqual(configuracao.nome, "Residencial Teste")
        self.assertEqual(configuracao.valor_m3_gas, Decimal("23.40"))
        self.assertEqual(ConfiguracaoCondominio.objects.count(), 1)

    def test_cabecalho_usa_nome_configurado_e_fallback(self):
        self.client.force_login(self.usuario)

        resposta_padrao = self.client.get(
            reverse("configuracoes:detalhes")
        )
        self.assertContains(resposta_padrao, "ControlCond")

        atualizar_configuracao(
            {
                "nome": "Residencial das Araucárias",
                "valor_m3_gas": Decimal("21.02"),
            }
        )
        resposta_configurada = self.client.get(
            reverse("configuracoes:detalhes")
        )

        self.assertContains(
            resposta_configurada,
            "Residencial das Araucárias",
        )

    def test_views_rejeitam_metodos_inesperados_e_nao_usam_cache(self):
        self.client.force_login(self.usuario)

        detalhes = self.client.get(reverse("configuracoes:detalhes"))
        resposta_post = self.client.post(reverse("configuracoes:detalhes"))
        resposta_put = self.client.put(reverse("configuracoes:editar"))

        self.assertIn("no-store", detalhes["Cache-Control"])
        self.assertEqual(resposta_post.status_code, 405)
        self.assertEqual(resposta_put.status_code, 405)


class ConfiguracaoCondominioAdminTests(TestCase):
    def test_admin_impede_segundo_registro(self):
        model_admin = ConfiguracaoCondominioAdmin(
            ConfiguracaoCondominio,
            admin.site,
        )
        obter_configuracao()
        self.assertFalse(model_admin.has_add_permission(None))
        self.assertFalse(model_admin.has_delete_permission(None))

    def test_faixas_estao_registradas_no_admin(self):
        self.assertIn(FaixaTarifaAgua, admin.site._registry)
