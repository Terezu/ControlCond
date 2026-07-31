from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import date, timedelta

from apartamentos.models import Apartamento
from condominios.models import Condominio, VinculoUsuarioCondominio
from condominios.permissions import (
    Permissao,
    usuario_possui_permissao,
)

from contratos.models import Contrato
from faturas.models import Fatura, HistoricoFinanceiroFatura
from pessoas.models import Pessoa

from .models import AuditoriaAcesso, AuditoriaRemocaoUsuario
from .services import (
    analisar_exclusao_usuario,
    anonimizar_usuario,
    desativar_conta_usuario,
    executar_remocao_segura_usuario,
    excluir_usuario_permanentemente,
    reativar_conta_usuario,
)


class RemocaoSeguraUsuarioTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.global_admin = self.User.objects.create_superuser(
            "global-remocao",
            "global-remocao@example.com",
            "Senha-forte-2026",
        )
        self.condominio = Condominio.objects.order_by("id").first()
        if self.condominio is None:
            self.condominio = Condominio.objects.create(nome="Remoção")

    def usuario(self, nome="alvo"):
        return self.User.objects.create_user(
            nome,
            f"{nome}@example.com",
            "Senha-forte-2026",
            first_name="Nome pessoal",
            last_name="Sobrenome pessoal",
        )

    def test_permissao_e_exclusiva_do_global(self):
        global_ = self.global_admin
        self.assertTrue(usuario_possui_permissao(
            global_, None, Permissao.EXCLUIR_USUARIO_PERMANENTEMENTE
        ))
        for papel in VinculoUsuarioCondominio.Papel.values:
            usuario = self.usuario(f"papel-{papel}")
            VinculoUsuarioCondominio.objects.create(
                usuario=usuario,
                condominio=self.condominio,
                papel=papel,
            )
            self.assertFalse(usuario_possui_permissao(
                usuario,
                self.condominio,
                Permissao.EXCLUIR_USUARIO_PERMANENTEMENTE,
            ))

    def test_exclusao_fisica_sem_referencias_preserva_auditoria(self):
        alvo = self.usuario("sem-historico")
        alvo_id = alvo.pk
        cliente_alvo = Client()
        cliente_alvo.force_login(alvo)
        analise = analisar_exclusao_usuario(alvo)
        self.assertTrue(analise.exclusao_fisica_permitida)
        excluir_usuario_permanentemente(
            alvo.pk,
            executor=self.global_admin,
            justificativa="Solicitação excepcional validada.",
        )
        self.assertFalse(self.User.objects.filter(pk=alvo_id).exists())
        self.assertFalse(Session.objects.exists())
        auditoria = AuditoriaRemocaoUsuario.objects.get(
            usuario_alvo_id=alvo_id
        )
        self.assertEqual(auditoria.resultado, "exclusao_fisica_concluida")
        self.assertNotIn("example.com", str(auditoria.situacao_anterior))

    def test_usuario_com_vinculo_e_anonimizado_e_preserva_chave(self):
        alvo = self.usuario("com-vinculo")
        alvo_id = alvo.pk
        vinculo = VinculoUsuarioCondominio.objects.create(
            usuario=alvo,
            condominio=self.condominio,
            papel=VinculoUsuarioCondominio.Papel.CONSULTA,
        )
        auditoria_historica = AuditoriaAcesso.objects.create(
            executor=self.global_admin,
            usuario_afetado=alvo,
            condominio=self.condominio,
            acao="alteracao",
            justificativa="Registro histórico.",
            operacao_global=True,
        )
        analise = analisar_exclusao_usuario(alvo)
        self.assertTrue(analise.anonimizacao_obrigatoria)
        anonimizar_usuario(
            alvo.pk,
            executor=self.global_admin,
            justificativa="Preservação histórica obrigatória.",
        )
        alvo.refresh_from_db()
        vinculo.refresh_from_db()
        self.assertEqual(alvo.pk, alvo_id)
        self.assertFalse(alvo.is_active)
        self.assertFalse(vinculo.ativo)
        self.assertEqual(alvo.first_name, "")
        self.assertEqual(alvo.last_name, "")
        self.assertTrue(alvo.username.startswith("usuario_anonimo_"))
        self.assertTrue(alvo.email.endswith("@invalid.local"))
        self.assertFalse(alvo.has_usable_password())
        self.assertTrue(
            AuditoriaAcesso.objects.filter(pk=auditoria_historica.pk).exists()
        )
        auditoria = AuditoriaRemocaoUsuario.objects.get(
            usuario_alvo_id=alvo_id
        )
        self.assertNotIn("com-vinculo@example.com", str(auditoria.__dict__))

    def test_sessoes_sao_invalidadas_na_desativacao_e_reativacao_auditada(self):
        alvo = self.usuario("sessao")
        vinculo = VinculoUsuarioCondominio.objects.create(
            usuario=alvo,
            condominio=self.condominio,
            papel=VinculoUsuarioCondominio.Papel.CONSULTA,
        )
        token_anterior = default_token_generator.make_token(alvo)
        cliente_alvo = Client()
        cliente_alvo.force_login(alvo)
        self.assertTrue(Session.objects.exists())
        desativar_conta_usuario(
            alvo.pk,
            executor=self.global_admin,
            justificativa="Bloqueio global necessário.",
        )
        alvo.refresh_from_db()
        vinculo.refresh_from_db()
        self.assertFalse(alvo.is_active)
        self.assertTrue(vinculo.ativo)
        self.assertFalse(Session.objects.exists())
        self.assertFalse(
            default_token_generator.check_token(alvo, token_anterior)
        )
        reativar_conta_usuario(
            alvo.pk,
            executor=self.global_admin,
            justificativa="Acesso revisado.",
        )
        alvo.refresh_from_db()
        self.assertTrue(alvo.is_active)
        self.assertEqual(
            AuditoriaRemocaoUsuario.objects.filter(
                usuario_alvo_id=alvo.pk
            ).count(),
            2,
        )

    def test_protege_autoacao_justificativa_confirmacao_e_repeticao(self):
        with self.assertRaises(PermissionDenied):
            excluir_usuario_permanentemente(
                self.global_admin.pk,
                executor=self.global_admin,
                justificativa="Não deve executar.",
            )
        alvo = self.usuario("confirmacao")
        with self.assertRaisesRegex(ValueError, "justificativa"):
            excluir_usuario_permanentemente(
                alvo.pk, executor=self.global_admin, justificativa=" "
            )
        with self.assertRaisesRegex(ValueError, "Digite exatamente"):
            executar_remocao_segura_usuario(
                alvo.pk,
                executor=self.global_admin,
                justificativa="Solicitação válida.",
                confirmacao="INCORRETA",
                ciente=True,
            )
        vinculo = VinculoUsuarioCondominio.objects.create(
            usuario=alvo,
            condominio=self.condominio,
            papel=VinculoUsuarioCondominio.Papel.CONSULTA,
        )
        executar_remocao_segura_usuario(
            alvo.pk,
            executor=self.global_admin,
            justificativa="Solicitação válida.",
            confirmacao="ANONIMIZAR USUARIO",
            ciente=True,
        )
        vinculo.refresh_from_db()
        with self.assertRaisesRegex(ValueError, "já foi anonimizada"):
            anonimizar_usuario(
                alvo.pk,
                executor=self.global_admin,
                justificativa="Repetição indevida.",
            )

    def test_orm_e_admin_nao_contornam_fluxo(self):
        alvo = self.usuario("orm-bloqueado")
        with self.assertRaises(PermissionDenied), transaction.atomic():
            alvo.delete()
        self.assertTrue(self.User.objects.filter(pk=alvo.pk).exists())
        self.client.force_login(self.global_admin)
        resposta = self.client.post(
            reverse("admin:auth_user_delete", args=[alvo.pk]),
            {"post": "yes"},
        )
        self.assertEqual(resposta.status_code, 403)
        self.assertTrue(self.User.objects.filter(pk=alvo.pk).exists())

    def test_analise_detecta_contrato_fatura_pagamento_e_arquivamento(self):
        alvo = self.usuario("historico-modulos")
        apartamento = Apartamento.objects.create(
            condominio=self.condominio,
            numero="H-01",
            arquivado=True,
            ativo=False,
            arquivado_em=timezone.now(),
            arquivado_por=alvo,
            retencao_ate=date.today() + timedelta(days=365),
        )
        pessoa = Pessoa.objects.create(
            condominio=self.condominio,
            nome_completo="Pessoa Histórica",
            cpf="12345678901",
            email="pessoa-historica@example.com",
            telefone="11999999999",
        )
        Contrato.objects.create(
            condominio=self.condominio,
            apartamento=apartamento,
            pessoa_contratante=pessoa,
            responsavel_financeiro=pessoa,
            data_inicio=date.today() - timedelta(days=60),
            data_termino=date.today() - timedelta(days=1),
            situacao=Contrato.Situacao.RESCINDIDO,
            data_rescisao=date.today() - timedelta(days=10),
            justificativa_rescisao="Histórico",
            usuario_rescisao=alvo,
            rescindido_em=timezone.now(),
        )
        fatura = Fatura.objects.create(
            apartamento=apartamento,
            mes=1,
            ano=2026,
            consumo_agua=0,
            consumo_gas=0,
            apartamento_numero_emissao=apartamento.numero,
        )
        HistoricoFinanceiroFatura.objects.create(
            fatura=fatura,
            status_anterior=Fatura.Status.PENDENTE,
            novo_status=Fatura.Status.PAGA,
            acao=HistoricoFinanceiroFatura.Acao.PAGAMENTO_CONFIRMADO,
            usuario=alvo,
        )
        analise = analisar_exclusao_usuario(alvo)
        self.assertTrue(analise.anonimizacao_obrigatoria)
        chaves = set(analise.referencias)
        self.assertIn("apartamentos.apartamento", chaves)
        self.assertIn("contratos.contrato", chaves)
        self.assertIn("faturas.historicofinanceirofatura", chaves)
    def test_rotas_bloqueiam_nao_global_e_get_nao_executa(self):
        alvo = self.usuario("rota-alvo")
        nao_global = self.usuario("rota-comum")
        VinculoUsuarioCondominio.objects.create(
            usuario=nao_global,
            condominio=self.condominio,
            papel=VinculoUsuarioCondominio.Papel.ADMINISTRADOR,
        )
        self.client.force_login(nao_global)
        self.assertEqual(
            self.client.get(
                reverse("usuarios:analisar_remocao", args=[alvo.pk])
            ).status_code,
            403,
        )
        self.client.force_login(self.global_admin)
        self.assertEqual(
            self.client.get(
                reverse("usuarios:executar_remocao", args=[alvo.pk])
            ).status_code,
            405,
        )
        self.assertTrue(self.User.objects.filter(pk=alvo.pk).exists())
