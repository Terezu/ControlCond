from datetime import date

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apartamentos.models import Apartamento
from condominios.models import Condominio, VinculoUsuarioCondominio
from condominios.services import CHAVE_CONDOMINIO_ATIVO

from .models import Pessoa, VinculoPessoaApartamento
from .services import (
    cadastrar_pessoa,
    consultar_pessoa,
    criar_vinculo,
    editar_pessoa,
    editar_vinculo,
    encerrar_vinculo,
    listar_pessoas,
    normalizar_cpf,
    recuperar_responsavel_financeiro,
)


class PessoasServiceTests(TestCase):
    def setUp(self):
        self.condominio = Condominio.objects.get()
        self.outro_condominio = Condominio.objects.create(
            nome="Condomínio Pessoas B"
        )
        self.apartamento = Apartamento.objects.create(
            condominio=self.condominio,
            numero="101-P",
        )
        self.outro_apartamento = Apartamento.objects.create(
            condominio=self.outro_condominio,
            numero="101-P",
        )

    def pessoa(self, cpf="52998224725", **dados):
        padrao = {
            "condominio": self.condominio,
            "nome_completo": "Maria da Silva",
            "cpf": cpf,
            "rg": "",
            "email": "MARIA@example.com",
            "telefone": "(41) 99999-9999",
            "observacoes": "  Observação  ",
        }
        padrao.update(dados)
        return cadastrar_pessoa(**padrao)

    def test_cadastro_normaliza_e_persiste_dados(self):
        pessoa = self.pessoa(cpf="529.982.247-25")
        self.assertEqual(pessoa.cpf, "52998224725")
        self.assertEqual(pessoa.cpf_formatado, "529.982.247-25")
        self.assertEqual(pessoa.email, "maria@example.com")
        self.assertEqual(pessoa.observacoes, "Observação")
        self.assertEqual(pessoa.situacao, Pessoa.Situacao.ATIVA)
        self.assertFalse(pessoa.vinculos_apartamentos.exists())

    def test_cpf_invalido_ou_duplicado_e_rejeitado(self):
        for cpf in ("", "11111111111", "52998224724"):
            with self.subTest(cpf=cpf), self.assertRaises(ValueError):
                normalizar_cpf(cpf)
        self.pessoa()
        with self.assertRaisesRegex(ValueError, "Já existe"):
            self.pessoa(condominio=self.outro_condominio)

    def test_edicao_e_consulta_respeitam_condominio(self):
        pessoa = self.pessoa()
        atualizada = editar_pessoa(
            pessoa.id,
            condominio=self.condominio,
            nome_completo="Maria Atualizada",
            cpf=pessoa.cpf,
            rg="123",
            email="nova@example.com",
            telefone="41999999999",
            data_nascimento=date(1990, 1, 2),
            observacoes=None,
            situacao=Pessoa.Situacao.INATIVA,
        )
        self.assertEqual(atualizada.nome_completo, "Maria Atualizada")
        self.assertEqual(atualizada.situacao, Pessoa.Situacao.INATIVA)
        with self.assertRaisesRegex(ValueError, "não encontrada"):
            consultar_pessoa(
                pessoa.id, condominio=self.outro_condominio
            )

    def test_listagem_filtra_busca_situacao_e_vinculo(self):
        pessoa = self.pessoa()
        outra = self.pessoa(
            cpf="16899535009",
            nome_completo="João Souza",
            email="joao@example.com",
            situacao=Pessoa.Situacao.INATIVA,
        )
        criar_vinculo(
            condominio=self.condominio,
            pessoa_id=pessoa.id,
            apartamento_id=self.apartamento.id,
            tipo=VinculoPessoaApartamento.Tipo.MORADOR,
            data_inicio=date(2026, 1, 1),
        )
        self.assertEqual(
            list(listar_pessoas(
                condominio=self.condominio, busca="529.982"
            )),
            [pessoa],
        )
        self.assertEqual(
            list(listar_pessoas(
                condominio=self.condominio,
                situacao=Pessoa.Situacao.INATIVA,
            )),
            [outra],
        )
        self.assertEqual(
            list(listar_pessoas(
                condominio=self.condominio,
                tipo_vinculo=VinculoPessoaApartamento.Tipo.MORADOR,
            )),
            [pessoa],
        )

    def test_vinculo_preserva_historico_ao_encerrar(self):
        pessoa = self.pessoa()
        vinculo = criar_vinculo(
            condominio=self.condominio,
            pessoa_id=pessoa.id,
            apartamento_id=self.apartamento.id,
            tipo=VinculoPessoaApartamento.Tipo.PROPRIETARIO,
            data_inicio=date(2026, 1, 1),
        )
        encerrado = encerrar_vinculo(
            vinculo.id,
            condominio=self.condominio,
            data_fim=date(2026, 6, 30),
        )
        self.assertFalse(encerrado.ativo)
        self.assertEqual(encerrado.data_fim, date(2026, 6, 30))
        self.assertTrue(
            VinculoPessoaApartamento.objects.filter(pk=vinculo.id).exists()
        )

    def test_mesma_pessoa_pode_acumular_tipos_no_mesmo_apartamento(self):
        pessoa = self.pessoa()
        for tipo in (
            VinculoPessoaApartamento.Tipo.PROPRIETARIO,
            VinculoPessoaApartamento.Tipo.MORADOR,
            VinculoPessoaApartamento.Tipo.RESPONSAVEL_FINANCEIRO,
        ):
            criar_vinculo(
                condominio=self.condominio,
                pessoa_id=pessoa.id,
                apartamento_id=self.apartamento.id,
                tipo=tipo,
                data_inicio=date(2026, 1, 1),
            )
        self.assertEqual(
            pessoa.vinculos_apartamentos.filter(ativo=True).count(), 3
        )

    def test_edita_vinculo_sem_perder_identidade_ou_historico(self):
        pessoa = self.pessoa()
        vinculo = criar_vinculo(
            condominio=self.condominio,
            pessoa_id=pessoa.id,
            apartamento_id=self.apartamento.id,
            tipo=VinculoPessoaApartamento.Tipo.MORADOR,
            data_inicio=date(2026, 1, 1),
        )
        atualizado = editar_vinculo(
            vinculo.id,
            condominio=self.condominio,
            apartamento_id=self.apartamento.id,
            tipo=VinculoPessoaApartamento.Tipo.INQUILINO,
            data_inicio=date(2026, 2, 1),
        )
        self.assertEqual(atualizado.pk, vinculo.pk)
        self.assertEqual(
            atualizado.tipo, VinculoPessoaApartamento.Tipo.INQUILINO
        )
        self.assertEqual(atualizado.data_inicio, date(2026, 2, 1))

    def test_vinculo_rejeita_condominio_diferente_e_pessoa_inativa(self):
        pessoa = self.pessoa()
        with self.assertRaisesRegex(ValueError, "não encontrado"):
            criar_vinculo(
                condominio=self.condominio,
                pessoa_id=pessoa.id,
                apartamento_id=self.outro_apartamento.id,
                tipo=VinculoPessoaApartamento.Tipo.MORADOR,
                data_inicio=date(2026, 1, 1),
            )
        pessoa.situacao = Pessoa.Situacao.INATIVA
        pessoa.save()
        with self.assertRaisesRegex(ValueError, "pessoa inativa"):
            criar_vinculo(
                condominio=self.condominio,
                pessoa_id=pessoa.id,
                apartamento_id=self.apartamento.id,
                tipo=VinculoPessoaApartamento.Tipo.MORADOR,
                data_inicio=date(2026, 1, 1),
            )

    def test_apenas_um_responsavel_financeiro_ativo(self):
        primeira = self.pessoa()
        segunda = self.pessoa(
            cpf="16899535009",
            nome_completo="João Souza",
            email="joao@example.com",
        )
        vinculo = criar_vinculo(
            condominio=self.condominio,
            pessoa_id=primeira.id,
            apartamento_id=self.apartamento.id,
            tipo=(
                VinculoPessoaApartamento.Tipo.RESPONSAVEL_FINANCEIRO
            ),
            data_inicio=date(2026, 1, 1),
        )
        self.assertEqual(
            recuperar_responsavel_financeiro(self.apartamento),
            primeira,
        )
        with self.assertRaisesRegex(ValueError, "já possui"):
            criar_vinculo(
                condominio=self.condominio,
                pessoa_id=segunda.id,
                apartamento_id=self.apartamento.id,
                tipo=(
                    VinculoPessoaApartamento.Tipo.RESPONSAVEL_FINANCEIRO
                ),
                data_inicio=date(2026, 2, 1),
            )
        encerrar_vinculo(
            vinculo.id,
            condominio=self.condominio,
            data_fim=date(2026, 3, 31),
        )
        criar_vinculo(
            condominio=self.condominio,
            pessoa_id=segunda.id,
            apartamento_id=self.apartamento.id,
            tipo=VinculoPessoaApartamento.Tipo.RESPONSAVEL_FINANCEIRO,
            data_inicio=date(2026, 4, 1),
        )
        self.assertEqual(
            recuperar_responsavel_financeiro(
                self.apartamento, em=date(2026, 2, 1)
            ),
            primeira,
        )
        self.assertEqual(
            recuperar_responsavel_financeiro(self.apartamento),
            segunda,
        )

    def test_regras_criticas_tambem_estao_no_banco(self):
        pessoa = self.pessoa()
        VinculoPessoaApartamento.objects.create(
            pessoa=pessoa,
            apartamento=self.apartamento,
            tipo=VinculoPessoaApartamento.Tipo.INQUILINO,
            data_inicio=date(2026, 1, 1),
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            VinculoPessoaApartamento.objects.create(
                pessoa=pessoa,
                apartamento=self.apartamento,
                tipo=VinculoPessoaApartamento.Tipo.INQUILINO,
                data_inicio=date(2026, 2, 1),
            )


class PessoasPresentationTests(TestCase):
    def setUp(self):
        self.condominio = Condominio.objects.get()
        self.usuario = get_user_model().objects.create_user(
            username="pessoas-admin",
            password="senha",
            is_staff=True,
        )
        VinculoUsuarioCondominio.objects.get_or_create(
            usuario=self.usuario,
            condominio=self.condominio,
            defaults={
                "papel": VinculoUsuarioCondominio.Papel.ADMINISTRADOR,
                "ativo": True,
            },
        )
        self.client.force_login(self.usuario)
        sessao = self.client.session
        sessao[CHAVE_CONDOMINIO_ATIVO] = self.condominio.id
        sessao.save()
        self.apartamento = Apartamento.objects.create(
            condominio=self.condominio,
            numero="202-P",
        )
        self.pessoa = cadastrar_pessoa(
            condominio=self.condominio,
            nome_completo="Ana de Oliveira",
            cpf="11144477735",
            email="ana@example.com",
            telefone="41999990000",
        )

    def test_menu_lista_e_detalhes_seguem_padrao_visual(self):
        criar_vinculo(
            condominio=self.condominio,
            pessoa_id=self.pessoa.id,
            apartamento_id=self.apartamento.id,
            tipo=VinculoPessoaApartamento.Tipo.PROPRIETARIO,
            data_inicio=date(2026, 1, 1),
        )
        resposta = self.client.get(reverse("pessoas:lista"))
        self.assertContains(resposta, "Pessoas vinculadas")
        self.assertContains(
            resposta,
            (
                "Gerencie moradores, proprietários, inquilinos e "
                "responsáveis financeiros do condomínio."
            ),
        )
        self.assertContains(resposta, "Cadastrar pessoa")
        self.assertContains(resposta, "Pessoas cadastradas")
        self.assertContains(resposta, "Ana de Oliveira")
        self.assertContains(resposta, "Proprietário")
        self.assertContains(resposta, "Apartamento 202-P")
        self.assertContains(resposta, 'aria-current="page"')

        resposta = self.client.get(
            reverse("pessoas:detalhes", args=[self.pessoa.id])
        )
        self.assertContains(resposta, "Dados pessoais")
        self.assertContains(resposta, "Vínculos com apartamentos")
        self.assertContains(resposta, "Adicionar vínculo")
        self.assertContains(resposta, "Condomínio")
        self.assertContains(resposta, "Situação")

    def test_fluxo_de_cadastro_edicao_vinculo_e_encerramento(self):
        resposta = self.client.post(
            reverse("pessoas:nova"),
            {
                "nome_completo": "Carlos Lima",
                "cpf": "168.995.350-09",
                "rg": "",
                "email": "carlos@example.com",
                "telefone": "41988887777",
                "data_nascimento": "",
                "situacao": Pessoa.Situacao.ATIVA,
                "observacoes": "",
            },
        )
        criada = Pessoa.objects.get(cpf="16899535009")
        self.assertRedirects(
            resposta, reverse("pessoas:detalhes", args=[criada.id])
        )
        resposta = self.client.post(
            reverse("pessoas:novo_vinculo", args=[criada.id]),
            {
                "apartamento": self.apartamento.id,
                "tipo": VinculoPessoaApartamento.Tipo.MORADOR,
                "data_inicio": "2026-01-01",
            },
        )
        vinculo = criada.vinculos_apartamentos.get()
        self.assertRedirects(
            resposta, reverse("pessoas:detalhes", args=[criada.id])
        )
        resposta = self.client.post(
            reverse(
                "pessoas:editar_vinculo",
                args=[criada.id, vinculo.id],
            ),
            {
                "apartamento": self.apartamento.id,
                "tipo": VinculoPessoaApartamento.Tipo.INQUILINO,
                "data_inicio": "2026-02-01",
            },
        )
        self.assertRedirects(
            resposta, reverse("pessoas:detalhes", args=[criada.id])
        )
        vinculo.refresh_from_db()
        self.assertEqual(
            vinculo.tipo, VinculoPessoaApartamento.Tipo.INQUILINO
        )
        resposta = self.client.post(
            reverse(
                "pessoas:encerrar_vinculo",
                args=[criada.id, vinculo.id],
            ),
            {"data_fim": "2026-06-30"},
        )
        self.assertRedirects(
            resposta, reverse("pessoas:detalhes", args=[criada.id])
        )
        vinculo.refresh_from_db()
        self.assertFalse(vinculo.ativo)

    def test_detalhe_apartamento_exibe_vinculos_agrupados_e_historico(self):
        vinculo = criar_vinculo(
            condominio=self.condominio,
            pessoa_id=self.pessoa.id,
            apartamento_id=self.apartamento.id,
            tipo=VinculoPessoaApartamento.Tipo.PROPRIETARIO,
            data_inicio=date(2025, 1, 1),
        )
        encerrar_vinculo(
            vinculo.id,
            condominio=self.condominio,
            data_fim=date(2025, 12, 31),
        )
        resposta = self.client.get(
            reverse("apartamentos:detalhes", args=[self.apartamento.id])
        )
        self.assertContains(resposta, "Pessoas vinculadas")
        self.assertContains(resposta, "Proprietário")
        self.assertContains(resposta, "Ana de Oliveira")
        self.assertContains(resposta, "Encerrado")

    def test_outro_condominio_nao_pode_acessar_pessoa(self):
        outro = Condominio.objects.create(nome="Condomínio Isolado")
        outra = cadastrar_pessoa(
            condominio=outro,
            nome_completo="Pessoa Externa",
            cpf="93541134780",
            email="externa@example.com",
            telefone="41900000000",
        )
        resposta = self.client.get(
            reverse("pessoas:detalhes", args=[outra.id])
        )
        self.assertEqual(resposta.status_code, 404)
