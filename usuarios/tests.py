from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.exceptions import PermissionDenied
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from condominios.models import Condominio, VinculoUsuarioCondominio
from condominios.permissions import Permissao, usuario_possui_permissao
from condominios.services import CHAVE_CONDOMINIO_ATIVO

from .models import AuditoriaAcesso
from .services import alterar_acesso, cadastrar_usuario


class BaseAcessoTests(TestCase):
    def setUp(self):
        self.condominio = Condominio.objects.order_by("id").first()
        if self.condominio is None:
            self.condominio = Condominio.objects.create(nome="Condomínio Teste")
        self.owner = get_user_model().objects.create_user(
            "proprietario", "owner@example.com", "Senha-forte-2026"
        )
        self.vinculo_owner = VinculoUsuarioCondominio.objects.create(
            usuario=self.owner,
            condominio=self.condominio,
            papel=VinculoUsuarioCondominio.Papel.PROPRIETARIO,
        )


class AutenticacaoTests(BaseAcessoTests):
    def test_login_valido_e_invalido(self):
        resposta = self.client.post(reverse("login"), {
            "username": self.owner.username,
            "password": "Senha-forte-2026",
        })
        self.assertRedirects(resposta, reverse("dashboard:inicio"))
        self.client.logout()
        resposta = self.client.post(reverse("login"), {
            "username": self.owner.username,
            "password": "incorreta",
        })
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Usuário ou senha inválidos")

    def test_usuario_inativo_nao_autentica(self):
        self.owner.is_active = False
        self.owner.save(update_fields=["is_active"])
        resposta = self.client.post(reverse("login"), {
            "username": self.owner.username,
            "password": "Senha-forte-2026",
        })
        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_pagina_protegida_logout_e_sessao_expirada(self):
        url = reverse("dashboard:inicio")
        self.assertRedirects(
            self.client.get(url),
            f"{reverse('login')}?next={url}",
        )
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(url).status_code, 200)
        resposta = self.client.post(reverse("logout"))
        self.assertRedirects(resposta, reverse("login"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_alteracao_de_senha(self):
        self.client.force_login(self.owner)
        resposta = self.client.post(reverse("password_change"), {
            "old_password": "Senha-forte-2026",
            "new_password1": "Senha-nova-forte-2026",
            "new_password2": "Senha-nova-forte-2026",
        })
        self.assertRedirects(resposta, reverse("usuarios:perfil"))
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.check_password("Senha-nova-forte-2026"))

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
    )
    def test_recuperacao_e_redefinicao_de_senha(self):
        resposta = self.client.post(reverse("password_reset"), {
            "email": self.owner.email,
        })
        self.assertRedirects(resposta, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        uid = urlsafe_base64_encode(force_bytes(self.owner.pk))
        token = default_token_generator.make_token(self.owner)
        resposta = self.client.get(
            reverse("password_reset_confirm", args=[uid, token])
        )
        self.assertEqual(resposta.status_code, 302)
        redefinir = resposta.url
        resposta = self.client.post(redefinir, {
            "new_password1": "Outra-senha-forte-2026",
            "new_password2": "Outra-senha-forte-2026",
        })
        self.assertRedirects(resposta, reverse("password_reset_complete"))

    def test_token_invalido_exibe_mensagem_segura(self):
        resposta = self.client.get(
            reverse("password_reset_confirm", args=["invalid", "invalid"])
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "inválido ou expirou")


class PermissoesEGestaoTests(BaseAcessoTests):
    def criar_vinculado(self, nome, papel, condominio=None, ativo=True):
        usuario = get_user_model().objects.create_user(
            nome, f"{nome}@example.com", "Senha-forte-2026"
        )
        vinculo = VinculoUsuarioCondominio.objects.create(
            usuario=usuario,
            condominio=condominio or self.condominio,
            papel=papel,
            ativo=ativo,
        )
        return usuario, vinculo

    def test_matriz_dos_cargos_condominiais(self):
        P = VinculoUsuarioCondominio.Papel
        proprietario_admin, _ = self.criar_vinculado(
            "proprietario-admin", P.PROPRIETARIO_ADMINISTRATIVO
        )
        admin, _ = self.criar_vinculado("admin", P.ADMINISTRADOR)
        operador, _ = self.criar_vinculado("operador", P.OPERADOR)
        consulta, _ = self.criar_vinculado("consulta", P.CONSULTA)
        self.assertTrue(usuario_possui_permissao(
            self.owner, self.condominio, Permissao.RESCINDIR_CONTRATO
        ))
        self.assertFalse(usuario_possui_permissao(
            self.owner, self.condominio, Permissao.GERENCIAR_CONTRATOS
        ))
        self.assertTrue(usuario_possui_permissao(
            proprietario_admin,
            self.condominio,
            Permissao.GERENCIAR_CONTRATOS,
        ))
        self.assertTrue(usuario_possui_permissao(
            admin, self.condominio, Permissao.GERENCIAR_USUARIOS
        ))
        self.assertTrue(usuario_possui_permissao(
            operador, self.condominio, Permissao.MARCAR_FATURA_PAGA
        ))
        self.assertFalse(usuario_possui_permissao(
            consulta, self.condominio, Permissao.CRIAR_OPERACIONAL
        ))

    def test_cadastro_hash_duplicidade_e_auditoria(self):
        usuario, vinculo = cadastrar_usuario(
            executor=self.owner,
            condominio=self.condominio,
            username="novo",
            email="novo@example.com",
            first_name="Novo",
            last_name="Usuário",
            senha_temporaria="Senha-temporaria-forte-2026",
            papel=VinculoUsuarioCondominio.Papel.ADMINISTRADOR,
        )
        self.assertNotEqual(usuario.password, "Senha-temporaria-forte-2026")
        self.assertTrue(usuario.check_password("Senha-temporaria-forte-2026"))
        self.assertEqual(vinculo.condominio, self.condominio)
        self.assertTrue(AuditoriaAcesso.objects.filter(
            usuario_afetado=usuario, acao="criacao"
        ).exists())
        with self.assertRaisesRegex(ValueError, "nome"):
            cadastrar_usuario(
                executor=self.owner,
                condominio=self.condominio,
                username="NOVO",
                email="outro@example.com",
                first_name="Outro",
                last_name="Usuário",
                senha_temporaria="Senha-temporaria-forte-2026",
                papel=VinculoUsuarioCondominio.Papel.ADMINISTRADOR,
            )

    def test_senha_parecida_com_usuario_retorna_erro_no_formulario(self):
        self.client.force_login(self.owner)
        resposta = self.client.post(reverse("usuarios:novo"), {
            "first_name": "Usuário",
            "last_name": "Teste",
            "username": "usuario",
            "email": "usuario@example.com",
            "senha_temporaria": "usuario",
            "papel": VinculoUsuarioCondominio.Papel.OPERADOR,
            "ativo": "on",
        })
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "A senha é muito parecida")
        self.assertFalse(
            get_user_model().objects.filter(username="usuario").exists()
        )

    def test_admin_nao_cria_nem_altera_proprietario(self):
        P = VinculoUsuarioCondominio.Papel
        admin, _ = self.criar_vinculado("admin2", P.ADMINISTRADOR)
        alvo, vinculo = self.criar_vinculado("alvo", P.OPERADOR)
        with self.assertRaises(PermissionDenied):
            alterar_acesso(
                vinculo.id,
                executor=admin,
                condominio=self.condominio,
                papel=P.PROPRIETARIO,
                ativo=True,
                conta_ativa=True,
            )
        with self.assertRaises(PermissionDenied):
            alterar_acesso(
                self.vinculo_owner.id,
                executor=admin,
                condominio=self.condominio,
                papel=P.ADMINISTRADOR,
                ativo=True,
                conta_ativa=True,
            )

    def test_autoelevacao_e_ultimo_proprietario_sao_bloqueados(self):
        P = VinculoUsuarioCondominio.Papel
        admin, vinculo = self.criar_vinculado("admin3", P.ADMINISTRADOR)
        with self.assertRaises(PermissionDenied):
            alterar_acesso(
                vinculo.id,
                executor=admin,
                condominio=self.condominio,
                papel=P.PROPRIETARIO,
                ativo=True,
                conta_ativa=True,
            )
        global_admin = get_user_model().objects.create_superuser(
            username="global-protecao",
            email="global@example.com",
            password="Senha-forte-2026",
        )
        with self.assertRaisesRegex(ValueError, "último proprietário"):
            alterar_acesso(
                self.vinculo_owner.id,
                executor=global_admin,
                condominio=self.condominio,
                papel=P.PROPRIETARIO,
                ativo=False,
                conta_ativa=True,
            )
        with self.assertRaisesRegex(ValueError, "último proprietário"):
            alterar_acesso(
                self.vinculo_owner.id,
                executor=global_admin,
                condominio=self.condominio,
                papel=P.PROPRIETARIO,
                ativo=True,
                conta_ativa=False,
            )

    def test_consulta_nao_acessa_formulario_nem_post(self):
        consulta, _ = self.criar_vinculado(
            "consulta2", VinculoUsuarioCondominio.Papel.CONSULTA
        )
        self.client.force_login(consulta)
        self.assertEqual(
            self.client.get(reverse("apartamentos:novo")).status_code, 403
        )
        self.assertEqual(
            self.client.post(reverse("apartamentos:novo"), {}).status_code, 403
        )

    def test_isolamento_e_listagem_limitada_ao_condominio(self):
        outro = Condominio.objects.create(nome="Outro condomínio")
        externo, _ = self.criar_vinculado(
            "externo",
            VinculoUsuarioCondominio.Papel.ADMINISTRADOR,
            condominio=outro,
        )
        self.client.force_login(self.owner)
        sessao = self.client.session
        sessao[CHAVE_CONDOMINIO_ATIVO] = self.condominio.id
        sessao.save()
        resposta = self.client.get(reverse("usuarios:lista"))
        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, externo.username)

    def test_vinculo_inativo_limpa_condominio_da_sessao(self):
        self.client.force_login(self.owner)
        sessao = self.client.session
        sessao[CHAVE_CONDOMINIO_ATIVO] = self.condominio.id
        sessao.save()
        self.vinculo_owner.ativo = False
        self.vinculo_owner.save(update_fields=["ativo"])
        resposta = self.client.get(reverse("dashboard:inicio"))
        self.assertRedirects(
            resposta,
            reverse("condominios:selecionar")
            + "?next=%2F",
        )
        self.assertNotIn(CHAVE_CONDOMINIO_ATIVO, self.client.session)
