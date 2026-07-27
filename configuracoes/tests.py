from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from condominios.models import Condominio, VinculoUsuarioCondominio

from .forms import ConfiguracaoCondominioForm
from .admin import ConfiguracaoCondominioAdmin
from .models import (
    CHAVE_CONFIGURACAO,
    COR_DESTAQUE_PADRAO,
    COR_PRIMARIA_PADRAO,
    COR_SECUNDARIA_PADRAO,
    ConfiguracaoCondominio,
    FaixaTarifaAgua,
    TabelaTarifariaAgua,
    TarifaGas,
)
from .services import (
    atualizar_configuracao as atualizar_configuracao_por_condominio,
    obter_configuracao as obter_configuracao_por_condominio,
    obter_configuracoes as obter_configuracoes_por_condominio,
    obter_faixas_agua_ativas as obter_faixas_agua_ativas_por_condominio,
    obter_tabela_agua_vigente as obter_tabela_agua_vigente_por_condominio,
    obter_tarifa_gas_vigente as obter_tarifa_gas_vigente_por_condominio,
    validar_tabela_agua,
)


def obter_configuracao():
    return obter_configuracao_por_condominio(Condominio.objects.get())


def obter_configuracoes():
    return obter_configuracoes_por_condominio(Condominio.objects.get())


def atualizar_configuracao(dados):
    return atualizar_configuracao_por_condominio(
        Condominio.objects.get(), dados
    )


def obter_faixas_agua_ativas(*args):
    return obter_faixas_agua_ativas_por_condominio(
        Condominio.objects.get(), *args
    )


def obter_tabela_agua_vigente(mes, ano):
    return obter_tabela_agua_vigente_por_condominio(
        Condominio.objects.get(), mes, ano
    )


def obter_tarifa_gas_vigente(mes, ano):
    return obter_tarifa_gas_vigente_por_condominio(
        Condominio.objects.get(), mes, ano
    )


class TarifasConsumoTests(TestCase):
    def setUp(self):
        self.tabela_inicial = TabelaTarifariaAgua.objects.get()
        self.tarifa_inicial = TarifaGas.objects.get()

    def test_seleciona_regras_pelo_primeiro_dia_da_competencia(self):
        self.assertEqual(
            obter_tabela_agua_vigente(1, 2026), self.tabela_inicial
        )
        self.assertEqual(
            obter_tarifa_gas_vigente(1, 2026), self.tarifa_inicial
        )

    def test_rejeita_vigencias_sobrepostas(self):
        tabela = TabelaTarifariaAgua(
            nome="Sobreposta", data_inicio_vigencia=date(2026, 1, 1)
        )
        with self.assertRaises(ValidationError):
            tabela.full_clean()
        tarifa = TarifaGas(
            nome="Sobreposta", valor_por_m3=Decimal("10"),
            data_inicio_vigencia=date(2026, 1, 1),
        )
        with self.assertRaises(ValidationError):
            tarifa.full_clean()

    def test_rejeita_gas_negativo_e_fim_antes_do_inicio(self):
        tarifa = TarifaGas(
            nome="Inválida", valor_por_m3=Decimal("-1"),
            data_inicio_vigencia=date(2026, 2, 1),
            data_fim_vigencia=date(2026, 1, 31),
        )
        with self.assertRaises(ValidationError):
            tarifa.full_clean()

    def test_detecta_lacuna_e_sobreposicao_de_faixas(self):
        segunda = self.tabela_inicial.faixas.order_by("ordem")[1]
        segunda.consumo_inicial += 1
        segunda.save(update_fields=["consumo_inicial"])
        with self.assertRaisesRegex(ValueError, "lacunas"):
            validar_tabela_agua(self.tabela_inicial)

    def test_faixa_rejeita_intervalo_invertido(self):
        faixa = FaixaTarifaAgua(
            tabela=self.tabela_inicial, consumo_inicial=10,
            consumo_final=5, valor=Decimal("1"), ordem=99,
        )
        with self.assertRaises(ValidationError):
            faixa.full_clean()

    def test_telas_exigem_staff_e_exibem_navegacao(self):
        usuario = get_user_model().objects.create_user(
            username="comum", password="senha"
        )
        self.client.force_login(usuario)
        resposta = self.client.get(reverse("configuracoes:tabelas_agua"))
        self.assertEqual(resposta.status_code, 302)
        usuario.is_staff = True
        usuario.save(update_fields=["is_staff"])
        VinculoUsuarioCondominio.objects.get_or_create(
            usuario=usuario,
            condominio=Condominio.objects.get(),
        )
        resposta = self.client.get(reverse("configuracoes:detalhes"))
        self.assertContains(resposta, "Configurar tabela de água")
        self.assertContains(resposta, "Configurar tarifa de gás")

    def test_detalhes_exibe_faixas_da_tabela_vigente(self):
        usuario = get_user_model().objects.create_user(
            username="staff-faixas", password="senha", is_staff=True
        )
        VinculoUsuarioCondominio.objects.get_or_create(
            usuario=usuario,
            condominio=Condominio.objects.get(),
        )
        self.client.force_login(usuario)

        resposta = self.client.get(reverse("configuracoes:detalhes"))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, self.tabela_inicial.nome)
        self.assertContains(resposta, "R$ 101,91")
        self.assertNotContains(resposta, "Nenhuma tabela de água vigente")

    def test_nova_vigencia_de_agua_altera_so_competencias_futuras(self):
        from calculos.services import calcular_valor_agua
        valor_antigo = calcular_valor_agua(5, 12, 2026)
        self.tabela_inicial.data_fim_vigencia = date(2026, 12, 31)
        self.tabela_inicial.save(update_fields=["data_fim_vigencia"])
        nova = TabelaTarifariaAgua.objects.create(
            nome="Tabela 2027", data_inicio_vigencia=date(2027, 1, 1)
        )
        FaixaTarifaAgua.objects.create(
            tabela=nova, consumo_inicial=0, consumo_final=None,
            valor=Decimal("150.00"), ordem=1,
        )
        self.assertEqual(valor_antigo, Decimal("101.91"))
        self.assertEqual(
            calcular_valor_agua(5, 1, 2027), Decimal("150.00")
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

    def test_banco_protege_limites_da_politica_financeira(self):
        casos = (
            ("dia_vencimento_padrao", 32),
            ("dias_tolerancia_pagamento", 366),
            ("percentual_bonificacao_padrao", Decimal("100.001")),
            ("dias_antecedencia_bonificacao", 366),
        )
        for campo, valor in casos:
            with self.subTest(campo=campo):
                configuracao = obter_configuracao()
                setattr(configuracao, campo, valor)
                with self.assertRaises(IntegrityError), transaction.atomic():
                    configuracao.save(update_fields=[campo])
                configuracao.refresh_from_db()


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

    def test_politica_financeira_e_isolada_por_condominio(self):
        condominio_inicial = Condominio.objects.get()
        outro_condominio = Condominio.objects.create(nome="Condomínio B")

        configuracao_inicial = atualizar_configuracao_por_condominio(
            condominio_inicial,
            {
                "dia_vencimento_padrao": 12,
                "dias_tolerancia_pagamento": 2,
                "percentual_multa_padrao": Decimal("2.000"),
                "percentual_juros_padrao": Decimal("0.033"),
                "tipo_juros": "diario",
                "percentual_bonificacao_padrao": Decimal("5.000"),
                "dias_antecedencia_bonificacao": 4,
            },
        )
        configuracao_b = atualizar_configuracao_por_condominio(
            outro_condominio,
            {
                "dia_vencimento_padrao": 20,
                "dias_tolerancia_pagamento": 7,
                "percentual_multa_padrao": Decimal("1.500"),
                "percentual_juros_padrao": Decimal("1.000"),
                "tipo_juros": "mensal",
                "percentual_bonificacao_padrao": Decimal("3.000"),
                "dias_antecedencia_bonificacao": 10,
            },
        )

        self.assertEqual(configuracao_inicial.dia_vencimento_padrao, 12)
        self.assertEqual(configuracao_inicial.tipo_juros, "diario")
        self.assertEqual(configuracao_b.dia_vencimento_padrao, 20)
        self.assertEqual(configuracao_b.tipo_juros, "mensal")
        self.assertNotEqual(
            configuracao_inicial.percentual_bonificacao_padrao,
            configuracao_b.percentual_bonificacao_padrao,
        )

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
                "dia_vencimento_padrao": "10",
                "dias_tolerancia_pagamento": "0",
                "dias_vencimento_padrao": "10",
                "percentual_multa_padrao": "0",
                "percentual_juros_padrao": "0",
                "tipo_juros": "mensal",
                "percentual_bonificacao_padrao": "0",
                "dias_antecedencia_bonificacao": "0",
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

    def test_formulario_rejeita_politica_financeira_invalida(self):
        form = ConfiguracaoCondominioForm(
            data={
                "nome": "ControlCond",
                "valor_m3_gas": "21.02",
                "cor_primaria": "#1F4E5F",
                "cor_secundaria": "#64748B",
                "cor_destaque": "#E8F1F4",
                "moeda": "BRL",
                "dia_vencimento_padrao": "32",
                "dias_tolerancia_pagamento": "366",
                "dias_vencimento_padrao": "10",
                "percentual_multa_padrao": "2",
                "percentual_juros_padrao": "1",
                "tipo_juros": "semanal",
                "percentual_bonificacao_padrao": "100.001",
                "dias_antecedencia_bonificacao": "366",
                "valor_bonificacao_padrao": "0",
            }
        )

        self.assertFalse(form.is_valid())
        for campo in (
            "dia_vencimento_padrao",
            "dias_tolerancia_pagamento",
            "tipo_juros",
            "percentual_bonificacao_padrao",
            "dias_antecedencia_bonificacao",
        ):
            with self.subTest(campo=campo):
                self.assertIn(campo, form.errors)

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
                "dia_vencimento_padrao": "10",
                "dias_tolerancia_pagamento": "0",
                "dias_vencimento_padrao": "10",
                "percentual_multa_padrao": "0",
                "percentual_juros_padrao": "0",
                "tipo_juros": "mensal",
                "percentual_bonificacao_padrao": "0",
                "dias_antecedencia_bonificacao": "0",
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
        VinculoUsuarioCondominio.objects.get_or_create(
            usuario=self.usuario,
            condominio=Condominio.objects.get(),
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
                "cor_primaria": "#7B2CBF",
                "cor_secundaria": "#4361EE",
                "cor_destaque": "#F3E8FF",
                "moeda": "BRL",
                "dia_vencimento_padrao": "15",
                "dias_tolerancia_pagamento": "3",
                "dias_vencimento_padrao": "10",
                "percentual_multa_padrao": "2.5",
                "percentual_juros_padrao": "1.25",
                "tipo_juros": "diario",
                "percentual_bonificacao_padrao": "4.5",
                "dias_antecedencia_bonificacao": "5",
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
        self.assertEqual(configuracao.cor_primaria, "#7B2CBF")
        self.assertEqual(configuracao.cor_secundaria, "#4361EE")
        self.assertEqual(configuracao.cor_destaque, "#F3E8FF")
        self.assertEqual(configuracao.dia_vencimento_padrao, 15)
        self.assertEqual(configuracao.dias_tolerancia_pagamento, 3)
        self.assertEqual(
            configuracao.percentual_multa_padrao,
            Decimal("2.500"),
        )
        self.assertEqual(
            configuracao.percentual_juros_padrao,
            Decimal("1.250"),
        )
        self.assertEqual(configuracao.tipo_juros, "diario")
        self.assertEqual(
            configuracao.percentual_bonificacao_padrao,
            Decimal("4.500"),
        )
        self.assertEqual(configuracao.dias_antecedencia_bonificacao, 5)
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

    def test_tema_configurado_persiste_e_chega_ao_template_base(self):
        self.client.force_login(self.usuario)
        configuracao = atualizar_configuracao(
            {
                "cor_primaria": "#7B2CBF",
                "cor_secundaria": "#4361EE",
                "cor_destaque": "#F3E8FF",
            }
        )

        self.assertEqual(configuracao.cor_primaria, "#7B2CBF")
        self.assertEqual(configuracao.cor_secundaria, "#4361EE")
        self.assertEqual(configuracao.cor_destaque, "#F3E8FF")

        for url in (
            reverse("dashboard:inicio"),
            reverse("apartamentos:lista"),
            reverse("leituras:lista"),
            reverse("faturas:lista"),
            reverse("configuracoes:detalhes"),
            reverse("configuracoes:editar"),
        ):
            with self.subTest(url=url):
                resposta = self.client.get(url)
                self.assertContains(
                    resposta,
                    "--controlcond-primary: #7B2CBF",
                )
                self.assertContains(
                    resposta,
                    "--controlcond-secondary: #4361EE",
                )
                self.assertContains(
                    resposta,
                    "--controlcond-highlight: #F3E8FF",
                )
                conteudo = resposta.content.decode()
                self.assertLess(
                    conteudo.index("css/style.css"),
                    conteudo.index('id="controlcond-theme"'),
                )
                self.assertIn(
                    "background-color: var(--controlcond-primary) !important",
                    conteudo,
                )

        self.client.logout()
        self.client.force_login(self.usuario)
        resposta_apos_novo_login = self.client.get(
            reverse("dashboard:inicio")
        )
        self.assertContains(
            resposta_apos_novo_login,
            "--controlcond-primary: #7B2CBF",
        )

    def test_tema_acompanha_troca_de_condominio(self):
        outro_condominio = Condominio.objects.create(nome="Edifício Azul")
        VinculoUsuarioCondominio.objects.create(
            usuario=self.usuario,
            condominio=outro_condominio,
        )
        atualizar_configuracao_por_condominio(
            outro_condominio,
            {
                "cor_primaria": "#0057B8",
                "cor_secundaria": "#334155",
                "cor_destaque": "#DBEAFE",
            },
        )
        self.client.force_login(self.usuario)

        self.client.post(
            reverse("condominios:selecionar"),
            {"condominio": outro_condominio.pk},
        )
        resposta_outro = self.client.get(reverse("dashboard:inicio"))
        self.assertContains(
            resposta_outro,
            "--controlcond-primary: #0057B8",
        )

        condominio_inicial = Condominio.objects.exclude(
            pk=outro_condominio.pk
        ).get()
        self.client.post(
            reverse("condominios:selecionar"),
            {"condominio": condominio_inicial.pk},
        )
        resposta_inicial = self.client.get(reverse("dashboard:inicio"))
        self.assertContains(
            resposta_inicial,
            "--controlcond-primary: #1F4E5F",
        )

    def test_formulario_oferece_restauracao_das_tres_cores_padrao(self):
        self.client.force_login(self.usuario)

        resposta = self.client.get(reverse("configuracoes:editar"))

        self.assertContains(resposta, "Restaurar cores padrão")
        self.assertContains(
            resposta,
            f'data-cor-primaria="{COR_PRIMARIA_PADRAO}"',
        )
        self.assertContains(
            resposta,
            f'data-cor-secundaria="{COR_SECUNDARIA_PADRAO}"',
        )
        self.assertContains(
            resposta,
            f'data-cor-destaque="{COR_DESTAQUE_PADRAO}"',
        )
        self.assertEqual(
            ConfiguracaoCondominio._meta.get_field("cor_primaria").default,
            COR_PRIMARIA_PADRAO,
        )
        self.assertEqual(
            ConfiguracaoCondominio._meta.get_field("cor_secundaria").default,
            COR_SECUNDARIA_PADRAO,
        )
        self.assertEqual(
            ConfiguracaoCondominio._meta.get_field("cor_destaque").default,
            COR_DESTAQUE_PADRAO,
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
