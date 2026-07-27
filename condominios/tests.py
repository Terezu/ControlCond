from datetime import date
from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.contrib.sessions.middleware import SessionMiddleware
from django.db.models.signals import post_save
from django.dispatch import receiver

from apartamentos.models import Apartamento
from configuracoes.models import (
    ConfiguracaoCondominio,
    FaixaTarifaAgua,
    TabelaTarifariaAgua,
    TarifaGas,
)
from configuracoes.services import (
    obter_configuracao,
    obter_tabela_agua_vigente,
    obter_tarifa_gas_vigente,
)
from dashboard.services import obter_resumo_dashboard
from faturas.models import Fatura

from .models import Condominio, VinculoUsuarioCondominio
from .services import (
    CHAVE_CONDOMINIO_ATIVO,
    definir_condominio_ativo,
    listar_condominios_do_usuario,
    obter_condominio_ativo,
    usuario_tem_acesso_ao_condominio,
)


@receiver(
    post_save,
    sender=get_user_model(),
    dispatch_uid="testes_vincular_staff_legado",
)
def _vincular_staff_dos_testes_legados(sender, instance, created, **kwargs):
    """Adapta somente fixtures antigas; não existe no código de produção."""
    if instance.is_staff:
        condominio = Condominio.objects.order_by("id").first()
        if condominio:
            VinculoUsuarioCondominio.objects.get_or_create(
                usuario=instance,
                condominio=condominio,
                defaults={
                    "papel": VinculoUsuarioCondominio.Papel.ADMINISTRADOR,
                    "ativo": True,
                },
            )


class FundacaoMulticondominioTests(TestCase):
    def setUp(self):
        self.inicial = Condominio.objects.get()
        self.a = self.inicial
        self.a.nome = "Condomínio A"
        self.a.save(update_fields=["nome"])
        self.b = Condominio.objects.create(nome="Condomínio B")
        self.usuario = get_user_model().objects.create_user(
            username="multi", password="senha"
        )

    def request(self):
        request = RequestFactory().get("/")
        request.user = self.usuario
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        return request

    def test_slug_unico_e_vinculos_com_papeis_distintos(self):
        outro = Condominio.objects.create(nome="Condomínio B")
        self.assertNotEqual(self.b.slug, outro.slug)
        VinculoUsuarioCondominio.objects.create(
            usuario=self.usuario, condominio=self.a,
            papel=VinculoUsuarioCondominio.Papel.ADMINISTRADOR,
        )
        VinculoUsuarioCondominio.objects.create(
            usuario=self.usuario, condominio=self.b,
            papel=VinculoUsuarioCondominio.Papel.CONSULTA,
        )
        self.assertEqual(listar_condominios_do_usuario(self.usuario).count(), 2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            VinculoUsuarioCondominio.objects.create(
                usuario=self.usuario, condominio=self.a,
                papel=VinculoUsuarioCondominio.Papel.OPERADOR,
            )

    def test_vinculo_ou_condominio_inativo_nao_concede_acesso(self):
        vinculo = VinculoUsuarioCondominio.objects.create(
            usuario=self.usuario, condominio=self.a,
            papel=VinculoUsuarioCondominio.Papel.OPERADOR, ativo=False,
        )
        self.assertFalse(usuario_tem_acesso_ao_condominio(self.usuario, self.a))
        vinculo.ativo = True
        vinculo.save()
        self.a.ativo = False
        self.a.save()
        self.assertFalse(usuario_tem_acesso_ao_condominio(self.usuario, self.a))

    def test_configuracoes_e_apartamentos_sao_isolados(self):
        config_a = obter_configuracao(self.a)
        config_b = obter_configuracao(self.b)
        config_a.nome = "Dados A"
        config_a.save()
        config_b.nome = "Dados B"
        config_b.save()
        apt_a = Apartamento.objects.create(
            condominio=self.a, numero="101"
        )
        apt_b = Apartamento.objects.create(
            condominio=self.b, numero="101"
        )
        self.assertNotEqual(config_a.pk, config_b.pk)
        self.assertEqual(apt_a.numero, apt_b.numero)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Apartamento.objects.create(condominio=self.a, numero="101")

    def test_tarifas_mesmo_periodo_em_condominios_distintos(self):
        tabela_a = TabelaTarifariaAgua.objects.get(condominio=self.a)
        tabela_b = TabelaTarifariaAgua.objects.create(
            condominio=self.b, nome="Água B",
            data_inicio_vigencia=date(2000, 1, 1),
        )
        FaixaTarifaAgua.objects.create(
            tabela=tabela_b, consumo_inicial=0, consumo_final=None,
            valor=Decimal("200"), ordem=1,
        )
        gas_b = TarifaGas.objects.create(
            condominio=self.b, nome="Gás B", valor_por_m3=Decimal("30"),
            data_inicio_vigencia=date(2000, 1, 1),
        )
        self.assertEqual(
            obter_tabela_agua_vigente(self.a, 1, 2026), tabela_a
        )
        self.assertEqual(
            obter_tabela_agua_vigente(self.b, 1, 2026), tabela_b
        )
        self.assertEqual(
            obter_tarifa_gas_vigente(self.b, 1, 2026), gas_b
        )

    def test_sessao_revalida_vinculo_e_auto_seleciona_unico(self):
        VinculoUsuarioCondominio.objects.create(
            usuario=self.usuario, condominio=self.a,
            papel=VinculoUsuarioCondominio.Papel.ADMINISTRADOR,
        )
        request = self.request()
        self.assertEqual(obter_condominio_ativo(request), self.a)
        definir_condominio_ativo(request, self.a)
        self.assertEqual(request.session[CHAVE_CONDOMINIO_ATIVO], self.a.pk)
        self.a.ativo = False
        self.a.save()
        self.assertIsNone(obter_condominio_ativo(request))
        self.assertNotIn(CHAVE_CONDOMINIO_ATIVO, request.session)
        with self.assertRaises(PermissionDenied):
            definir_condominio_ativo(request, self.b)

    def test_dashboard_nao_mistura_apartamentos(self):
        Apartamento.objects.create(condominio=self.a, numero="201")
        Apartamento.objects.create(condominio=self.b, numero="201")
        resumo = obter_resumo_dashboard(self.a, 1, 2026)
        self.assertEqual(resumo.total_apartamentos, 1)


class SelecaoVisualCondominioTests(TestCase):
    def setUp(self):
        self.a = Condominio.objects.get()
        self.a.nome = "Condomínio A"
        self.a.save(update_fields=["nome"])
        self.b = Condominio.objects.create(nome="Condomínio B")
        self.usuario = get_user_model().objects.create_user(
            username="seletor", password="senha", is_staff=True
        )
        self.vinculo_a, _ = VinculoUsuarioCondominio.objects.get_or_create(
            usuario=self.usuario, condominio=self.a,
            defaults={
                "papel": VinculoUsuarioCondominio.Papel.ADMINISTRADOR,
                "ativo": True,
            },
        )
        self.client.force_login(self.usuario)

    def vincular_b(self, **kwargs):
        return VinculoUsuarioCondominio.objects.create(
            usuario=self.usuario,
            condominio=self.b,
            papel=VinculoUsuarioCondominio.Papel.ADMINISTRADOR,
            **kwargs,
        )

    def test_um_condominio_e_selecionado_e_exibido_sem_troca(self):
        resposta = self.client.get(reverse("dashboard:inicio"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Condomínio A")
        self.assertNotContains(resposta, "Trocar condomínio ativo")
        self.assertEqual(
            self.client.session[CHAVE_CONDOMINIO_ATIVO], self.a.pk
        )

    def test_multiplos_sem_selecao_redirecionam_para_tela(self):
        self.vincular_b()
        resposta = self.client.get(reverse("dashboard:inicio"))
        self.assertRedirects(
            resposta,
            f"{reverse('condominios:selecionar')}?next=%2F",
            fetch_redirect_response=False,
        )
        selecao = self.client.get(reverse("condominios:selecionar"))
        self.assertContains(selecao, "Condomínio A")
        self.assertContains(selecao, "Condomínio B")

    def test_troca_exige_post_e_respeita_next_seguro(self):
        self.vincular_b()
        url = reverse("condominios:selecionar")
        self.client.get(url)
        self.assertNotIn(CHAVE_CONDOMINIO_ATIVO, self.client.session)
        resposta = self.client.post(
            url,
            {"condominio": self.b.pk, "next": reverse("apartamentos:lista")},
        )
        self.assertRedirects(
            resposta,
            reverse("apartamentos:lista"),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            self.client.session[CHAVE_CONDOMINIO_ATIVO], self.b.pk
        )
        resposta = self.client.post(
            url,
            {"condominio": self.a.pk, "next": "https://malicioso.test/"},
        )
        self.assertRedirects(
            resposta, reverse("dashboard:inicio"),
            fetch_redirect_response=False,
        )

    def test_nao_seleciona_sem_vinculo_inativo_ou_condominio_inativo(self):
        url = reverse("condominios:selecionar")
        resposta = self.client.post(url, {"condominio": self.b.pk})
        self.assertEqual(resposta.status_code, 403)
        vinculo = self.vincular_b(ativo=False)
        resposta = self.client.get(url)
        self.assertNotContains(resposta, "Condomínio B")
        vinculo.ativo = True
        vinculo.save()
        self.b.ativo = False
        self.b.save()
        resposta = self.client.get(url)
        self.assertNotContains(resposta, "Condomínio B")

    def test_sem_vinculo_inclusive_staff_ve_acesso_indisponivel(self):
        VinculoUsuarioCondominio.objects.filter(usuario=self.usuario).delete()
        resposta = self.client.get(reverse("dashboard:inicio"))
        self.assertEqual(resposta.status_code, 302)
        selecao = self.client.get(reverse("condominios:selecionar"))
        self.assertContains(
            selecao,
            "Seu usuário ainda não possui acesso a nenhum condomínio ativo.",
        )

    def test_troca_altera_apartamentos_e_bloqueia_objeto_anterior(self):
        self.vincular_b()
        apt_a = Apartamento.objects.create(
            condominio=self.a, numero="101-A"
        )
        Apartamento.objects.create(condominio=self.b, numero="101-B")
        url = reverse("condominios:selecionar")
        self.client.post(url, {"condominio": self.a.pk})
        resposta_a = self.client.get(reverse("apartamentos:lista"))
        self.assertContains(resposta_a, "101-A")
        self.assertNotContains(resposta_a, "101-B")
        self.client.post(url, {"condominio": self.b.pk})
        resposta_b = self.client.get(reverse("apartamentos:lista"))
        self.assertContains(resposta_b, "101-B")
        self.assertNotContains(resposta_b, "101-A")
        bloqueado = self.client.get(
            reverse("apartamentos:detalhes", args=[apt_a.pk])
        )
        self.assertEqual(bloqueado.status_code, 404)

    def test_troca_altera_dashboard_faturas_pdf_e_zip(self):
        self.vincular_b()
        apt_a = Apartamento.objects.create(
            condominio=self.a, numero="FAT-A"
        )
        apt_b = Apartamento.objects.create(
            condominio=self.b, numero="FAT-B"
        )
        fatura_a = Fatura.objects.create(
            apartamento=apt_a, mes=11, ano=2026,
            consumo_agua=0, consumo_gas=0,
            valor_aluguel=Decimal("100.00"),
            valor_total=Decimal("100.00"),
            apartamento_numero_emissao="FAT-A",
        )
        fatura_b = Fatura.objects.create(
            apartamento=apt_b, mes=11, ano=2026,
            consumo_agua=0, consumo_gas=0,
            valor_aluguel=Decimal("200.00"),
            valor_total=Decimal("200.00"),
            apartamento_numero_emissao="FAT-B",
        )
        selecionar = reverse("condominios:selecionar")
        self.client.post(selecionar, {"condominio": self.a.pk})
        dashboard_a = self.client.get(
            reverse("dashboard:inicio"), {"mes": 11, "ano": 2026}
        )
        self.assertEqual(
            dashboard_a.context["resumo"].valor_faturado,
            Decimal("100.00"),
        )
        lista_a = self.client.get(reverse("faturas:lista"))
        self.assertContains(lista_a, "FAT-A")
        self.assertNotContains(lista_a, "FAT-B")

        self.client.post(selecionar, {"condominio": self.b.pk})
        dashboard_b = self.client.get(
            reverse("dashboard:inicio"), {"mes": 11, "ano": 2026}
        )
        self.assertEqual(
            dashboard_b.context["resumo"].valor_faturado,
            Decimal("200.00"),
        )
        self.assertEqual(
            self.client.get(
                reverse("faturas:baixar_pdf", args=[fatura_a.pk])
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse("faturas:baixar_pdf", args=[fatura_b.pk])
            ).status_code,
            200,
        )
        zip_response = self.client.get(
            reverse(
                "faturas:baixar_faturas_mes",
                args=[2026, 11],
            )
        )
        with ZipFile(BytesIO(zip_response.content)) as arquivo:
            nomes = arquivo.namelist()
        self.assertEqual(len(nomes), 1)
        self.assertIn("FAT-B".lower(), nomes[0].lower())
