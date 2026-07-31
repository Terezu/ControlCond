from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apartamentos.models import Apartamento
from apartamentos.services import excluir_apartamento
from leituras.services import cadastrar_leitura
from pessoas.services import cadastrar_pessoa

from .models import Condominio, VinculoUsuarioCondominio
from .permissions import (
    MATRIZ_PERMISSOES,
    PERMISSOES_ADMINISTRADOR,
    PERMISSOES_NEGADAS_AO_GLOBAL,
    PERMISSOES_PROPRIETARIO,
    PERMISSOES_PROPRIETARIO_ADMINISTRATIVO,
    Permissao,
    permissoes_do_usuario,
    usuario_possui_permissao,
)
from .services import CHAVE_CONDOMINIO_ATIVO, listar_condominios_do_usuario
from usuarios.services import cadastrar_usuario


class NovaMatrizCargosTests(TestCase):
    def setUp(self):
        self.condominio = Condominio.objects.order_by("id").first()
        if self.condominio is None:
            self.condominio = Condominio.objects.create(nome="Matriz")

    def usuario(self, nome, papel):
        usuario = get_user_model().objects.create_user(
            nome, f"{nome}@example.com", "Senha-forte-2026"
        )
        VinculoUsuarioCondominio.objects.create(
            usuario=usuario,
            condominio=self.condominio,
            papel=papel,
        )
        return usuario

    def test_proprietario_administrativo_e_uniao_sem_lista_duplicada(self):
        P = VinculoUsuarioCondominio.Papel
        self.assertEqual(
            PERMISSOES_PROPRIETARIO_ADMINISTRATIVO,
            PERMISSOES_PROPRIETARIO | PERMISSOES_ADMINISTRADOR,
        )
        self.assertEqual(
            MATRIZ_PERMISSOES[P.PROPRIETARIO_ADMINISTRATIVO],
            PERMISSOES_PROPRIETARIO_ADMINISTRATIVO,
        )

    def test_matriz_financeira_rescisao_e_dados_sensiveis(self):
        P = VinculoUsuarioCondominio.Papel
        proprietario = self.usuario("dono-matriz", P.PROPRIETARIO)
        proprietario_admin = self.usuario(
            "dono-admin-matriz", P.PROPRIETARIO_ADMINISTRATIVO
        )
        administrador = self.usuario("admin-matriz", P.ADMINISTRADOR)
        operador = self.usuario("operador-matriz", P.OPERADOR)
        consulta = self.usuario("consulta-matriz", P.CONSULTA)

        self.assertTrue(usuario_possui_permissao(
            proprietario, self.condominio, Permissao.RESCINDIR_CONTRATO
        ))
        self.assertFalse(usuario_possui_permissao(
            proprietario, self.condominio, Permissao.MARCAR_FATURA_PAGA
        ))
        for usuario in (proprietario_admin, administrador, operador):
            self.assertTrue(usuario_possui_permissao(
                usuario, self.condominio, Permissao.MARCAR_FATURA_PAGA
            ))
        for usuario in (proprietario_admin, administrador):
            for permissao in (
                Permissao.CANCELAR_FATURA,
                Permissao.ESTORNAR_FATURA,
                Permissao.REABRIR_FATURA,
                Permissao.EDITAR_VALORES_FINANCEIROS,
            ):
                self.assertTrue(usuario_possui_permissao(
                    usuario, self.condominio, permissao
                ))
        for usuario in (administrador, operador, consulta):
            self.assertFalse(usuario_possui_permissao(
                usuario, self.condominio, Permissao.RESCINDIR_CONTRATO
            ))
        for usuario in (operador, consulta):
            self.assertFalse(usuario_possui_permissao(
                usuario,
                self.condominio,
                Permissao.VISUALIZAR_DADOS_PESSOAIS_SENSIVEIS,
            ))

    def test_global_independe_de_vinculo_e_acessa_todos_condominios(self):
        outro = Condominio.objects.create(nome="Outro global")
        global_admin = get_user_model().objects.create_superuser(
            "global", "global@example.com", "Senha-forte-2026"
        )
        # Remove somente o vínculo criado pelo adaptador de fixtures legadas
        # carregado durante a suíte; produção não cria esse vínculo.
        global_admin.vinculos_condominios.all().delete()
        self.assertFalse(global_admin.vinculos_condominios.exists())
        self.assertEqual(
            set(listar_condominios_do_usuario(global_admin)),
            {self.condominio, outro},
        )
        self.assertTrue(usuario_possui_permissao(
            global_admin, outro, Permissao.MANUTENCAO_GLOBAL
        ))
        permissoes = permissoes_do_usuario(global_admin, outro)
        self.assertSetEqual(
            set(PERMISSOES_NEGADAS_AO_GLOBAL),
            {
                Permissao.ALTERAR_CONFIGURACOES_INSTITUCIONAIS,
                Permissao.ALTERAR_CONFIGURACOES_OPERACIONAIS,
            },
        )
        self.assertTrue(PERMISSOES_NEGADAS_AO_GLOBAL.isdisjoint(permissoes))
        self.assertIn(Permissao.MANUTENCAO_GLOBAL, permissoes)

    def test_cargos_que_cada_executor_pode_criar(self):
        P = VinculoUsuarioCondominio.Papel
        casos = (
            (self.usuario("dono-cria", P.PROPRIETARIO), {P.ADMINISTRADOR}),
            (
                self.usuario(
                    "dono-admin-cria", P.PROPRIETARIO_ADMINISTRATIVO
                ),
                {P.ADMINISTRADOR, P.OPERADOR, P.CONSULTA},
            ),
            (
                self.usuario("admin-cria", P.ADMINISTRADOR),
                {P.OPERADOR, P.CONSULTA},
            ),
        )
        for indice, (executor, permitidos) in enumerate(casos):
            for papel in P.values:
                dados = {
                    "executor": executor,
                    "condominio": self.condominio,
                    "username": f"alvo-{indice}-{papel}",
                    "email": f"alvo-{indice}-{papel}@example.com",
                    "first_name": "Alvo",
                    "last_name": "Teste",
                    "senha_temporaria": "Senha-alvo-forte-2026",
                    "papel": papel,
                }
                if papel in permitidos:
                    _, vinculo = cadastrar_usuario(**dados)
                    self.assertEqual(vinculo.papel, papel)
                else:
                    with self.assertRaises(PermissionDenied):
                        cadastrar_usuario(**dados)

    def test_operador_nao_recebe_dados_sensiveis_no_html_ou_contexto(self):
        P = VinculoUsuarioCondominio.Papel
        operador = self.usuario("operador-privacidade", P.OPERADOR)
        pessoa = cadastrar_pessoa(
            condominio=self.condominio,
            nome_completo="Pessoa Privada",
            cpf="52998224725",
            rg="123456",
            email="privado@example.com",
            telefone="41999999999",
            observacoes="Observação confidencial",
        )
        self.client.force_login(operador)
        sessao = self.client.session
        sessao[CHAVE_CONDOMINIO_ATIVO] = self.condominio.id
        sessao.save()
        resposta = self.client.get(reverse(
            "pessoas:detalhes", args=[pessoa.id]
        ))
        self.assertContains(resposta, "Informação restrita")
        for segredo in (
            pessoa.cpf, pessoa.rg, pessoa.email,
            pessoa.telefone, pessoa.observacoes,
        ):
            self.assertNotContains(resposta, segredo)
        pessoa_contexto = resposta.context["pessoa"]
        self.assertEqual(pessoa_contexto.email, "Informação restrita")
        self.assertEqual(pessoa_contexto.telefone, "Informação restrita")


class ArquivamentoApartamentoTests(TestCase):
    def setUp(self):
        self.condominio = Condominio.objects.order_by("id").first()
        if self.condominio is None:
            self.condominio = Condominio.objects.create(nome="Arquivo")
        self.admin = get_user_model().objects.create_user(
            "admin-arquiva", password="Senha-forte-2026"
        )
        VinculoUsuarioCondominio.objects.create(
            usuario=self.admin,
            condominio=self.condominio,
            papel=VinculoUsuarioCondominio.Papel.ADMINISTRADOR,
        )

    def test_arquiva_preserva_e_libera_numero_e_bloco(self):
        apartamento = Apartamento.objects.create(
            condominio=self.condominio, numero="101", bloco="A"
        )
        excluir_apartamento(
            apartamento.id,
            condominio=self.condominio,
            usuario=self.admin,
        )
        apartamento.refresh_from_db()
        self.assertTrue(apartamento.arquivado)
        self.assertFalse(apartamento.ativo)
        self.assertEqual(apartamento.arquivado_por, self.admin)
        self.assertEqual(
            apartamento.retencao_ate,
            timezone.localdate() + timedelta(days=365),
        )
        novo = Apartamento.objects.create(
            condominio=self.condominio, numero="101", bloco="A"
        )
        self.assertNotEqual(novo.id, apartamento.id)
        self.assertEqual(
            Apartamento.objects.filter(
                condominio=self.condominio,
                numero="101",
                bloco="A",
                arquivado=False,
            ).count(),
            1,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            Apartamento.objects.create(
                condominio=self.condominio, numero="101", bloco="A"
            )
        with self.assertRaisesRegex(ValueError, "inválido"):
            cadastrar_leitura(
                apartamento,
                mes=7,
                ano=2026,
                leitura_agua=10,
            )

    def test_proprietario_operador_e_consulta_nao_arquivam(self):
        P = VinculoUsuarioCondominio.Papel
        for papel in (P.PROPRIETARIO, P.OPERADOR, P.CONSULTA):
            with self.subTest(papel=papel):
                usuario = get_user_model().objects.create_user(
                    f"nao-arquiva-{papel}", password="Senha-forte-2026"
                )
                VinculoUsuarioCondominio.objects.create(
                    usuario=usuario,
                    condominio=self.condominio,
                    papel=papel,
                )
                apartamento = Apartamento.objects.create(
                    condominio=self.condominio,
                    numero=f"N-{papel}",
                )
                with self.assertRaises(PermissionDenied):
                    excluir_apartamento(
                        apartamento.id,
                        condominio=self.condominio,
                        usuario=usuario,
                    )
