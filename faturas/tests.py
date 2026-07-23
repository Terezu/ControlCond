from decimal import Decimal
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse

from apartamentos.models import Apartamento
from configuracoes.services import atualizar_configuracao, obter_configuracao
from leituras.models import Leitura

from .forms import (
    AlterarStatusFaturaForm,
    FiltrarFaturasForm,
    GerarFaturaForm,
)
from .models import Fatura
from .pdf import gerar_pdf_fatura, obter_leituras_fatura
from .services import (
    cadastrar_fatura,
    editar_fatura,
    gerar_fatura_mensal,
    gerar_pdf_fatura as salvar_pdf_fatura,
)


class GerarFaturaMensalTests(TestCase):
    def setUp(self):
        self.apartamento = Apartamento.objects.create(
            numero="101",
            bloco="A",
        )

    def configurar_leituras_base(
        self,
        agua=Decimal("0.00"),
        gas=Decimal("0.00"),
    ):
        self.apartamento.leitura_base_agua = agua
        self.apartamento.leitura_base_gas = gas
        self.apartamento.save(
            update_fields=[
                "leitura_base_agua",
                "leitura_base_gas",
            ]
        )

    def criar_leitura(
        self,
        mes,
        ano,
        leitura_agua,
        leitura_gas,
    ):
        return Leitura.objects.create(
            apartamento=self.apartamento,
            mes=mes,
            ano=ano,
            leitura_agua=leitura_agua,
            leitura_gas=leitura_gas,
        )

    def test_gera_fatura_usando_leitura_anterior(self):
        self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=Decimal("100.50"),
            leitura_gas=Decimal("20.25"),
        )

        leitura_atual = self.criar_leitura(
            mes=2,
            ano=2026,
            leitura_agua=Decimal("108.20"),
            leitura_gas=Decimal("23.99"),
        )

        fatura = gerar_fatura_mensal(leitura_atual.id)

        # Água: 108,20 - 100,50 = 7,70
        # Gás: 23,99 - 20,25 = 3,74
        # As casas decimais do consumo são descartadas.
        self.assertEqual(fatura.consumo_agua, 7)
        self.assertEqual(fatura.consumo_gas, 3)

        self.assertEqual(
            fatura.valor_agua,
            Decimal("108.21"),
        )
        self.assertEqual(
            fatura.valor_gas,
            Decimal("63.06"),
        )
        self.assertEqual(
            fatura.valor_total,
            Decimal("171.27"),
        )

    def test_usa_a_leitura_anterior_mais_recente(self):
        self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=Decimal("100.00"),
            leitura_gas=Decimal("20.00"),
        )

        self.criar_leitura(
            mes=2,
            ano=2026,
            leitura_agua=Decimal("105.00"),
            leitura_gas=Decimal("22.00"),
        )

        leitura_atual = self.criar_leitura(
            mes=3,
            ano=2026,
            leitura_agua=Decimal("111.90"),
            leitura_gas=Decimal("25.80"),
        )

        fatura = gerar_fatura_mensal(leitura_atual.id)

        # Deve comparar março com fevereiro, não com janeiro.
        self.assertEqual(fatura.consumo_agua, 6)
        self.assertEqual(fatura.consumo_gas, 3)

    def test_ignora_leituras_futuras_ao_buscar_anterior(self):
        self.configurar_leituras_base(
            agua=Decimal("100.00"),
            gas=Decimal("20.00"),
        )

        leitura_atual = self.criar_leitura(
            mes=6,
            ano=2026,
            leitura_agua=Decimal("108.00"),
            leitura_gas=Decimal("23.00"),
        )

        self.criar_leitura(
            mes=7,
            ano=2026,
            leitura_agua=Decimal("115.00"),
            leitura_gas=Decimal("27.00"),
        )

        fatura = gerar_fatura_mensal(leitura_atual.id)

        # Deve ignorar julho e comparar junho com as leituras-base.
        self.assertEqual(fatura.consumo_agua, 8)
        self.assertEqual(fatura.consumo_gas, 3)

    def test_impede_gerar_fatura_duplicada(self):
        self.configurar_leituras_base(
            agua=Decimal("95.00"),
            gas=Decimal("18.00"),
        )

        leitura = self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=Decimal("100.00"),
            leitura_gas=Decimal("20.00"),
        )

        gerar_fatura_mensal(leitura.id)

        with self.assertRaisesMessage(
            ValueError,
            "Já existe uma fatura para este apartamento neste mês e ano.",
        ):
            gerar_fatura_mensal(leitura.id)

        self.assertEqual(Fatura.objects.count(), 1)

    def test_impede_fatura_sem_leitura_de_agua(self):
        leitura = self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=None,
            leitura_gas=Decimal("20.00"),
        )

        with self.assertRaisesMessage(
            ValueError,
            "A leitura precisa possuir valores de água e gás",
        ):
            gerar_fatura_mensal(leitura.id)

        self.assertEqual(Fatura.objects.count(), 0)

    def test_impede_fatura_sem_leitura_de_gas(self):
        leitura = self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=Decimal("100.00"),
            leitura_gas=None,
        )

        with self.assertRaisesMessage(
            ValueError,
            "A leitura precisa possuir valores de água e gás",
        ):
            gerar_fatura_mensal(leitura.id)

        self.assertEqual(Fatura.objects.count(), 0)

    def test_fatura_e_criada_com_status_pendente(self):
        self.configurar_leituras_base(
            agua=Decimal("95.00"),
            gas=Decimal("18.00"),
        )

        leitura = self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=Decimal("100.00"),
            leitura_gas=Decimal("20.00"),
        )

        fatura = gerar_fatura_mensal(leitura.id)

        self.assertEqual(
            fatura.status,
            Fatura.Status.PENDENTE,
        )

    def test_fatura_copia_aluguel_do_apartamento(self):
        self.apartamento.valor_aluguel = Decimal("1200.00")
        self.apartamento.save(update_fields=["valor_aluguel"])
        self.configurar_leituras_base()
        leitura = self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=Decimal("1.00"),
            leitura_gas=Decimal("1.00"),
        )

        fatura = gerar_fatura_mensal(leitura.id)

        self.assertEqual(fatura.valor_aluguel, Decimal("1200.00"))
        self.assertEqual(fatura.desconto, Decimal("0.00"))
        self.assertEqual(fatura.subtotal, Decimal("1322.93"))
        self.assertEqual(fatura.valor_total, Decimal("1322.93"))

    def test_fatura_aceita_aluguel_especifico_e_desconto(self):
        self.apartamento.valor_aluguel = Decimal("1200.00")
        self.apartamento.save(update_fields=["valor_aluguel"])
        self.configurar_leituras_base()
        leitura = self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=Decimal("10.00"),
            leitura_gas=Decimal("3.00"),
        )

        fatura = gerar_fatura_mensal(
            leitura.id,
            valor_aluguel=Decimal("1000.00"),
            desconto=Decimal("50.00"),
        )

        self.assertEqual(fatura.valor_agua, Decimal("117.66"))
        self.assertEqual(fatura.valor_gas, Decimal("63.06"))
        self.assertEqual(fatura.valor_aluguel, Decimal("1000.00"))
        self.assertEqual(fatura.subtotal, Decimal("1180.72"))
        self.assertEqual(fatura.desconto, Decimal("50.00"))
        self.assertEqual(fatura.valor_total, Decimal("1130.72"))

    def test_alteracao_do_apartamento_nao_muda_fatura_antiga(self):
        self.apartamento.valor_aluguel = Decimal("900.00")
        self.apartamento.save(update_fields=["valor_aluguel"])
        self.configurar_leituras_base()
        leitura = self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=Decimal("1.00"),
            leitura_gas=Decimal("1.00"),
        )
        fatura = gerar_fatura_mensal(leitura.id)

        self.apartamento.valor_aluguel = Decimal("1500.00")
        self.apartamento.save(update_fields=["valor_aluguel"])
        fatura.refresh_from_db()

        self.assertEqual(fatura.valor_aluguel, Decimal("900.00"))

    def test_rejeita_desconto_negativo_ou_superior_ao_subtotal(self):
        self.configurar_leituras_base()
        leitura = self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=Decimal("1.00"),
            leitura_gas=Decimal("1.00"),
        )

        with self.assertRaisesRegex(ValueError, "desconto"):
            gerar_fatura_mensal(
                leitura.id,
                desconto=Decimal("-0.01"),
            )
        with self.assertRaisesRegex(ValueError, "subtotal"):
            gerar_fatura_mensal(
                leitura.id,
                desconto=Decimal("999.00"),
            )

    def test_edicao_financeira_recalcula_sem_alterar_consumos(self):
        self.configurar_leituras_base()
        leitura = self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=Decimal("1.00"),
            leitura_gas=Decimal("1.00"),
        )
        fatura = gerar_fatura_mensal(leitura.id)
        consumos = (fatura.consumo_agua, fatura.consumo_gas)

        editar_fatura(
            fatura.id,
            valor_aluguel=Decimal("500.00"),
            desconto=Decimal("25.00"),
        )
        fatura.refresh_from_db()

        self.assertEqual(
            (fatura.consumo_agua, fatura.consumo_gas),
            consumos,
        )
        self.assertEqual(fatura.subtotal, Decimal("622.93"))
        self.assertEqual(fatura.valor_total, Decimal("597.93"))

    def test_tarifa_configurada_do_gas_e_usada_e_fica_registrada(self):
        atualizar_configuracao(
            {"valor_m3_gas": Decimal("30.00")}
        )
        self.configurar_leituras_base()
        leitura = self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=Decimal("1.00"),
            leitura_gas=Decimal("2.00"),
        )

        fatura = gerar_fatura_mensal(leitura.id)

        self.assertEqual(fatura.valor_gas, Decimal("60.00"))
        self.assertEqual(
            fatura.valor_m3_gas_emissao,
            Decimal("30.00"),
        )

    def test_alterar_tarifa_afeta_apenas_novas_faturas(self):
        self.configurar_leituras_base()
        leitura_janeiro = self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=Decimal("1.00"),
            leitura_gas=Decimal("1.00"),
        )
        fatura_janeiro = gerar_fatura_mensal(leitura_janeiro.id)

        atualizar_configuracao(
            {"valor_m3_gas": Decimal("25.00")}
        )
        leitura_fevereiro = self.criar_leitura(
            mes=2,
            ano=2026,
            leitura_agua=Decimal("2.00"),
            leitura_gas=Decimal("2.00"),
        )
        fatura_fevereiro = gerar_fatura_mensal(leitura_fevereiro.id)
        fatura_janeiro.refresh_from_db()

        self.assertEqual(fatura_janeiro.valor_gas, Decimal("21.02"))
        self.assertEqual(
            fatura_janeiro.valor_m3_gas_emissao,
            Decimal("21.02"),
        )
        self.assertEqual(fatura_fevereiro.valor_gas, Decimal("25.00"))
        self.assertEqual(
            fatura_fevereiro.valor_m3_gas_emissao,
            Decimal("25.00"),
        )

    def test_primeira_fatura_usa_leitura_base_do_apartamento(self):
        self.configurar_leituras_base(
            agua=Decimal("100.50"),
            gas=Decimal("20.25"),
        )

        leitura = self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=Decimal("108.20"),
            leitura_gas=Decimal("23.99"),
        )

        fatura = gerar_fatura_mensal(leitura.id)

        self.assertEqual(fatura.consumo_agua, 7)
        self.assertEqual(fatura.consumo_gas, 3)

        self.assertEqual(
            fatura.valor_agua,
            Decimal("108.21"),
        )
        self.assertEqual(
            fatura.valor_gas,
            Decimal("63.06"),
        )
        self.assertEqual(
            fatura.valor_total,
            Decimal("171.27"),
        )

    def test_primeira_fatura_pode_usar_leituras_base_zero(self):
        self.configurar_leituras_base()

        leitura = self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=Decimal("7.80"),
            leitura_gas=Decimal("3.40"),
        )

        fatura = gerar_fatura_mensal(leitura.id)

        self.assertEqual(fatura.consumo_agua, 7)
        self.assertEqual(fatura.consumo_gas, 3)

        self.assertEqual(
            fatura.valor_agua,
            Decimal("108.21"),
        )
        self.assertEqual(
            fatura.valor_gas,
            Decimal("63.06"),
        )
        self.assertEqual(
            fatura.valor_total,
            Decimal("171.27"),
        )

    def test_impede_primeira_fatura_sem_leituras_base(self):
        leitura = self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=Decimal("108.20"),
            leitura_gas=Decimal("23.99"),
        )

        with self.assertRaisesMessage(
            ValueError,
            "O apartamento não possui leituras-base configuradas.",
        ):
            gerar_fatura_mensal(leitura.id)

        self.assertEqual(Fatura.objects.count(), 0)

    def test_busca_ultima_medicao_de_cada_recurso_separadamente(self):
        self.configurar_leituras_base(
            agua=Decimal("90.00"),
            gas=Decimal("10.00"),
        )
        self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=Decimal("100.00"),
            leitura_gas=Decimal("20.00"),
        )
        self.criar_leitura(
            mes=2,
            ano=2026,
            leitura_agua=Decimal("105.00"),
            leitura_gas=None,
        )
        leitura_atual = self.criar_leitura(
            mes=3,
            ano=2026,
            leitura_agua=Decimal("111.00"),
            leitura_gas=Decimal("23.00"),
        )

        fatura = gerar_fatura_mensal(leitura_atual.id)

        self.assertEqual(fatura.consumo_agua, 6)
        self.assertEqual(fatura.consumo_gas, 3)
        self.assertEqual(fatura.leitura_agua_anterior, Decimal("105.00"))
        self.assertEqual(fatura.leitura_gas_anterior, Decimal("20.00"))

    def test_fatura_rejeita_leitura_de_outro_apartamento_ou_periodo(self):
        outro = Apartamento.objects.create(
            numero="202",
            leitura_base_agua=Decimal("0.00"),
            leitura_base_gas=Decimal("0.00"),
        )
        leitura = self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=Decimal("1.00"),
            leitura_gas=Decimal("1.00"),
        )

        with self.assertRaisesMessage(
            ValueError,
            "A leitura deve pertencer ao mesmo apartamento, mês e ano da fatura.",
        ):
            cadastrar_fatura(
                apartamento_id=outro.id,
                leitura_id=leitura.id,
                mes=2,
                ano=2026,
                consumo_agua=0,
                consumo_gas=0,
            )

        self.assertEqual(Fatura.objects.count(), 0)

    def test_dados_de_emissao_nao_mudam_com_correcoes_posteriores(self):
        self.configurar_leituras_base(
            agua=Decimal("100.00"),
            gas=Decimal("20.00"),
        )
        leitura = self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=Decimal("108.00"),
            leitura_gas=Decimal("23.00"),
        )
        fatura = gerar_fatura_mensal(leitura.id)

        leitura.leitura_agua = Decimal("109.00")
        leitura.leitura_gas = Decimal("24.00")
        leitura.save(update_fields=["leitura_agua", "leitura_gas"])
        self.apartamento.numero = "101-CORRIGIDO"
        self.apartamento.leitura_base_agua = Decimal("99.00")
        self.apartamento.save(
            update_fields=["numero", "leitura_base_agua"]
        )
        fatura.refresh_from_db()

        dados = obter_leituras_fatura(fatura)
        self.assertEqual(dados["agua_anterior"], Decimal("100.00"))
        self.assertEqual(dados["agua_atual"], Decimal("108.00"))
        self.assertEqual(dados["gas_anterior"], Decimal("20.00"))
        self.assertEqual(dados["gas_atual"], Decimal("23.00"))
        self.assertEqual(fatura.apartamento_numero_emissao, "101")

    def test_leitura_vinculada_a_fatura_nao_pode_ser_excluida(self):
        self.configurar_leituras_base()
        leitura = self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=Decimal("1.00"),
            leitura_gas=Decimal("1.00"),
        )
        gerar_fatura_mensal(leitura.id)

        with self.assertRaises(ProtectedError):
            leitura.delete()

        self.assertTrue(Leitura.objects.filter(pk=leitura.pk).exists())

    def test_cadastro_rejeita_booleano_como_consumo(self):
        with self.assertRaisesRegex(ValueError, "consumo de água"):
            cadastrar_fatura(
                apartamento_id=self.apartamento.id,
                mes=1,
                ano=2026,
                consumo_agua=True,
                consumo_gas=0,
            )

    def test_cadastro_rejeita_ano_fora_do_intervalo_de_datas(self):
        with self.assertRaisesRegex(ValueError, "ano válido"):
            cadastrar_fatura(
                apartamento_id=self.apartamento.id,
                mes=1,
                ano=10000,
                consumo_agua=0,
                consumo_gas=0,
            )

    def test_cadastro_rejeita_dados_divergentes_da_leitura_vinculada(self):
        self.configurar_leituras_base()
        leitura = self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=Decimal("1.00"),
            leitura_gas=Decimal("1.00"),
        )

        with self.assertRaisesRegex(ValueError, "não correspondem"):
            cadastrar_fatura(
                apartamento_id=self.apartamento.id,
                leitura_id=leitura.id,
                mes=1,
                ano=2026,
                consumo_agua=999,
                consumo_gas=999,
                valor_agua=Decimal("1.00"),
                valor_gas=Decimal("1.00"),
                leitura_agua_atual=Decimal("999.00"),
                leitura_gas_atual=Decimal("999.00"),
            )

        self.assertFalse(Fatura.objects.exists())

    def test_cadastro_deriva_dados_da_leitura_quando_omitidos(self):
        self.configurar_leituras_base()
        leitura = self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=Decimal("1.00"),
            leitura_gas=Decimal("1.00"),
        )

        fatura = cadastrar_fatura(
            apartamento_id=self.apartamento.id,
            leitura_id=leitura.id,
            mes=1,
            ano=2026,
        )

        self.assertEqual(fatura.consumo_agua, 1)
        self.assertEqual(fatura.consumo_gas, 1)
        self.assertEqual(fatura.valor_agua, Decimal("101.91"))
        self.assertEqual(fatura.valor_gas, Decimal("21.02"))
        self.assertEqual(fatura.leitura_agua_atual, Decimal("1.00"))

    def test_gerador_em_disco_reutiliza_o_pdf_canonico(self):
        fatura = Fatura.objects.create(
            apartamento=self.apartamento,
            mes=1,
            ano=2026,
            consumo_agua=0,
            consumo_gas=0,
            apartamento_numero_emissao=self.apartamento.numero,
        )

        with TemporaryDirectory() as pasta:
            caminho = salvar_pdf_fatura(fatura.id, pasta)
            conteudo = caminho.read_bytes()

        self.assertTrue(conteudo.startswith(b"%PDF"))

    def test_pdf_funciona_com_configuracao_incompleta_e_sem_logo(self):
        fatura = Fatura.objects.create(
            apartamento=self.apartamento,
            mes=1,
            ano=2026,
            consumo_agua=0,
            consumo_gas=0,
            apartamento_numero_emissao=self.apartamento.numero,
        )

        arquivo = gerar_pdf_fatura(
            fatura,
            configuracao=obter_configuracao(),
        )
        try:
            self.assertTrue(arquivo.read(4).startswith(b"%PDF"))
        finally:
            arquivo.close()

    def test_pdf_exibe_aluguel_subtotal_desconto_e_total_persistidos(self):
        fatura = Fatura.objects.create(
            apartamento=self.apartamento,
            mes=1,
            ano=2026,
            consumo_agua=10,
            consumo_gas=3,
            valor_agua=Decimal("117.66"),
            valor_gas=Decimal("63.06"),
            valor_aluguel=Decimal("1200.00"),
            desconto=Decimal("50.00"),
            valor_total=Decimal("1330.72"),
            apartamento_numero_emissao=self.apartamento.numero,
        )

        with patch("faturas.pdf.canvas.Canvas") as canvas_mock:
            pdf_mock = canvas_mock.return_value
            pdf_mock.stringWidth.return_value = 0
            gerar_pdf_fatura(
                fatura,
                configuracao=obter_configuracao(),
            )

        textos = [
            chamada.args[2]
            for chamada in (
                pdf_mock.drawString.call_args_list
                + pdf_mock.drawRightString.call_args_list
            )
        ]
        conteudo = " ".join(textos)
        for esperado in (
            "R$ 117,66",
            "R$ 63,06",
            "R$ 1.200,00",
            "R$ 1.380,72",
            "- R$ 50,00",
            "R$ 1.330,72",
        ):
            with self.subTest(esperado=esperado):
                self.assertIn(esperado, conteudo)

    def test_pdf_usa_dados_configurados(self):
        configuracao = atualizar_configuracao(
            {
                "nome": "Condomínio Teste",
                "cnpj": "04.252.011/0001-10",
                "endereco": "Rua Principal, 100",
                "cep": "80000-000",
                "cidade": "Curitiba",
                "estado": "PR",
                "telefone": "(41) 3333-3333",
                "email": "condominio@example.com",
                "administradora_nome": "Administradora Teste",
                "administradora_responsavel": "Maria",
                "administradora_telefone": "(41) 99999-9999",
                "administradora_email": "admin@example.com",
                "observacoes_padrao": "Pague até o vencimento.",
                "texto_rodape": "Documento do condomínio.",
                "valor_m3_gas": Decimal("21.02"),
            }
        )
        fatura = Fatura.objects.create(
            apartamento=self.apartamento,
            mes=1,
            ano=2026,
            consumo_agua=0,
            consumo_gas=0,
            apartamento_numero_emissao=self.apartamento.numero,
        )

        with patch("faturas.pdf.canvas.Canvas") as canvas_mock:
            pdf_mock = canvas_mock.return_value
            pdf_mock.stringWidth.return_value = 0
            gerar_pdf_fatura(fatura, configuracao=configuracao)

        textos = [
            chamada.args[2]
            for chamada in pdf_mock.drawString.call_args_list
        ]
        conteudo = " ".join(textos)
        for esperado in (
            "Condomínio Teste",
            "04.252.011/0001-10",
            "Rua Principal, 100",
            "80000-000",
            "Curitiba",
            "(41) 3333-3333",
            "condominio@example.com",
            "Administradora Teste",
            "Maria",
            "(41) 99999-9999",
            "admin@example.com",
            "Pague até o vencimento.",
            "Documento do condomínio.",
        ):
            with self.subTest(esperado=esperado):
                self.assertIn(esperado, conteudo)

    def test_pdf_ignora_logo_ausente_ou_invalida(self):
        configuracao = obter_configuracao()
        fatura = Fatura.objects.create(
            apartamento=self.apartamento,
            mes=1,
            ano=2026,
            consumo_agua=0,
            consumo_gas=0,
            apartamento_numero_emissao=self.apartamento.numero,
        )

        configuracao.logo.name = "configuracoes/logos/ausente.png"
        arquivo_sem_logo = gerar_pdf_fatura(
            fatura,
            configuracao=configuracao,
        )
        arquivo_sem_logo.close()

        with TemporaryDirectory() as pasta:
            with self.settings(MEDIA_ROOT=pasta):
                configuracao.logo.save(
                    "invalida.png",
                    ContentFile(b"isto nao e uma imagem"),
                    save=True,
                )
                arquivo_logo_invalida = gerar_pdf_fatura(
                    fatura,
                    configuracao=configuracao,
                )
                try:
                    self.assertTrue(
                        arquivo_logo_invalida.read(4).startswith(b"%PDF")
                    )
                finally:
                    arquivo_logo_invalida.close()

    def test_banco_rejeita_total_diferente_da_soma(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Fatura.objects.create(
                apartamento=self.apartamento,
                mes=1,
                ano=2026,
                consumo_agua=1,
                consumo_gas=1,
                valor_agua=Decimal("10.00"),
                valor_gas=Decimal("5.00"),
                valor_total=Decimal("99.00"),
            )

    def test_banco_rejeita_aluguel_desconto_e_subtotal_invalidos(self):
        casos = [
            {
                "valor_aluguel": Decimal("-0.01"),
                "desconto": Decimal("0.00"),
                "valor_total": Decimal("0.00"),
            },
            {
                "valor_aluguel": Decimal("0.00"),
                "desconto": Decimal("-0.01"),
                "valor_total": Decimal("0.01"),
            },
            {
                "valor_aluguel": Decimal("10.00"),
                "desconto": Decimal("10.01"),
                "valor_total": Decimal("0.00"),
            },
        ]
        for indice, valores in enumerate(casos, start=1):
            with self.subTest(valores=valores):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Fatura.objects.create(
                        apartamento=self.apartamento,
                        mes=indice,
                        ano=2026,
                        consumo_agua=0,
                        consumo_gas=0,
                        **valores,
                    )

    def test_banco_rejeita_retrato_de_leituras_incompleto_ou_regressivo(self):
        casos = [
            {
                "leitura_agua_anterior": Decimal("10.00"),
                "leitura_agua_atual": None,
            },
            {
                "leitura_gas_anterior": Decimal("10.00"),
                "leitura_gas_atual": Decimal("9.99"),
            },
        ]
        for indice, retrato in enumerate(casos, start=1):
            with self.subTest(retrato=retrato):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Fatura.objects.create(
                        apartamento=self.apartamento,
                        mes=indice,
                        ano=2026,
                        consumo_agua=0,
                        consumo_gas=0,
                        **retrato,
                    )

    def test_modelo_rejeita_consumo_e_valor_divergentes_das_leituras(self):
        fatura = Fatura(
            apartamento=self.apartamento,
            mes=1,
            ano=2026,
            consumo_agua=999,
            consumo_gas=1,
            valor_agua=Decimal("1.00"),
            valor_gas=Decimal("21.02"),
            valor_total=Decimal("22.02"),
            leitura_agua_anterior=Decimal("0.00"),
            leitura_agua_atual=Decimal("1.00"),
            leitura_gas_anterior=Decimal("0.00"),
            leitura_gas_atual=Decimal("1.00"),
        )

        with self.assertRaises(ValidationError) as contexto:
            fatura.full_clean()

        self.assertIn("consumo_agua", contexto.exception.message_dict)
        self.assertIn("valor_agua", contexto.exception.message_dict)

    def test_formulario_exibe_apenas_leituras_aptas_a_faturamento(self):
        incompleta = self.criar_leitura(
            mes=1,
            ano=2026,
            leitura_agua=Decimal("1.00"),
            leitura_gas=None,
        )
        ja_faturada = self.criar_leitura(
            mes=2,
            ano=2026,
            leitura_agua=Decimal("2.00"),
            leitura_gas=Decimal("2.00"),
        )
        Fatura.objects.create(
            apartamento=self.apartamento,
            mes=2,
            ano=2026,
            consumo_agua=0,
            consumo_gas=0,
        )
        elegivel = self.criar_leitura(
            mes=3,
            ano=2026,
            leitura_agua=Decimal("3.00"),
            leitura_gas=Decimal("3.00"),
        )

        ids = set(
            GerarFaturaForm()
            .fields["leitura"]
            .queryset
            .values_list("id", flat=True)
        )

        self.assertIn(elegivel.id, ids)
        self.assertNotIn(incompleta.id, ids)
        self.assertNotIn(ja_faturada.id, ids)


class FaturaFormPresentationTests(TestCase):
    def test_widgets_preservam_restricoes_e_recebem_estilo_bootstrap(self):
        filtros = FiltrarFaturasForm()
        geracao = GerarFaturaForm()
        status = AlterarStatusFaturaForm()

        self.assertEqual(filtros.fields["ano"].widget.attrs["min"], 2000)
        self.assertEqual(filtros.fields["ano"].widget.attrs["max"], 9999)
        self.assertEqual(
            filtros.fields["apartamento"].widget.attrs["class"],
            "form-select",
        )
        self.assertEqual(
            geracao.fields["leitura"].widget.attrs["class"],
            "form-select",
        )
        self.assertEqual(
            status.fields["status"].widget.attrs["class"],
            "form-select",
        )

    def test_desconto_vazio_e_normalizado_para_zero(self):
        apartamento = Apartamento.objects.create(numero="101")
        leitura = Leitura.objects.create(
            apartamento=apartamento,
            mes=1,
            ano=2026,
            leitura_agua=Decimal("1.00"),
            leitura_gas=Decimal("1.00"),
        )
        form = GerarFaturaForm(
            {
                "leitura": leitura.id,
                "valor_aluguel": "",
                "desconto": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data["valor_aluguel"])
        self.assertEqual(form.cleaned_data["desconto"], Decimal("0.00"))


class FaturaPresentationTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="operador-faturas",
            password="senha-de-teste",
            is_staff=True,
        )
        self.client.force_login(usuario)

    @patch("faturas.views.listar_faturas", return_value=[])
    def test_lista_usa_layout_padrao_e_exibe_estado_vazio(self, _listar):
        resposta = self.client.get(reverse("faturas:lista"))

        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, "faturas/lista.html")
        self.assertTemplateUsed(resposta, "base.html")
        self.assertContains(resposta, "Nenhuma fatura encontrada")
        self.assertContains(resposta, reverse("faturas:gerar"))

    @patch("faturas.views.listar_faturas")
    def test_lista_exibe_fatura_e_acoes_validas(self, listar):
        listar.return_value = [
            SimpleNamespace(
                id=7,
                apartamento_numero_emissao="101",
                apartamento_bloco_emissao="A",
                mes=7,
                ano=2026,
                valor_total=Decimal("144.03"),
                status="paga",
                get_status_display=lambda: "Paga",
            )
        ]

        resposta = self.client.get(reverse("faturas:lista"))

        self.assertContains(resposta, "Apartamento 101")
        self.assertContains(resposta, "07/2026")
        self.assertContains(resposta, reverse("faturas:detalhes", args=[7]))
        self.assertContains(resposta, reverse("faturas:pdf", args=[7]))

    def test_geracao_usa_formulario_padrao_e_mantem_cancelamento(self):
        resposta = self.client.get(reverse("faturas:gerar"))

        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, "faturas/gerar.html")
        self.assertTemplateUsed(resposta, "components/form_field.html")
        self.assertContains(resposta, "Gerar fatura")
        self.assertContains(resposta, "Valor do aluguel")
        self.assertContains(resposta, "Desconto")
        self.assertContains(resposta, "faturas/js/gerar_fatura.js")
        self.assertContains(resposta, reverse("faturas:lista"))

    def test_endpoint_retorna_aluguel_da_unidade(self):
        apartamento = Apartamento.objects.create(
            numero="303",
            valor_aluguel=Decimal("1250.50"),
        )
        leitura = Leitura.objects.create(
            apartamento=apartamento,
            mes=1,
            ano=2026,
            leitura_agua=Decimal("1.00"),
            leitura_gas=Decimal("1.00"),
        )

        resposta = self.client.get(
            reverse("faturas:valor_aluguel_leitura"),
            {"leitura": leitura.id},
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(
            resposta.json()["valor_aluguel"],
            "1250.50",
        )

    def test_edicao_financeira_atualiza_total(self):
        apartamento = Apartamento.objects.create(numero="404")
        fatura = Fatura.objects.create(
            apartamento=apartamento,
            mes=1,
            ano=2026,
            consumo_agua=0,
            consumo_gas=0,
            valor_agua=Decimal("100.00"),
            valor_gas=Decimal("50.00"),
            valor_total=Decimal("150.00"),
        )

        resposta = self.client.post(
            reverse("faturas:alterar_valores", args=[fatura.id]),
            {
                "valor_aluguel": "1000.00",
                "desconto": "50.00",
            },
        )

        self.assertRedirects(
            resposta,
            reverse("faturas:detalhes", args=[fatura.id]),
        )
        fatura.refresh_from_db()
        self.assertEqual(fatura.valor_aluguel, Decimal("1000.00"))
        self.assertEqual(fatura.desconto, Decimal("50.00"))
        self.assertEqual(fatura.valor_total, Decimal("1100.00"))

    @patch("faturas.views.consultar_fatura")
    def test_detalhes_exibe_dados_status_e_acoes(self, consultar):
        consultar.return_value = SimpleNamespace(
            id=7,
            apartamento_numero_emissao="101",
            apartamento_bloco_emissao="A",
            mes=7,
            ano=2026,
            consumo_agua=10,
            consumo_gas=4,
            valor_agua=Decimal("100.00"),
            valor_gas=Decimal("44.03"),
            valor_aluguel=Decimal("0.00"),
            desconto=Decimal("0.00"),
            subtotal=Decimal("144.03"),
            valor_total=Decimal("144.03"),
            status="paga",
            get_status_display=lambda: "Paga",
            leitura_agua_anterior=Decimal("10.00"),
            leitura_agua_atual=Decimal("20.00"),
            leitura_gas_anterior=Decimal("5.00"),
            leitura_gas_atual=Decimal("9.00"),
        )

        resposta = self.client.get(reverse("faturas:detalhes", args=[7]))

        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, "faturas/detalhes.html")
        self.assertContains(resposta, "Apartamento 101")
        self.assertContains(resposta, "Paga")
        self.assertContains(resposta, reverse("faturas:pdf", args=[7]))
        self.assertContains(resposta, reverse("faturas:alterar_status", args=[7]))
