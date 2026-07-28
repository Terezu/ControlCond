from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apartamentos.models import Apartamento
from condominios.models import Condominio, VinculoUsuarioCondominio
from faturas.models import Fatura
from leituras.models import Leitura

from .services import obter_resumo_dashboard


class DashboardAccessTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="operador-dashboard",
            password="senha-de-teste",
            is_staff=True,
        )
        condominio = Condominio.objects.order_by("id").first()
        if condominio is None:
            condominio = Condominio.objects.create(nome="Condomínio Teste")
        VinculoUsuarioCondominio.objects.update_or_create(
            usuario=self.usuario,
            condominio=condominio,
            defaults={
                "papel": VinculoUsuarioCondominio.Papel.ADMINISTRADOR,
                "ativo": True,
            },
        )

    def test_usuario_anonimo_e_redirecionado_para_login(self):
        url = reverse("dashboard:inicio")
        resposta = self.client.get(url)

        self.assertRedirects(
            resposta,
            f"{reverse('login')}?next={url}",
        )

    def test_usuario_staff_pode_acessar_dashboard(self):
        self.client.force_login(self.usuario)

        resposta = self.client.get(reverse("dashboard:inicio"))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Fechamento Mensal")
        self.assertContains(
            resposta,
            reverse("faturas:fechamento_mensal"),
        )

    def test_dashboard_rejeita_metodos_nao_seguros(self):
        self.client.force_login(self.usuario)

        resposta = self.client.post(reverse("dashboard:inicio"))

        self.assertEqual(resposta.status_code, 405)

    def test_usuario_sem_permissao_nao_visualiza_dados_financeiros(self):
        usuario = get_user_model().objects.create_user(
            username="morador-dashboard",
            password="senha-de-teste",
        )
        self.client.force_login(usuario)
        url = reverse("dashboard:inicio")

        resposta = self.client.get(url)

        self.assertRedirects(
            resposta,
            f"{reverse('condominios:selecionar')}?next=%2F",
        )

    @patch("dashboard.forms.timezone.localdate")
    def test_competencia_atual_e_padrao_quando_parametros_ausentes(
        self,
        localdate,
    ):
        localdate.return_value = date(2026, 7, 24)
        self.client.force_login(self.usuario)

        resposta = self.client.get(reverse("dashboard:inicio"))

        self.assertEqual(resposta.context["resumo"].mes, 7)
        self.assertEqual(resposta.context["resumo"].ano, 2026)
        self.assertContains(resposta, "Julho de 2026")

    def test_competencia_valida_vem_do_get(self):
        self.client.force_login(self.usuario)

        resposta = self.client.get(
            reverse("dashboard:inicio"),
            {"mes": "2", "ano": "2025"},
        )

        self.assertEqual(resposta.context["resumo"].mes, 2)
        self.assertEqual(resposta.context["resumo"].ano, 2025)
        self.assertContains(resposta, "Fevereiro de 2025")

    def test_competencia_selecionada_permanece_na_sessao(self):
        self.client.force_login(self.usuario)
        url = reverse("dashboard:inicio")

        self.client.get(url, {"mes": "2", "ano": "2025"})
        resposta = self.client.get(url)

        self.assertEqual(resposta.context["resumo"].mes, 2)
        self.assertEqual(resposta.context["resumo"].ano, 2025)
        self.assertContains(resposta, "Fevereiro de 2025")

    def test_nova_competencia_substitui_a_anterior_na_sessao(self):
        self.client.force_login(self.usuario)
        url = reverse("dashboard:inicio")

        self.client.get(url, {"mes": "2", "ano": "2025"})
        self.client.get(url, {"mes": "9", "ano": "2026"})
        resposta = self.client.get(url)

        self.assertEqual(resposta.context["resumo"].mes, 9)
        self.assertEqual(resposta.context["resumo"].ano, 2026)
        self.assertContains(resposta, "Setembro de 2026")

    def test_parametros_invalidos_nao_apagam_competencia_salva(self):
        self.client.force_login(self.usuario)
        url = reverse("dashboard:inicio")
        self.client.get(url, {"mes": "2", "ano": "2025"})

        resposta = self.client.get(
            url,
            {"mes": "99", "ano": "-1"},
        )

        self.assertFalse(resposta.context["form_competencia"].is_valid())
        self.assertEqual(resposta.context["resumo"].mes, 2)
        self.assertEqual(resposta.context["resumo"].ano, 2025)

    @patch("dashboard.forms.timezone.localdate")
    def test_parametros_invalidos_exibem_erros_e_usam_padrao(
        self,
        localdate,
    ):
        localdate.return_value = date(2026, 7, 24)
        self.client.force_login(self.usuario)

        resposta = self.client.get(
            reverse("dashboard:inicio"),
            {"mes": "99", "ano": "-1"},
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(resposta.context["form_competencia"].is_valid())
        self.assertEqual(resposta.context["resumo"].mes, 7)
        self.assertContains(resposta, "Faça uma escolha válida")
        self.assertContains(
            resposta,
            "Certifique-se que este valor seja maior ou igual a 2000",
        )


class DashboardResumoTests(TestCase):
    def criar_apartamento(self, numero, *, com_leitura=False):
        apartamento = Apartamento.objects.create(numero=numero)
        if com_leitura:
            Leitura.objects.create(
                apartamento=apartamento,
                mes=7,
                ano=2026,
                leitura_agua=Decimal("1.00"),
                leitura_gas=Decimal("1.00"),
            )
        return apartamento

    def criar_fatura(self, apartamento, status, valor):
        return Fatura.objects.create(
            apartamento=apartamento,
            mes=7,
            ano=2026,
            consumo_agua=0,
            consumo_gas=0,
            valor_aluguel=valor,
            valor_total=valor,
            status=status,
            apartamento_numero_emissao=apartamento.numero,
        )

    def test_estado_vazio_retorna_zeros_e_decimais(self):
        resumo = obter_resumo_dashboard(Condominio.objects.get(), 7, 2026)

        self.assertEqual(resumo.total_apartamentos, 0)
        self.assertEqual(resumo.faturas_vencidas, 0)
        self.assertEqual(resumo.receitas_previstas, Decimal("0.00"))
        self.assertEqual(resumo.receitas_recebidas, Decimal("0.00"))
        self.assertEqual(resumo.receitas_pendentes, Decimal("0.00"))
        self.assertEqual(resumo.receitas_vencidas, Decimal("0.00"))
        self.assertEqual(
            resumo.total_bonificacoes_concedidas,
            Decimal("0.00"),
        )
        self.assertEqual(
            resumo.total_multas_arrecadadas,
            Decimal("0.00"),
        )
        self.assertEqual(resumo.receita_liquida, Decimal("0.00"))
        self.assertEqual(resumo.valor_faturado, Decimal("0.00"))
        self.assertEqual(resumo.valor_recebido, Decimal("0.00"))
        self.assertEqual(resumo.valor_pendente, Decimal("0.00"))
        self.assertEqual(resumo.valor_cancelado, Decimal("0.00"))
        self.assertEqual(resumo.taxa_pagamento, Decimal("0.0"))
        self.assertEqual(resumo.cobertura_leituras, Decimal("0.0"))

    def test_indicadores_operacionais_e_financeiros_mistos(self):
        pendente = self.criar_apartamento("101", com_leitura=True)
        paga = self.criar_apartamento("102", com_leitura=True)
        cancelada = self.criar_apartamento("103")
        self.criar_apartamento("104")
        self.criar_fatura(
            pendente,
            Fatura.Status.PENDENTE,
            Decimal("100.10"),
        )
        self.criar_fatura(
            paga,
            Fatura.Status.PAGA,
            Decimal("200.20"),
        )
        self.criar_fatura(
            cancelada,
            Fatura.Status.CANCELADA,
            Decimal("300.30"),
        )

        resumo = obter_resumo_dashboard(Condominio.objects.get(), 7, 2026)

        self.assertEqual(resumo.total_apartamentos, 4)
        self.assertEqual(resumo.apartamentos_com_leitura, 2)
        self.assertEqual(resumo.apartamentos_sem_leitura, 2)
        self.assertEqual(resumo.apartamentos_com_fatura, 3)
        self.assertEqual(resumo.apartamentos_sem_fatura, 1)
        self.assertEqual(resumo.faturas_pendentes, 1)
        self.assertEqual(resumo.faturas_pagas, 1)
        self.assertEqual(resumo.faturas_canceladas, 1)
        self.assertEqual(resumo.valor_faturado, Decimal("300.30"))
        self.assertEqual(resumo.valor_recebido, Decimal("200.20"))
        self.assertEqual(resumo.valor_pendente, Decimal("100.10"))
        self.assertEqual(resumo.valor_cancelado, Decimal("300.30"))
        self.assertEqual(resumo.taxa_pagamento, Decimal("50.0"))
        self.assertEqual(
            resumo.taxa_inadimplencia,
            Decimal("50.0"),
        )
        self.assertEqual(resumo.cobertura_leituras, Decimal("50.0"))
        self.assertEqual(
            resumo.cobertura_faturamento,
            Decimal("75.0"),
        )

    def test_indicadores_financeiros_consideram_vencimento_e_valor_final(self):
        paga = self.criar_fatura(
            self.criar_apartamento("201"),
            Fatura.Status.PAGA,
            Decimal("200.00"),
        )
        vencida = self.criar_fatura(
            self.criar_apartamento("202"),
            Fatura.Status.PENDENTE,
            Decimal("100.00"),
        )
        a_vencer = self.criar_fatura(
            self.criar_apartamento("203"),
            Fatura.Status.PENDENTE,
            Decimal("150.00"),
        )
        self.criar_fatura(
            self.criar_apartamento("204"),
            Fatura.Status.CANCELADA,
            Decimal("50.00"),
        )
        Fatura.objects.filter(pk=paga.pk).update(
            valor_final=Decimal("195.00"),
            valor_pago=Decimal("195.00"),
            valor_bonificacao_aplicada=Decimal("10.00"),
            valor_multa_aplicada=Decimal("5.00"),
            data_pagamento=date(2026, 7, 5),
        )
        Fatura.objects.filter(pk=vencida.pk).update(
            data_vencimento=date(2026, 7, 10),
        )
        Fatura.objects.filter(pk=a_vencer.pk).update(
            data_vencimento=date(2026, 7, 25),
        )

        resumo = obter_resumo_dashboard(
            Condominio.objects.get(),
            7,
            2026,
            data_referencia=date(2026, 7, 20),
        )

        self.assertEqual(resumo.receitas_previstas, Decimal("450.00"))
        self.assertEqual(resumo.receitas_recebidas, Decimal("195.00"))
        self.assertEqual(resumo.receitas_pendentes, Decimal("250.00"))
        self.assertEqual(resumo.receitas_vencidas, Decimal("100.00"))
        self.assertEqual(resumo.faturas_pagas, 1)
        self.assertEqual(resumo.faturas_pendentes, 2)
        self.assertEqual(resumo.faturas_vencidas, 1)
        self.assertEqual(resumo.taxa_inadimplencia, Decimal("33.3"))
        self.assertEqual(
            resumo.total_bonificacoes_concedidas,
            Decimal("10.00"),
        )
        self.assertEqual(
            resumo.total_multas_arrecadadas,
            Decimal("5.00"),
        )
        self.assertEqual(resumo.receita_liquida, Decimal("195.00"))

    def test_percentuais_arredondam_com_uma_casa(self):
        apartamentos = [
            self.criar_apartamento(
                str(numero),
                com_leitura=numero == 1,
            )
            for numero in range(1, 4)
        ]
        self.criar_fatura(
            apartamentos[0],
            Fatura.Status.PAGA,
            Decimal("1.01"),
        )
        self.criar_fatura(
            apartamentos[1],
            Fatura.Status.PAGA,
            Decimal("2.02"),
        )
        self.criar_fatura(
            apartamentos[2],
            Fatura.Status.PENDENTE,
            Decimal("3.03"),
        )

        resumo = obter_resumo_dashboard(Condominio.objects.get(), 7, 2026)

        self.assertEqual(resumo.taxa_pagamento, Decimal("66.7"))
        self.assertEqual(
            resumo.taxa_inadimplencia,
            Decimal("33.3"),
        )
        self.assertEqual(resumo.cobertura_leituras, Decimal("33.3"))
        self.assertEqual(
            resumo.cobertura_faturamento,
            Decimal("100.0"),
        )

    def test_dashboard_agrega_total_persistido_com_aluguel_e_desconto(self):
        apartamento = self.criar_apartamento("501")
        Fatura.objects.create(
            apartamento=apartamento,
            mes=7,
            ano=2026,
            consumo_agua=0,
            consumo_gas=0,
            valor_aluguel=Decimal("1000.00"),
            desconto=Decimal("50.00"),
            valor_total=Decimal("950.00"),
            status=Fatura.Status.PENDENTE,
            apartamento_numero_emissao=apartamento.numero,
        )

        resumo = obter_resumo_dashboard(Condominio.objects.get(), 7, 2026)

        self.assertEqual(resumo.valor_faturado, Decimal("950.00"))
        self.assertEqual(resumo.valor_pendente, Decimal("950.00"))

    def test_listas_sao_limitadas_e_indicam_excedente(self):
        for numero in range(1, 7):
            self.criar_apartamento(str(numero))

        resumo = obter_resumo_dashboard(Condominio.objects.get(), 7, 2026)

        self.assertEqual(len(resumo.lista_sem_leitura.itens), 5)
        self.assertTrue(resumo.lista_sem_leitura.tem_mais)
        self.assertEqual(len(resumo.lista_sem_fatura.itens), 5)
        self.assertTrue(resumo.lista_sem_fatura.tem_mais)

    def test_service_executa_cinco_queries_de_dominio(self):
        self.criar_apartamento("101", com_leitura=True)

        with self.assertNumQueries(6):
            obter_resumo_dashboard(Condominio.objects.get(), 7, 2026)

    def test_interface_exibe_cards_listas_links_e_moeda_brasileira(self):
        usuario = get_user_model().objects.create_user(
            username="operador-interface-dashboard",
            password="senha-de-teste",
            is_staff=True,
        )
        self.client.force_login(usuario)
        apartamento = self.criar_apartamento(
            "701",
            com_leitura=True,
        )
        fatura = self.criar_fatura(
            apartamento,
            Fatura.Status.PENDENTE,
            Decimal("1234.56"),
        )

        resposta = self.client.get(
            reverse("dashboard:inicio"),
            {"mes": "7", "ano": "2026"},
        )

        for texto in (
            "Total de apartamentos",
            "Com leitura",
            "Apartamentos sem leitura",
            "Com fatura",
            "Apartamentos sem fatura",
            "Faturas pendentes",
            "Pagas",
            "Vencidas",
            "Canceladas",
            "Receitas previstas",
            "Receitas recebidas",
            "Receitas pendentes",
            "Receitas vencidas",
            "Valor cancelado",
            "Taxa de pagamento",
            "Inadimplência",
            "Bonificações concedidas",
            "Multas arrecadadas",
            "Receita líquida do período",
            "Cobertura de faturamento",
        ):
            with self.subTest(texto=texto):
                self.assertContains(resposta, texto)
        self.assertContains(resposta, "R$ 1.234,56")
        self.assertContains(
            resposta,
            reverse("faturas:detalhes", args=[fatura.id]),
        )
        self.assertContains(
            resposta,
            "?mes=7&amp;ano=2026&amp;status=pendente",
        )
        self.assertContains(
            resposta,
            'class="dashboard-hero-value"',
            count=4,
        )
        self.assertContains(
            resposta,
            'id="indicadoresDetalhados" class="collapse"',
        )
        self.assertContains(
            resposta,
            'id="filtroCompetencia" class="collapse"',
        )
        self.assertContains(resposta, "Visão executiva")
        self.assertContains(resposta, "Ações rápidas")
        self.assertContains(resposta, 'class="dashboard-quick-action"', count=4)
        self.assertContains(resposta, 'class="dashboard-status-bar"')
        self.assertContains(resposta, "Fechamento mensal")

    def test_lista_sem_fatura_aponta_para_leitura_quando_existir(self):
        usuario = get_user_model().objects.create_user(
            username="operador-links-dashboard",
            password="senha-de-teste",
            is_staff=True,
        )
        self.client.force_login(usuario)
        apartamento = self.criar_apartamento(
            "702",
            com_leitura=True,
        )
        leitura = apartamento.leituras.get(mes=7, ano=2026)

        resposta = self.client.get(
            reverse("dashboard:inicio"),
            {"mes": "7", "ano": "2026"},
        )

        self.assertContains(
            resposta,
            f"{reverse('faturas:gerar')}?leitura={leitura.id}",
        )

    def test_interface_trata_estados_vazios(self):
        usuario = get_user_model().objects.create_user(
            username="operador-vazio-dashboard",
            password="senha-de-teste",
            is_staff=True,
        )
        self.client.force_login(usuario)

        resposta = self.client.get(
            reverse("dashboard:inicio"),
            {"mes": "7", "ano": "2026"},
        )

        self.assertContains(resposta, "Nenhum apartamento cadastrado")
        self.assertContains(resposta, "R$ 0,00", count=8)

