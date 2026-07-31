from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from condominios.models import Condominio, VinculoUsuarioCondominio
from condominios.services import CHAVE_CONDOMINIO_ATIVO
from contratos.services import cadastrar_contrato, rescindir_contrato
from faturas.models import Fatura
from leituras.models import Leitura
from pessoas.models import VinculoPessoaApartamento
from pessoas.services import cadastrar_pessoa, criar_vinculo, encerrar_vinculo

from .models import Apartamento
from .selectors import (
    enriquecer_apartamentos,
    listar_apartamentos_operacionais,
    montar_painel_apartamento,
)


class ApartamentoOperacionalTests(TestCase):
    def setUp(self):
        self.condominio = Condominio.objects.get()
        self.usuario = get_user_model().objects.create_user(
            username="apartamento-operacional",
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
        self.client.force_login(self.usuario)
        sessao = self.client.session
        sessao[CHAVE_CONDOMINIO_ATIVO] = self.condominio.id
        sessao.save()
        self.apartamento = Apartamento.objects.create(
            condominio=self.condominio,
            numero="OP-101",
            bloco="A",
            leitura_base_agua=Decimal("10"),
            leitura_base_gas=Decimal("5"),
        )

    def pessoa(self, cpf="52998224725", nome="Pessoa Operacional"):
        return cadastrar_pessoa(
            condominio=self.condominio,
            nome_completo=nome,
            cpf=cpf,
            email=f"{cpf}@example.com",
            telefone="41999999999",
        )

    def painel(self):
        apartamento = listar_apartamentos_operacionais(
            self.condominio
        ).get(pk=self.apartamento.pk)
        return montar_painel_apartamento(apartamento)

    def test_apartamento_sem_pessoas_e_sem_responsavel(self):
        painel = self.painel()
        self.assertFalse(painel.ocupado)
        self.assertIsNone(painel.pessoa_principal)
        self.assertIsNone(painel.responsavel_financeiro)
        resposta = self.client.get(reverse(
            "apartamentos:detalhes", args=[self.apartamento.id]
        ))
        self.assertContains(
            resposta, "Nenhuma pessoa vinculada a este apartamento"
        )
        self.assertContains(resposta, "Sem responsável financeiro")

    def test_uma_pessoa_com_multiplos_vinculos_nao_e_duplicada(self):
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
        painel = self.painel()
        self.assertEqual(len(painel.pessoas), 1)
        self.assertEqual(len(painel.pessoas[0].tipos_ativos), 3)
        self.assertEqual(painel.responsavel_financeiro, pessoa)
        resposta = self.client.get(reverse(
            "apartamentos:detalhes", args=[self.apartamento.id]
        ))
        self.assertContains(resposta, pessoa.nome_completo)
        self.assertContains(resposta, "Proprietário")
        self.assertContains(resposta, "Morador")
        self.assertContains(resposta, "Responsável financeiro")

    def test_apartamento_com_uma_pessoa_e_um_vinculo(self):
        pessoa = self.pessoa()
        criar_vinculo(
            condominio=self.condominio,
            pessoa_id=pessoa.id,
            apartamento_id=self.apartamento.id,
            tipo=VinculoPessoaApartamento.Tipo.MORADOR,
            data_inicio=date(2026, 1, 1),
        )
        painel = self.painel()
        self.assertEqual(len(painel.pessoas), 1)
        self.assertEqual(painel.pessoa_principal, pessoa)
        self.assertTrue(painel.ocupado)
        self.assertIsNone(painel.responsavel_financeiro)

    def test_inquilino_com_contrato_ativo_e_prioridade_principal(self):
        pessoa = self.pessoa()
        criar_vinculo(
            condominio=self.condominio,
            pessoa_id=pessoa.id,
            apartamento_id=self.apartamento.id,
            tipo=VinculoPessoaApartamento.Tipo.INQUILINO,
            data_inicio=timezone.localdate() - timedelta(days=5),
        )
        cadastrar_contrato(
            condominio=self.condominio,
            apartamento_id=self.apartamento.id,
            pessoa_contratante_id=pessoa.id,
            responsavel_financeiro_id=pessoa.id,
            data_inicio=timezone.localdate() - timedelta(days=5),
            data_termino=timezone.localdate() + timedelta(days=30),
        )
        painel = self.painel()
        self.assertEqual(painel.pessoa_principal, pessoa)
        self.assertTrue(painel.ocupado)
        self.assertTrue(painel.contrato_atual.proximo_vencimento)
        resposta = self.client.get(reverse("apartamentos:lista"))
        self.assertContains(resposta, "Contrato próximo do vencimento")
        self.assertContains(resposta, "Ativo até")

    def test_contrato_futuro_nao_marca_unidade_como_ocupada(self):
        pessoa = self.pessoa()
        cadastrar_contrato(
            condominio=self.condominio,
            apartamento_id=self.apartamento.id,
            pessoa_contratante_id=pessoa.id,
            responsavel_financeiro_id=pessoa.id,
            data_inicio=timezone.localdate() + timedelta(days=10),
            data_termino=timezone.localdate() + timedelta(days=100),
        )
        painel = self.painel()
        self.assertFalse(painel.ocupado)
        self.assertIsNotNone(painel.contrato_futuro)
        resposta = self.client.get(reverse("apartamentos:lista"))
        self.assertContains(resposta, "Contrato futuro")
        self.assertContains(resposta, "Futuro")

    def test_preserva_historico_de_vinculo_encerrado(self):
        pessoa = self.pessoa()
        vinculo = criar_vinculo(
            condominio=self.condominio,
            pessoa_id=pessoa.id,
            apartamento_id=self.apartamento.id,
            tipo=VinculoPessoaApartamento.Tipo.PROPRIETARIO,
            data_inicio=date(2025, 1, 1),
        )
        encerrar_vinculo(
            vinculo.id,
            condominio=self.condominio,
            data_fim=date(2025, 12, 31),
        )
        painel = self.painel()
        self.assertEqual(len(painel.pessoas), 1)
        self.assertFalse(painel.pessoas[0].ativo)
        resposta = self.client.get(reverse(
            "apartamentos:detalhes", args=[self.apartamento.id]
        ))
        self.assertContains(resposta, "Histórico")

    def test_isolamento_entre_condominios(self):
        outro = Condominio.objects.create(nome="Outro Operacional")
        Apartamento.objects.create(
            condominio=outro, numero=self.apartamento.numero, bloco="A"
        )
        queryset = listar_apartamentos_operacionais(self.condominio)
        self.assertEqual(list(queryset), [self.apartamento])

    def test_listagem_e_enriquecimento_nao_geram_n_mais_um(self):
        for indice in range(5):
            Apartamento.objects.create(
                condominio=self.condominio, numero=f"OP-{indice + 200}"
            )
        with self.assertNumQueries(3):
            apartamentos = list(
                listar_apartamentos_operacionais(self.condominio)
            )
            enriquecer_apartamentos(apartamentos)
            list(apartamentos)

    def test_leituras_e_faturas_permanecem_no_detalhe(self):
        Leitura.objects.create(
            apartamento=self.apartamento,
            mes=7,
            ano=2026,
            leitura_agua=Decimal("20"),
            leitura_gas=Decimal("8"),
        )
        Fatura.objects.create(
            apartamento=self.apartamento,
            mes=7,
            ano=2026,
            consumo_agua=0,
            consumo_gas=0,
            valor_aluguel=Decimal("100"),
            valor_total=Decimal("100"),
            apartamento_numero_emissao=self.apartamento.numero,
        )
        resposta = self.client.get(reverse(
            "apartamentos:detalhes", args=[self.apartamento.id]
        ))
        self.assertContains(resposta, "07/2026")
        self.assertContains(resposta, "20")
        self.assertContains(resposta, "R$ 100,00")
        self.assertContains(resposta, "Não registrado na emissão")

    def test_acoes_exigem_usuario_staff(self):
        visitante = get_user_model().objects.create_user(
            username="visitante-operacional", password="senha"
        )
        self.client.force_login(visitante)
        resposta = self.client.get(reverse(
            "apartamentos:detalhes", args=[self.apartamento.id]
        ))
        self.assertEqual(resposta.status_code, 302)
