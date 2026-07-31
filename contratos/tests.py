from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apartamentos.models import Apartamento
from condominios.models import Condominio, VinculoUsuarioCondominio
from condominios.services import CHAVE_CONDOMINIO_ATIVO
from pessoas.models import VinculoPessoaApartamento
from pessoas.services import cadastrar_pessoa

from .models import (
    AuditoriaRescisaoContrato,
    Contrato,
    VinculoFinanceiroContrato,
)
from .selectors import classificar_contratos
from .services import (
    cadastrar_contrato,
    consultar_contrato,
    rescindir_contrato,
)


class ContratosServiceTests(TestCase):
    def setUp(self):
        self.hoje = timezone.localdate()
        self.condominio = Condominio.objects.get()
        self.outro_condominio = Condominio.objects.create(
            nome="Condomínio Contratos B"
        )
        self.apartamento = Apartamento.objects.create(
            condominio=self.condominio, numero="C-101"
        )
        self.outro_apartamento = Apartamento.objects.create(
            condominio=self.outro_condominio, numero="C-101"
        )
        self.contratante = cadastrar_pessoa(
            condominio=self.condominio,
            nome_completo="Contratante Teste",
            cpf="52998224725",
            email="contratante@example.com",
            telefone="41999990001",
        )
        self.responsavel = cadastrar_pessoa(
            condominio=self.condominio,
            nome_completo="Responsável Teste",
            cpf="16899535009",
            email="responsavel@example.com",
            telefone="41999990002",
        )
        self.usuario = get_user_model().objects.create_user(
            username="proprietario-contrato",
            password="senha",
            is_staff=True,
        )
        VinculoUsuarioCondominio.objects.update_or_create(
            usuario=self.usuario,
            condominio=self.condominio,
            defaults={
                "papel": VinculoUsuarioCondominio.Papel.PROPRIETARIO,
                "ativo": True,
            },
        )

    def criar(self, **alteracoes):
        dados = {
            "condominio": self.condominio,
            "apartamento_id": self.apartamento.id,
            "pessoa_contratante_id": self.contratante.id,
            "responsavel_financeiro_id": self.responsavel.id,
            "data_inicio": self.hoje - timedelta(days=10),
            "data_termino": self.hoje + timedelta(days=100),
            "observacoes": "Contrato de teste",
        }
        dados.update(alteracoes)
        return cadastrar_contrato(**dados)

    def test_criacao_valida_e_vinculo_financeiro_sem_morador(self):
        contrato = self.criar()
        self.assertEqual(contrato.situacao, Contrato.Situacao.ATIVO)
        vinculos = VinculoPessoaApartamento.objects.filter(
            apartamento=self.apartamento, pessoa=self.responsavel
        )
        self.assertTrue(vinculos.filter(
            tipo=VinculoPessoaApartamento.Tipo.RESPONSAVEL_FINANCEIRO,
            ativo=True,
        ).exists())
        self.assertFalse(vinculos.filter(
            tipo=VinculoPessoaApartamento.Tipo.MORADOR
        ).exists())

    def test_atualiza_vinculo_financeiro_existente(self):
        existente = VinculoPessoaApartamento.objects.create(
            pessoa=self.responsavel,
            apartamento=self.apartamento,
            tipo=VinculoPessoaApartamento.Tipo.RESPONSAVEL_FINANCEIRO,
            data_inicio=self.hoje,
        )
        contrato = self.criar(
            data_inicio=self.hoje - timedelta(days=30)
        )
        existente.refresh_from_db()
        self.assertEqual(existente.data_inicio, contrato.data_inicio)
        self.assertEqual(
            VinculoPessoaApartamento.objects.filter(
                apartamento=self.apartamento,
                tipo=VinculoPessoaApartamento.Tipo.RESPONSAVEL_FINANCEIRO,
                ativo=True,
            ).count(),
            1,
        )

    def test_termino_deve_ser_posterior_ao_inicio(self):
        for delta in (0, -1):
            with self.subTest(delta=delta), self.assertRaisesRegex(
                ValueError, "posterior"
            ):
                self.criar(
                    data_inicio=self.hoje,
                    data_termino=self.hoje + timedelta(days=delta),
                )

    def test_impede_sobreposicao_e_dois_ativos(self):
        self.criar()
        with self.assertRaisesRegex(ValueError, "sobreposto"):
            self.criar(
                data_inicio=self.hoje,
                data_termino=self.hoje + timedelta(days=200),
            )

    def test_impede_sobreposicao_de_contratos_futuros(self):
        self.criar(
            data_inicio=self.hoje + timedelta(days=100),
            data_termino=self.hoje + timedelta(days=200),
        )
        with self.assertRaisesRegex(ValueError, "sobreposto"):
            self.criar(
                data_inicio=self.hoje + timedelta(days=150),
                data_termino=self.hoje + timedelta(days=250),
            )

    def test_contrato_futuro(self):
        contrato = self.criar(
            data_inicio=self.hoje + timedelta(days=10),
            data_termino=self.hoje + timedelta(days=100),
        )
        self.assertEqual(contrato.situacao, Contrato.Situacao.FUTURO)
        self.assertEqual(
            classificar_contratos(self.condominio)["futuros"].count(), 1
        )

    def test_classificacao_proximo_vencimento_ate_45_dias(self):
        self.criar(data_termino=self.hoje + timedelta(days=45))
        resumo = classificar_contratos(self.condominio)
        self.assertEqual(resumo["ativos"].count(), 1)
        self.assertEqual(resumo["proximos"].count(), 1)

    def test_fora_da_janela_de_45_dias(self):
        self.criar(data_termino=self.hoje + timedelta(days=46))
        self.assertEqual(
            classificar_contratos(self.condominio)["proximos"].count(), 0
        )

    def test_encerramento_automatico_por_data(self):
        contrato = self.criar(
            data_inicio=self.hoje - timedelta(days=100),
            data_termino=self.hoje - timedelta(days=1),
        )
        self.assertEqual(contrato.situacao, Contrato.Situacao.ENCERRADO)
        contrato.situacao = Contrato.Situacao.ATIVO
        contrato.save(update_fields=["situacao"])
        atualizado = consultar_contrato(
            contrato.id, condominio=self.condominio
        )
        self.assertEqual(atualizado.situacao, Contrato.Situacao.ENCERRADO)

    def test_rescisao_exige_justificativa_e_impede_repeticao(self):
        contrato = self.criar()
        with self.assertRaisesRegex(ValueError, "justificativa"):
            rescindir_contrato(
                contrato.id,
                condominio=self.condominio,
                usuario=self.usuario,
                justificativa=" ",
            )
        rescindido = rescindir_contrato(
            contrato.id,
            condominio=self.condominio,
            usuario=self.usuario,
            justificativa="Acordo entre as partes.",
        )
        self.assertEqual(rescindido.situacao, Contrato.Situacao.RESCINDIDO)
        self.assertEqual(rescindido.usuario_rescisao, self.usuario)
        self.assertIsNotNone(rescindido.rescindido_em)
        with self.assertRaisesRegex(ValueError, "já foi rescindido"):
            rescindir_contrato(
                contrato.id,
                condominio=self.condominio,
                usuario=self.usuario,
                justificativa="Nova tentativa.",
            )
        self.assertEqual(
            AuditoriaRescisaoContrato.objects.filter(
                contrato=contrato
            ).count(),
            1,
        )
        self.assertTrue(Contrato.objects.filter(pk=contrato.id).exists())

    def test_rescisao_encerra_vinculo_financeiro_criado_exclusivamente(self):
        contrato = self.criar()
        dependencia = VinculoFinanceiroContrato.objects.get(
            contrato=contrato
        )
        self.assertTrue(dependencia.criado_pelo_contrato)
        rescindir_contrato(
            contrato.id,
            condominio=self.condominio,
            usuario=self.usuario,
            justificativa="  Encerramento solicitado.  ",
        )
        dependencia.vinculo.refresh_from_db()
        self.assertFalse(dependencia.vinculo.ativo)
        self.assertIsNotNone(dependencia.vinculo.data_fim)
        auditoria = AuditoriaRescisaoContrato.objects.get(
            contrato=contrato
        )
        self.assertEqual(auditoria.justificativa, "Encerramento solicitado.")
        self.assertEqual(
            auditoria.vinculo_financeiro_encerrado,
            dependencia.vinculo,
        )

    def test_rescisao_preserva_vinculo_manual_e_outros_tipos(self):
        financeiro = VinculoPessoaApartamento.objects.create(
            pessoa=self.responsavel,
            apartamento=self.apartamento,
            tipo=VinculoPessoaApartamento.Tipo.RESPONSAVEL_FINANCEIRO,
            data_inicio=self.hoje - timedelta(days=30),
        )
        proprietario = VinculoPessoaApartamento.objects.create(
            pessoa=self.responsavel,
            apartamento=self.apartamento,
            tipo=VinculoPessoaApartamento.Tipo.PROPRIETARIO,
            data_inicio=self.hoje - timedelta(days=30),
        )
        morador = VinculoPessoaApartamento.objects.create(
            pessoa=self.contratante,
            apartamento=self.apartamento,
            tipo=VinculoPessoaApartamento.Tipo.MORADOR,
            data_inicio=self.hoje - timedelta(days=30),
        )
        contrato = self.criar()
        self.assertFalse(
            contrato.dependencia_vinculo_financeiro.criado_pelo_contrato
        )
        rescindir_contrato(
            contrato.id,
            condominio=self.condominio,
            usuario=self.usuario,
            justificativa="Fim do contrato.",
        )
        for vinculo in (financeiro, proprietario, morador):
            vinculo.refresh_from_db()
            self.assertTrue(vinculo.ativo)
        self.responsavel.refresh_from_db()
        self.assertTrue(self.responsavel.pk)

    def test_rescisao_preserva_vinculo_compartilhado_com_contrato_futuro(self):
        atual = self.criar(data_termino=self.hoje + timedelta(days=10))
        futuro = self.criar(
            data_inicio=self.hoje + timedelta(days=11),
            data_termino=self.hoje + timedelta(days=100),
        )
        self.assertEqual(
            atual.dependencia_vinculo_financeiro.vinculo_id,
            futuro.dependencia_vinculo_financeiro.vinculo_id,
        )
        rescindir_contrato(
            atual.id,
            condominio=self.condominio,
            usuario=self.usuario,
            justificativa="Substituição programada.",
        )
        vinculo = atual.dependencia_vinculo_financeiro.vinculo
        vinculo.refresh_from_db()
        self.assertTrue(vinculo.ativo)

    def test_contrato_encerrado_nao_pode_ser_rescindido_e_futuro_pode(self):
        encerrado = self.criar(
            data_inicio=self.hoje - timedelta(days=20),
            data_termino=self.hoje - timedelta(days=1),
        )
        with self.assertRaisesRegex(ValueError, "encerrado naturalmente"):
            rescindir_contrato(
                encerrado.id,
                condominio=self.condominio,
                usuario=self.usuario,
                justificativa="Tentativa retroativa.",
            )
        futuro = self.criar(
            data_inicio=self.hoje + timedelta(days=10),
            data_termino=self.hoje + timedelta(days=30),
        )
        rescindir_contrato(
            futuro.id,
            condominio=self.condominio,
            usuario=self.usuario,
            justificativa="Cancelamento antecipado.",
        )
        futuro.refresh_from_db()
        self.assertEqual(futuro.situacao, Contrato.Situacao.RESCINDIDO)

    @patch("contratos.services.AuditoriaRescisaoContrato.objects.create")
    def test_falha_na_auditoria_reverte_toda_a_transacao(self, criar_auditoria):
        contrato = self.criar()
        vinculo = contrato.dependencia_vinculo_financeiro.vinculo
        criar_auditoria.side_effect = RuntimeError("falha simulada")
        with self.assertRaisesRegex(RuntimeError, "falha simulada"):
            rescindir_contrato(
                contrato.id,
                condominio=self.condominio,
                usuario=self.usuario,
                justificativa="Não deve persistir.",
            )
        contrato.refresh_from_db()
        vinculo.refresh_from_db()
        self.assertEqual(contrato.situacao, Contrato.Situacao.ATIVO)
        self.assertIsNone(contrato.data_rescisao)
        self.assertTrue(vinculo.ativo)

    def test_rescisao_rejeita_usuario_sem_papel_proprietario(self):
        contrato = self.criar()
        operador = get_user_model().objects.create_user(
            username="operador-contrato", is_staff=True
        )
        VinculoUsuarioCondominio.objects.update_or_create(
            usuario=operador,
            condominio=self.condominio,
            defaults={
                "papel": VinculoUsuarioCondominio.Papel.ADMINISTRADOR,
                "ativo": True,
            },
        )
        with self.assertRaises(PermissionDenied):
            rescindir_contrato(
                contrato.id,
                condominio=self.condominio,
                usuario=operador,
                justificativa="Sem autorização.",
            )

    def test_service_rejeita_vinculo_de_usuario_inativo(self):
        contrato = self.criar()
        vinculo = VinculoUsuarioCondominio.objects.get(
            usuario=self.usuario, condominio=self.condominio
        )
        vinculo.ativo = False
        vinculo.save(update_fields=["ativo"])
        with self.assertRaises(PermissionDenied):
            rescindir_contrato(
                contrato.id,
                condominio=self.condominio,
                usuario=self.usuario,
                justificativa="Acesso revogado.",
            )
        contrato.refresh_from_db()
        self.assertIsNone(contrato.data_rescisao)

    def test_isolamento_entre_condominios(self):
        contrato = self.criar()
        with self.assertRaisesRegex(ValueError, "não encontrado"):
            consultar_contrato(
                contrato.id, condominio=self.outro_condominio
            )
        with self.assertRaisesRegex(ValueError, "condomínio ativo"):
            self.criar(apartamento_id=self.outro_apartamento.id)


class ContratosPresentationTests(TestCase):
    def setUp(self):
        self.hoje = timezone.localdate()
        self.condominio = Condominio.objects.get()
        self.usuario = get_user_model().objects.create_user(
            username="dono-ui-contrato", password="senha", is_staff=True
        )
        VinculoUsuarioCondominio.objects.update_or_create(
            usuario=self.usuario,
            condominio=self.condominio,
            defaults={
                "papel": VinculoUsuarioCondominio.Papel.PROPRIETARIO,
                "ativo": True,
            },
        )
        self.client.force_login(self.usuario)
        sessao = self.client.session
        sessao[CHAVE_CONDOMINIO_ATIVO] = self.condominio.id
        sessao.save()
        self.apartamento = Apartamento.objects.create(
            condominio=self.condominio, numero="UI-301", bloco="A"
        )
        self.pessoa = cadastrar_pessoa(
            condominio=self.condominio,
            nome_completo="Pessoa Contrato UI",
            cpf="11144477735",
            email="ui@example.com",
            telefone="41999990003",
        )
        self.contrato = cadastrar_contrato(
            condominio=self.condominio,
            apartamento_id=self.apartamento.id,
            pessoa_contratante_id=self.pessoa.id,
            responsavel_financeiro_id=self.pessoa.id,
            data_inicio=self.hoje - timedelta(days=5),
            data_termino=self.hoje + timedelta(days=30),
        )

    def test_listagem_cards_abas_tabela_e_menu(self):
        resposta = self.client.get(reverse("contratos:lista"))
        for texto in (
            "Contratos",
            "Gerencie contratos, responsáveis financeiros e vencimentos",
            "Contratos ativos",
            "Próximos do vencimento",
            "Inativos",
            "Futuros",
            "Pessoa Contrato UI",
            "30 dias",
        ):
            self.assertContains(resposta, texto)

    def test_detalhes_integrados_em_apartamento_e_pessoa(self):
        resposta = self.client.get(reverse(
            "apartamentos:detalhes", args=[self.apartamento.id]
        ))
        self.assertContains(resposta, "Contrato")
        self.assertContains(resposta, "Pessoa Contrato UI")
        resposta = self.client.get(reverse(
            "pessoas:detalhes", args=[self.pessoa.id]
        ))
        self.assertContains(resposta, "Contratos")
        self.assertContains(resposta, "UI-301")

    def test_view_rescisao_exige_proprietario(self):
        resposta = self.client.post(
            reverse("contratos:rescindir", args=[self.contrato.id]),
            {
                "data_rescisao": self.hoje.isoformat(),
                "justificativa": "Rescisão autorizada.",
            },
        )
        self.assertRedirects(
            resposta,
            reverse("contratos:detalhes", args=[self.contrato.id]),
        )
        self.contrato.refresh_from_db()
        self.assertEqual(
            self.contrato.situacao, Contrato.Situacao.RESCINDIDO
        )

    def _usuario_no_papel(self, papel, nome):
        usuario = get_user_model().objects.create_user(
            username=nome, password="senha"
        )
        VinculoUsuarioCondominio.objects.create(
            usuario=usuario,
            condominio=self.condominio,
            papel=papel,
        )
        return usuario

    def test_botao_somente_para_proprietario_e_contrato_apto(self):
        url = reverse("contratos:detalhes", args=[self.contrato.id])
        self.assertContains(self.client.get(url), "Rescindir contrato")
        for papel in (
            VinculoUsuarioCondominio.Papel.ADMINISTRADOR,
            VinculoUsuarioCondominio.Papel.OPERADOR,
            VinculoUsuarioCondominio.Papel.CONSULTA,
        ):
            with self.subTest(papel=papel):
                usuario = self._usuario_no_papel(papel, f"teste-{papel}")
                self.client.force_login(usuario)
                self.assertNotContains(
                    self.client.get(url), "Rescindir contrato"
                )
                self.assertEqual(
                    self.client.get(reverse(
                        "contratos:rescindir", args=[self.contrato.id]
                    )).status_code,
                    403,
                )

    def test_confirmacao_exibe_dados_e_rejeita_justificativa_vazia(self):
        url = reverse("contratos:rescindir", args=[self.contrato.id])
        resposta = self.client.get(url)
        for texto in (
            "Apartamento", "UI-301", "Bloco", self.condominio.nome,
            "Pessoa contratante", "Responsável financeiro",
            "Início do contrato", "Término previsto", "Situação atual",
            "Confirmar rescisão", "Cancelar",
        ):
            self.assertContains(resposta, texto)
        for justificativa in ("", "   "):
            with self.subTest(justificativa=repr(justificativa)):
                resposta = self.client.post(url, {
                    "data_rescisao": self.hoje.isoformat(),
                    "justificativa": justificativa,
                })
                self.assertEqual(resposta.status_code, 200)
                self.assertContains(resposta, "Informe a justificativa")
        self.contrato.refresh_from_db()
        self.assertIsNone(self.contrato.data_rescisao)

    def test_pos_rescisao_exibe_dados_historicos_e_integracoes(self):
        rescindir_contrato(
            self.contrato.id,
            condominio=self.condominio,
            usuario=self.usuario,
            justificativa="Entrega das chaves.",
        )
        detalhes = self.client.get(reverse(
            "contratos:detalhes", args=[self.contrato.id]
        ))
        self.assertContains(detalhes, "Dados da rescisão")
        self.assertContains(detalhes, "Entrega das chaves.")
        self.assertContains(detalhes, "Rescindido")
        self.assertNotContains(detalhes, "Rescindir contrato")
        self.assertNotContains(detalhes, "Editar contrato")

        inativos = self.client.get(
            reverse("contratos:lista"), {"aba": "inativos"}
        )
        self.assertContains(inativos, "Rescindido")
        proximos = self.client.get(
            reverse("contratos:lista"), {"aba": "proximos"}
        )
        self.assertNotContains(proximos, "Pessoa Contrato UI")
        apartamento = self.client.get(reverse(
            "apartamentos:detalhes", args=[self.apartamento.id]
        ))
        self.assertContains(
            apartamento, "Nenhum contrato ativo para este apartamento"
        )
        historico = self.client.get(reverse(
            "contratos:historico_apartamento", args=[self.apartamento.id]
        ))
        self.assertContains(historico, "Rescindido")
        pessoa = self.client.get(reverse(
            "pessoas:detalhes", args=[self.pessoa.id]
        ))
        self.assertContains(pessoa, "Rescindido")

    def test_encerrado_nao_exibe_botao_nem_abre_confirmacao(self):
        self.contrato.data_termino = self.hoje - timedelta(days=1)
        self.contrato.data_inicio = self.hoje - timedelta(days=10)
        self.contrato.situacao = Contrato.Situacao.ENCERRADO
        self.contrato.save(update_fields=[
            "data_inicio", "data_termino", "situacao"
        ])
        detalhes = self.client.get(reverse(
            "contratos:detalhes", args=[self.contrato.id]
        ))
        self.assertNotContains(detalhes, "Rescindir contrato")
        self.assertEqual(self.client.get(reverse(
            "contratos:rescindir", args=[self.contrato.id]
        )).status_code, 404)

    def test_metodo_invalido_e_vinculo_inativo_sao_bloqueados(self):
        url = reverse("contratos:rescindir", args=[self.contrato.id])
        self.assertEqual(self.client.put(url).status_code, 405)
        vinculo = VinculoUsuarioCondominio.objects.get(
            usuario=self.usuario, condominio=self.condominio
        )
        vinculo.ativo = False
        vinculo.save(update_fields=["ativo"])
        resposta = self.client.get(url)
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("condominios:selecionar"), resposta.url)

    def test_url_de_outro_condominio_nao_expoe_contrato(self):
        outro = Condominio.objects.create(nome="Condomínio isolado")
        usuario = get_user_model().objects.create_user(
            username="dono-outro-condominio", password="senha"
        )
        VinculoUsuarioCondominio.objects.create(
            usuario=usuario,
            condominio=outro,
            papel=VinculoUsuarioCondominio.Papel.PROPRIETARIO,
        )
        self.client.force_login(usuario)
        sessao = self.client.session
        sessao[CHAVE_CONDOMINIO_ATIVO] = outro.id
        sessao.save()
        self.assertEqual(self.client.get(reverse(
            "contratos:rescindir", args=[self.contrato.id]
        )).status_code, 404)
