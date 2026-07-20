from decimal import Decimal
from tempfile import TemporaryDirectory

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from apartamentos.models import Apartamento
from leituras.models import Leitura

from .forms import GerarFaturaForm
from .models import Fatura
from .pdf import obter_leituras_fatura
from .services import (
    cadastrar_fatura,
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
