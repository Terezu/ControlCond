from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from PIL import Image

from condominios.models import Condominio, VinculoUsuarioCondominio
from condominios.services import CHAVE_CONDOMINIO_ATIVO

from .models import AuditoriaConfiguracao, ConfiguracaoCondominio
from .services import (
    atualizar_configuracao_global,
    atualizar_configuracao_institucional,
    atualizar_configuracao_operacional,
    obter_configuracao,
)


class SeparacaoConfiguracoesTests(TestCase):
    def setUp(self):
        self.condominio = Condominio.objects.order_by("id").first()
        if self.condominio is None:
            self.condominio = Condominio.objects.create(nome="Configuração A")
        self.outro = Condominio.objects.create(nome="Configuração B")

    def usuario(self, nome, papel, condominio=None):
        usuario = get_user_model().objects.create_user(
            nome, f"{nome}@example.com", "Senha-forte-2026"
        )
        VinculoUsuarioCondominio.objects.create(
            usuario=usuario,
            condominio=condominio or self.condominio,
            papel=papel,
        )
        return usuario

    def cliente(self, usuario, condominio=None):
        cliente = Client()
        cliente.force_login(usuario)
        sessao = cliente.session
        sessao[CHAVE_CONDOMINIO_ATIVO] = (
            condominio or self.condominio
        ).pk
        sessao.save()
        return cliente

    def test_matriz_de_acesso_das_tres_areas(self):
        P = VinculoUsuarioCondominio.Papel
        casos = (
            (P.PROPRIETARIO, 200, 200, 403),
            (P.PROPRIETARIO_ADMINISTRATIVO, 200, 200, 403),
            (P.ADMINISTRADOR, 403, 200, 403),
            (P.OPERADOR, 403, 403, 403),
            (P.CONSULTA, 403, 403, 403),
        )
        for indice, (papel, institucional, operacional, global_) in enumerate(casos):
            with self.subTest(papel=papel):
                cliente = self.cliente(self.usuario(f"papel-{indice}", papel))
                self.assertEqual(
                    cliente.get(reverse("configuracoes:institucionais")).status_code,
                    institucional,
                )
                self.assertEqual(
                    cliente.get(reverse("configuracoes:operacionais")).status_code,
                    operacional,
                )
                self.assertEqual(
                    cliente.get(reverse("configuracoes:globais")).status_code,
                    global_,
                )

    def test_edicao_respeita_proprietario_pa_e_administrador(self):
        P = VinculoUsuarioCondominio.Papel
        proprietario = self.cliente(self.usuario("dono-config", P.PROPRIETARIO))
        self.assertEqual(
            proprietario.get(
                reverse("configuracoes:institucionais_editar")
            ).status_code, 200
        )
        self.assertEqual(
            proprietario.get(
                reverse("configuracoes:operacionais_editar")
            ).status_code, 403
        )
        for nome, papel in (
            ("pa-config", P.PROPRIETARIO_ADMINISTRATIVO),
            ("admin-config", P.ADMINISTRADOR),
        ):
            cliente = self.cliente(self.usuario(nome, papel))
            esperado_institucional = (
                200 if papel == P.PROPRIETARIO_ADMINISTRATIVO else 403
            )
            self.assertEqual(
                cliente.get(
                    reverse("configuracoes:institucionais_editar")
                ).status_code,
                esperado_institucional,
            )
            self.assertEqual(
                cliente.get(
                    reverse("configuracoes:operacionais_editar")
                ).status_code,
                200,
            )

    def test_proprietario_altera_cores_logo_e_identidade_por_post(self):
        P = VinculoUsuarioCondominio.Papel
        cliente = self.cliente(
            self.usuario("dono-post-institucional", P.PROPRIETARIO)
        )
        arquivo_logo = BytesIO()
        Image.new("RGB", (2, 2), "white").save(arquivo_logo, format="PNG")
        resposta = cliente.post(
            reverse("configuracoes:institucionais_editar"),
            {
                "nome": "Residencial Identidade",
                "pais": "Brasil",
                "cor_primaria": "#112233",
                "cor_secundaria": "#445566",
                "cor_destaque": "#DDEEFF",
                "logo": SimpleUploadedFile(
                    "logo.png",
                    arquivo_logo.getvalue(),
                    content_type="image/png",
                ),
            },
        )
        self.assertEqual(resposta.status_code, 302)
        configuracao = obter_configuracao(self.condominio)
        self.assertEqual(configuracao.nome, "Residencial Identidade")
        self.assertEqual(configuracao.cor_primaria, "#112233")
        self.assertTrue(configuracao.logo.name)

    def test_menu_exibe_somente_as_areas_autorizadas(self):
        P = VinculoUsuarioCondominio.Papel
        dono = self.cliente(self.usuario("menu-dono", P.PROPRIETARIO))
        html_dono = dono.get(reverse("dashboard:inicio")).content.decode()
        self.assertIn("Institucionais", html_dono)
        self.assertIn("Operacionais", html_dono)
        operador = self.cliente(self.usuario("menu-operador", P.OPERADOR))
        html_operador = operador.get(reverse("dashboard:inicio")).content.decode()
        self.assertNotIn(">Configurações<", html_operador)

    def test_services_bloqueiam_manipulacao_manual(self):
        P = VinculoUsuarioCondominio.Papel
        administrador = self.usuario("admin-service", P.ADMINISTRADOR)
        operador = self.usuario("operador-service", P.OPERADOR)
        with self.assertRaises(PermissionDenied):
            atualizar_configuracao_institucional(
                self.condominio, {"nome": "Inválido"}, usuario=administrador
            )
        with self.assertRaises(PermissionDenied):
            atualizar_configuracao_operacional(
                self.condominio, {"moeda": "USD"}, usuario=operador
            )
        with self.assertRaises(PermissionDenied):
            atualizar_configuracao_global(
                {"dias_retencao_padrao": 100}, usuario=administrador
            )

    def test_cores_sao_do_condominio_e_herdadas_em_sessoes_distintas(self):
        P = VinculoUsuarioCondominio.Papel
        dono = self.usuario("dono-tema", P.PROPRIETARIO)
        atualizar_configuracao_institucional(
            self.condominio,
            {
                "cor_primaria": "#123456",
                "cor_secundaria": "#654321",
                "cor_destaque": "#ABCDEF",
            },
            usuario=dono,
        )
        for indice, papel in enumerate((
            P.PROPRIETARIO, P.PROPRIETARIO_ADMINISTRATIVO,
            P.ADMINISTRADOR, P.OPERADOR, P.CONSULTA,
        )):
            usuario = self.usuario(f"tema-{indice}", papel)
            resposta = self.cliente(usuario).get(reverse("dashboard:inicio"))
            self.assertContains(resposta, "--controlcond-primary: #123456")
        outra_config = obter_configuracao(self.outro)
        self.assertNotEqual(outra_config.cor_primaria, "#123456")

    def test_global_usa_tema_padrao_e_nao_altera_institucional(self):
        global_admin = get_user_model().objects.create_superuser(
            "global-config", "global-config@example.com", "Senha-forte-2026"
        )
        cliente = self.cliente(global_admin)
        resposta = cliente.get(reverse("dashboard:inicio"))
        self.assertContains(resposta, "--controlcond-primary: #1F4E5F")
        self.assertEqual(
            cliente.post(
                reverse("configuracoes:institucionais_editar"),
                {"nome": "Tentativa global"},
            ).status_code,
            403,
        )
        self.assertEqual(
            cliente.get(reverse("configuracoes:globais")).status_code, 200
        )
        self.assertEqual(
            cliente.get(reverse("configuracoes:operacionais")).status_code,
            200,
        )
        self.assertEqual(
            cliente.post(
                reverse("configuracoes:operacionais_editar"),
                {"moeda": "USD"},
            ).status_code,
            403,
        )

    def test_auditoria_separa_as_tres_origens(self):
        P = VinculoUsuarioCondominio.Papel
        dono = self.usuario("dono-audit", P.PROPRIETARIO)
        admin = self.usuario("admin-audit", P.ADMINISTRADOR)
        global_admin = get_user_model().objects.create_superuser(
            "global-audit", "global-audit@example.com", "Senha-forte-2026"
        )
        atualizar_configuracao_institucional(
            self.condominio, {"nome": "Novo nome"}, usuario=dono
        )
        atualizar_configuracao_operacional(
            self.condominio, {"moeda": "BRL"}, usuario=admin
        )
        atualizar_configuracao_global(
            {"dias_retencao_padrao": 730}, usuario=global_admin
        )
        self.assertSetEqual(
            set(AuditoriaConfiguracao.objects.values_list("tipo", flat=True)),
            {"institucional", "operacional", "global"},
        )
