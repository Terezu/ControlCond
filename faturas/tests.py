from decimal import Decimal
from datetime import date, timedelta
from base64 import b64decode
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse

from apartamentos.models import Apartamento
from configuracoes.services import (
    atualizar_configuracao as atualizar_configuracao_por_condominio,
    obter_configuracao as obter_configuracao_por_condominio,
)
from condominios.models import Condominio
from configuracoes.models import (
    FaixaTarifaAgua,
    TabelaTarifariaAgua,
    TarifaGas,
)
from leituras.models import Leitura

from .forms import (
    FiltrarFaturasForm,
    GerarFaturaForm,
    MotivoAlteracaoStatusForm,
    RegistrarPagamentoForm,
)
from .models import Fatura, HistoricoFinanceiroFatura
from .pdf import (
    gerar_pdf_fatura,
    gerar_pdf_fatura_bytes,
    obter_leituras_fatura,
)
from .services import (
    RegraNegocioFaturaError,
    cadastrar_fatura,
    cancelar_fatura,
    calcular_pagamento_fatura,
    editar_fatura,
    estornar_pagamento,
    executar_fechamento_mensal,
    executar_fechamento_mensal_por_condominio,
    excluir_fatura,
    gerar_fatura_mensal,
    marcar_fatura_como_paga,
    reabrir_fatura,
)


def obter_configuracao():
    return obter_configuracao_por_condominio(Condominio.objects.get())


def atualizar_configuracao(dados):
    return atualizar_configuracao_por_condominio(
        Condominio.objects.get(), dados
    )


class ComponentesFinanceirosFaturaTests(TestCase):
    def setUp(self):
        self.apartamento = Apartamento.objects.create(
            numero="FIN-1",
            valor_aluguel=Decimal("1000.00"),
            valor_condominio=Decimal("300.00"),
            valor_iptu=Decimal("100.00"),
            valor_bonificacao=Decimal("80.00"),
            dia_limite_bonificacao=10,
        )

    def criar_fatura(self, **kwargs):
        dados = {
            "apartamento_id": self.apartamento.id,
            "mes": 2,
            "ano": 2028,
            "consumo_agua": 0,
            "consumo_gas": 0,
            "valor_agua": Decimal("0.00"),
            "valor_gas": Decimal("0.00"),
        }
        dados.update(kwargs)
        return cadastrar_fatura(**dados)

    def test_gera_com_condominio_iptu_desconto_e_outros_positivo(self):
        fatura = self.criar_fatura(
            desconto=Decimal("50.00"),
            valor_outros=Decimal("80.00"),
            observacao_outros="Controle adicional do portão",
        )
        self.assertEqual(fatura.valor_total, Decimal("1430.00"))
        self.assertFalse(fatura.possui_bonificacao)
        self.assertEqual(fatura.valor_com_bonificacao, Decimal("1430.00"))

    def test_outros_negativo_reduz_total(self):
        fatura = self.criar_fatura(
            valor_outros=Decimal("-250.00"),
            observacao_outros="Reparo hidráulico pago pelo condômino",
        )
        self.assertEqual(fatura.valor_total, Decimal("1150.00"))

    def test_outros_exige_observacao_mas_zero_permite_vazio(self):
        with self.assertRaisesRegex(ValueError, "observação"):
            self.criar_fatura(valor_outros=Decimal("1.00"))
        fatura = self.criar_fatura(valor_outros=Decimal("0.00"))
        self.assertEqual(fatura.observacao_outros, "")

    def test_rejeita_componentes_nao_negativos_invalidos(self):
        for campo in (
            "valor_condominio",
            "valor_iptu",
            "valor_bonificacao",
        ):
            with self.subTest(campo=campo), self.assertRaisesRegex(
                ValueError,
                "negativo",
            ):
                self.criar_fatura(**{campo: Decimal("-0.01")})

    def test_rejeita_bonificacao_sem_dia_e_acima_do_total(self):
        self.apartamento.dia_limite_bonificacao = None
        self.apartamento.valor_bonificacao = Decimal("0.00")
        self.apartamento.save(
            update_fields=["dia_limite_bonificacao", "valor_bonificacao"]
        )
        with self.assertRaisesRegex(ValueError, "dia limite"):
            self.criar_fatura(valor_bonificacao=Decimal("10.00"))
        with self.assertRaisesRegex(ValueError, "bonificação"):
            self.criar_fatura(
                valor_bonificacao=Decimal("2000.00"),
                dia_limite_bonificacao=10,
            )

    def test_rejeita_total_normal_negativo(self):
        with self.assertRaisesRegex(ValueError, "desconto"):
            self.criar_fatura(
                valor_condominio=Decimal("0.00"),
                valor_iptu=Decimal("0.00"),
                valor_bonificacao=Decimal("0.00"),
                valor_outros=Decimal("-1001.00"),
                observacao_outros="Abatimento",
            )

    def test_pagamento_antes_no_limite_e_depois(self):
        for dia, aplicada, pago in (
            (9, True, Decimal("1320.00")),
            (10, True, Decimal("1320.00")),
            (11, False, Decimal("1400.00")),
        ):
            with self.subTest(dia=dia):
                fatura = self.criar_fatura(
                    modo_bonificacao=Fatura.OrigemBonificacao.ESPECIFICA,
                    tipo_bonificacao=Fatura.TipoBonificacao.VALOR_FIXO,
                    bonificacao_especifica=Decimal("80.00"),
                )
                marcar_fatura_como_paga(
                    fatura.id,
                    data_pagamento=date(2028, 2, dia),
                )
                fatura.refresh_from_db()
                self.assertEqual(fatura.bonificacao_aplicada, aplicada)
                self.assertEqual(fatura.valor_pago, pago)
                self.assertEqual(
                    fatura.valor_bonificacao_aplicada,
                    Decimal("80.00") if aplicada else Decimal("0.00"),
                )
                self.assertEqual(fatura.valor_original, Decimal("1400.00"))
                self.assertEqual(fatura.valor_final, pago)
                self.assertEqual(
                    fatura.dias_antecipados,
                    max(10 - dia, 0),
                )
                self.assertEqual(
                    fatura.dias_em_atraso,
                    max(dia - 10, 0),
                )
                self.assertEqual(
                    fatura.valor_multa_aplicada,
                    Decimal("0.00"),
                )
                self.assertEqual(
                    fatura.valor_juros_aplicados,
                    Decimal("0.00"),
                )
                fatura.delete()

    def test_pagamento_sem_bonificacao_usa_total(self):
        fatura = self.criar_fatura(
            valor_bonificacao=Decimal("0.00"),
            dia_limite_bonificacao=None,
        )
        marcar_fatura_como_paga(
            fatura.id,
            data_pagamento=date(2028, 2, 1),
        )
        fatura.refresh_from_db()
        self.assertFalse(fatura.bonificacao_aplicada)
        self.assertEqual(fatura.valor_pago, fatura.valor_total)

    def test_snapshot_nao_muda_e_excecao_mensal_e_editavel(self):
        fatura = self.criar_fatura(valor_condominio=Decimal("275.00"))
        self.apartamento.valor_condominio = Decimal("999.00")
        self.apartamento.save(update_fields=["valor_condominio"])
        fatura.refresh_from_db()
        self.assertEqual(fatura.valor_condominio, Decimal("275.00"))

    def test_geracao_mensal_usa_padrao_do_condominio_e_nao_do_apartamento(self):
        self.apartamento.leitura_base_agua = Decimal("0.00")
        self.apartamento.leitura_base_gas = Decimal("0.00")
        self.apartamento.save(
            update_fields=["leitura_base_agua", "leitura_base_gas"]
        )
        leitura = Leitura.objects.create(
            apartamento=self.apartamento,
            mes=1,
            ano=2028,
            leitura_agua=Decimal("1.00"),
            leitura_gas=Decimal("1.00"),
        )
        fatura = gerar_fatura_mensal(leitura.id)
        self.assertEqual(fatura.valor_condominio, Decimal("300.00"))
        self.assertEqual(fatura.valor_iptu, Decimal("100.00"))
        self.assertEqual(fatura.valor_bonificacao, Decimal("0.00"))
        self.assertEqual(
            fatura.origem_bonificacao_emissao,
            Fatura.OrigemBonificacao.NENHUMA,
        )

    def test_tarifa_de_agua_nova_nao_invalida_fatura_emitida(self):
        self.apartamento.leitura_base_agua = Decimal("0.00")
        self.apartamento.leitura_base_gas = Decimal("0.00")
        self.apartamento.save(
            update_fields=["leitura_base_agua", "leitura_base_gas"]
        )
        leitura = Leitura.objects.create(
            apartamento=self.apartamento,
            mes=1,
            ano=2028,
            leitura_agua=Decimal("1.00"),
            leitura_gas=Decimal("1.00"),
        )
        fatura = gerar_fatura_mensal(leitura.id)
        valor_agua_emitido = fatura.valor_agua
        tabela_antiga = fatura.tabela_agua_utilizada
        tabela_antiga.data_fim_vigencia = date(2028, 1, 31)
        tabela_antiga.save(update_fields=["data_fim_vigencia"])
        tabela_nova = TabelaTarifariaAgua.objects.create(
            nome="Nova tabela",
            data_inicio_vigencia=date(2028, 2, 1),
        )
        FaixaTarifaAgua.objects.create(
            tabela=tabela_nova,
            consumo_inicial=0,
            consumo_final=None,
            valor=Decimal("1.00"),
            ordem=1,
        )
        editar_fatura(fatura.id, valor_aluguel=Decimal("1100.00"))
        fatura.refresh_from_db()
        self.assertEqual(fatura.valor_agua, valor_agua_emitido)

    def test_data_limite_usa_ultimo_dia_valido(self):
        fatura = self.criar_fatura(
            valor_bonificacao=Decimal("80.00"),
            dia_limite_bonificacao=31,
        )
        self.assertEqual(fatura.data_limite_bonificacao, date(2028, 2, 29))

    def test_emissao_congela_vencimento_e_valor_original(self):
        atualizar_configuracao(
            {
                "dia_vencimento_padrao": 31,
                "percentual_bonificacao_padrao": Decimal("5.000"),
                "dias_antecedencia_bonificacao": 19,
            }
        )

        fatura = self.criar_fatura()

        self.assertEqual(fatura.data_vencimento, date(2028, 2, 29))
        self.assertEqual(fatura.data_limite_bonificacao, date(2028, 2, 10))
        self.assertEqual(fatura.valor_original, fatura.valor_total)
        atualizar_configuracao({"dia_vencimento_padrao": 5})
        fatura.refresh_from_db()
        self.assertEqual(fatura.data_vencimento, date(2028, 2, 29))

    def test_snapshots_de_pagamento_nao_podem_ser_alterados(self):
        fatura = self.criar_fatura(
            modo_bonificacao=Fatura.OrigemBonificacao.ESPECIFICA,
            tipo_bonificacao=Fatura.TipoBonificacao.VALOR_FIXO,
            bonificacao_especifica=Decimal("80.00"),
        )
        marcar_fatura_como_paga(
            fatura.id,
            data_pagamento=date(2028, 2, 9),
        )
        fatura.refresh_from_db()

        fatura.valor_final = Decimal("1.00")
        with self.assertRaisesRegex(
            ValidationError,
            "não podem ser alterados",
        ):
            fatura.save(update_fields=["valor_final"])

        fatura.refresh_from_db()
        self.assertEqual(fatura.valor_final, Decimal("1320.00"))

    def test_calcula_multa_e_juros_diarios_apos_tolerancia(self):
        atualizar_configuracao(
            {
                "dia_vencimento_padrao": 10,
                "dias_tolerancia_pagamento": 2,
                "percentual_multa_padrao": Decimal("2.000"),
                "percentual_juros_padrao": Decimal("0.100"),
                "tipo_juros": "diario",
            }
        )
        fatura = self.criar_fatura(
            valor_bonificacao=Decimal("0.00"),
            dia_limite_bonificacao=None,
        )

        marcar_fatura_como_paga(
            fatura.id,
            data_pagamento=date(2028, 2, 15),
            forma_pagamento=Fatura.FormaPagamento.PIX,
            observacoes_pagamento="Comprovante conferido.",
        )
        fatura.refresh_from_db()

        self.assertEqual(fatura.dias_em_atraso, 5)
        self.assertEqual(fatura.valor_multa_aplicada, Decimal("28.00"))
        self.assertEqual(fatura.valor_juros_aplicados, Decimal("4.20"))
        self.assertEqual(fatura.valor_final, Decimal("1432.20"))
        self.assertEqual(fatura.forma_pagamento, "pix")
        self.assertEqual(
            fatura.observacoes_pagamento,
            "Comprovante conferido.",
        )

    def test_calcula_juros_mensais_proporcionais_a_trinta_dias(self):
        atualizar_configuracao(
            {
                "dia_vencimento_padrao": 10,
                "dias_tolerancia_pagamento": 0,
                "percentual_multa_padrao": Decimal("0.000"),
                "percentual_juros_padrao": Decimal("3.000"),
                "tipo_juros": "mensal",
            }
        )
        fatura = self.criar_fatura(
            valor_bonificacao=Decimal("0.00"),
            dia_limite_bonificacao=None,
        )

        marcar_fatura_como_paga(
            fatura.id,
            data_pagamento=date(2028, 2, 25),
        )
        fatura.refresh_from_db()

        self.assertEqual(fatura.dias_em_atraso, 15)
        self.assertEqual(fatura.valor_juros_aplicados, Decimal("21.00"))
        self.assertEqual(fatura.valor_final, Decimal("1421.00"))

    def test_calcula_bonificacao_percentual_automaticamente(self):
        atualizar_configuracao(
            {
                "dia_vencimento_padrao": 10,
                "percentual_bonificacao_padrao": Decimal("5.000"),
                "dias_antecedencia_bonificacao": 5,
            }
        )
        fatura = self.criar_fatura()

        self.assertEqual(fatura.data_limite_bonificacao, date(2028, 2, 5))
        marcar_fatura_como_paga(
            fatura.id,
            data_pagamento=date(2028, 2, 5),
        )
        fatura.refresh_from_db()

        self.assertTrue(fatura.bonificacao_aplicada)
        self.assertEqual(
            fatura.valor_bonificacao_aplicada,
            Decimal("70.00"),
        )
        self.assertEqual(fatura.valor_final, Decimal("1330.00"))

    def test_bonificacao_especifica_percentual_substitui_padrao(self):
        atualizar_configuracao(
            {
                "percentual_bonificacao_padrao": Decimal("10.000"),
                "dias_antecedencia_bonificacao": 0,
            }
        )
        fatura = self.criar_fatura(
            modo_bonificacao=Fatura.OrigemBonificacao.ESPECIFICA,
            tipo_bonificacao=Fatura.TipoBonificacao.PERCENTUAL,
            bonificacao_especifica=Decimal("5.000"),
        )

        marcar_fatura_como_paga(
            fatura.id,
            data_pagamento=fatura.data_limite_bonificacao,
        )
        fatura.refresh_from_db()

        self.assertEqual(
            fatura.origem_bonificacao_emissao,
            Fatura.OrigemBonificacao.ESPECIFICA,
        )
        self.assertEqual(
            fatura.tipo_bonificacao_emissao,
            Fatura.TipoBonificacao.PERCENTUAL,
        )
        self.assertEqual(
            fatura.percentual_bonificacao_emissao,
            Decimal("5.000"),
        )
        self.assertEqual(
            fatura.valor_bonificacao_aplicada,
            Decimal("70.00"),
        )

    def test_bonificacao_especifica_fixa_e_opcao_sem_bonificacao(self):
        atualizar_configuracao(
            {"percentual_bonificacao_padrao": Decimal("10.000")}
        )
        fixa = self.criar_fatura(
            modo_bonificacao=Fatura.OrigemBonificacao.ESPECIFICA,
            tipo_bonificacao=Fatura.TipoBonificacao.VALOR_FIXO,
            bonificacao_especifica=Decimal("75.00"),
        )
        marcar_fatura_como_paga(
            fixa.id,
            data_pagamento=fixa.data_limite_bonificacao,
        )
        fixa.refresh_from_db()
        self.assertEqual(
            fixa.valor_bonificacao_aplicada,
            Decimal("75.00"),
        )
        fixa.delete()

        sem_bonificacao = self.criar_fatura(
            modo_bonificacao=Fatura.OrigemBonificacao.NENHUMA,
        )
        marcar_fatura_como_paga(
            sem_bonificacao.id,
            data_pagamento=date(2028, 2, 1),
        )
        sem_bonificacao.refresh_from_db()
        self.assertEqual(
            sem_bonificacao.origem_bonificacao_emissao,
            Fatura.OrigemBonificacao.NENHUMA,
        )
        self.assertEqual(
            sem_bonificacao.valor_bonificacao_aplicada,
            Decimal("0.00"),
        )

    def test_bonificacao_fora_do_prazo_nao_e_concedida(self):
        atualizar_configuracao(
            {
                "percentual_bonificacao_padrao": Decimal("5.000"),
                "dias_antecedencia_bonificacao": 2,
            }
        )
        fatura = self.criar_fatura()

        marcar_fatura_como_paga(
            fatura.id,
            data_pagamento=(
                fatura.data_limite_bonificacao + timedelta(days=1)
            ),
        )
        fatura.refresh_from_db()

        self.assertEqual(
            fatura.valor_bonificacao_aplicada,
            Decimal("0.00"),
        )

    def test_bonificacao_especifica_nao_pode_superar_valor_elegivel(self):
        with self.assertRaisesRegex(ValueError, "valor elegível"):
            self.criar_fatura(
                modo_bonificacao=Fatura.OrigemBonificacao.ESPECIFICA,
                tipo_bonificacao=Fatura.TipoBonificacao.VALOR_FIXO,
                bonificacao_especifica=Decimal("1400.01"),
            )

    def test_configuracao_da_bonificacao_fica_congelada_apos_pagamento(self):
        fatura = self.criar_fatura(
            modo_bonificacao=Fatura.OrigemBonificacao.ESPECIFICA,
            tipo_bonificacao=Fatura.TipoBonificacao.PERCENTUAL,
            bonificacao_especifica=Decimal("5.000"),
        )
        marcar_fatura_como_paga(
            fatura.id,
            data_pagamento=fatura.data_limite_bonificacao,
        )
        fatura.refresh_from_db()
        fatura.percentual_bonificacao_emissao = Decimal("50.000")

        with self.assertRaisesRegex(
            ValidationError,
            "não podem ser alterados",
        ):
            fatura.save(update_fields=["percentual_bonificacao_emissao"])

    def test_formato_legado_fixo_permanece_compativel(self):
        fatura = self.criar_fatura(
            valor_bonificacao=Decimal("80.00"),
            dia_limite_bonificacao=10,
        )

        self.assertEqual(
            fatura.origem_bonificacao_emissao,
            Fatura.OrigemBonificacao.ESPECIFICA,
        )
        self.assertEqual(
            fatura.tipo_bonificacao_emissao,
            Fatura.TipoBonificacao.VALOR_FIXO,
        )
        self.assertEqual(
            fatura.valor_bonificacao_fixa_emissao,
            Decimal("80.00"),
        )

    def test_bonificacao_padrao_e_isolada_entre_condominios(self):
        condominio_b = Condominio.objects.create(nome="Condomínio Bônus B")
        atualizar_configuracao_por_condominio(
            self.apartamento.condominio,
            {"percentual_bonificacao_padrao": Decimal("5.000")},
        )
        atualizar_configuracao_por_condominio(
            condominio_b,
            {"percentual_bonificacao_padrao": Decimal("12.000")},
        )
        apartamento_b = Apartamento.objects.create(
            condominio=condominio_b,
            numero="FIN-B",
        )

        fatura_a = self.criar_fatura()
        fatura_b = cadastrar_fatura(
            apartamento_id=apartamento_b.id,
            mes=2,
            ano=2028,
            consumo_agua=0,
            consumo_gas=0,
        )

        self.assertEqual(
            fatura_a.percentual_bonificacao_emissao,
            Decimal("5.000"),
        )
        self.assertEqual(
            fatura_b.percentual_bonificacao_emissao,
            Decimal("12.000"),
        )

    def test_alterar_configuracao_nao_recalcula_regras_da_fatura(self):
        atualizar_configuracao(
            {
                "percentual_multa_padrao": Decimal("2.000"),
                "percentual_juros_padrao": Decimal("0.100"),
                "tipo_juros": "diario",
            }
        )
        fatura = self.criar_fatura(
            valor_bonificacao=Decimal("0.00"),
            dia_limite_bonificacao=None,
        )
        atualizar_configuracao(
            {
                "percentual_multa_padrao": Decimal("50.000"),
                "percentual_juros_padrao": Decimal("20.000"),
                "tipo_juros": "mensal",
            }
        )

        marcar_fatura_como_paga(
            fatura.id,
            data_pagamento=date(2028, 2, 11),
        )
        fatura.refresh_from_db()

        self.assertEqual(
            fatura.percentual_multa_emissao,
            Decimal("2.000"),
        )
        self.assertEqual(
            fatura.percentual_juros_emissao,
            Decimal("0.100"),
        )
        self.assertEqual(fatura.tipo_juros_emissao, "diario")
        self.assertEqual(fatura.valor_multa_aplicada, Decimal("28.00"))
        self.assertEqual(fatura.valor_juros_aplicados, Decimal("1.40"))

    def test_formulario_pagamento_solicita_apenas_dados_operacionais(self):
        form = RegistrarPagamentoForm(
            data={
                "data_pagamento": "2028-02-10",
                "forma_pagamento": "pix",
                "observacoes_pagamento": "Pago pelo aplicativo.",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            tuple(form.fields),
            (
                "data_pagamento",
                "forma_pagamento",
                "observacoes_pagamento",
            ),
        )

    def test_previsao_e_confirmacao_usam_o_mesmo_calculo(self):
        atualizar_configuracao(
            {
                "dias_tolerancia_pagamento": 1,
                "percentual_multa_padrao": Decimal("2.000"),
                "percentual_juros_padrao": Decimal("0.100"),
                "tipo_juros": "diario",
            }
        )
        fatura = self.criar_fatura(
            valor_bonificacao=Decimal("0.00"),
            dia_limite_bonificacao=None,
        )
        previsao = calcular_pagamento_fatura(
            fatura,
            date(2028, 2, 13),
        )

        marcar_fatura_como_paga(
            fatura.id,
            data_pagamento=date(2028, 2, 13),
        )
        fatura.refresh_from_db()

        self.assertEqual(fatura.valor_multa_aplicada, previsao.multa)
        self.assertEqual(fatura.valor_juros_aplicados, previsao.juros)
        self.assertEqual(
            fatura.valor_bonificacao_aplicada,
            previsao.bonificacao,
        )
        self.assertEqual(fatura.valor_final, previsao.valor_final)


class ExclusaoFaturaTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="operador-exclusao-fatura",
            password="senha-de-teste",
            is_staff=True,
        )
        self.client.force_login(self.usuario)
        self.apartamento = Apartamento.objects.create(
            numero="701",
            leitura_base_agua=Decimal("0"),
            leitura_base_gas=Decimal("0"),
        )
        self.leitura = Leitura.objects.create(
            apartamento=self.apartamento,
            mes=7,
            ano=2026,
            leitura_agua=Decimal("10"),
            leitura_gas=Decimal("10"),
        )

    def criar_fatura(self, status=Fatura.Status.PENDENTE):
        return Fatura.objects.create(
            apartamento=self.apartamento,
            leitura=self.leitura,
            mes=7,
            ano=2026,
            consumo_agua=0,
            consumo_gas=0,
            status=status,
            apartamento_numero_emissao=self.apartamento.numero,
        )

    def test_confirmacao_nao_exclui_por_get_e_usa_mes(self):
        fatura = self.criar_fatura()
        resposta = self.client.get(
            reverse("faturas:excluir", args=[fatura.id])
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(Fatura.objects.filter(pk=fatura.id).exists())
        self.assertContains(resposta, "Fatura do mês 07/2026")
        self.assertContains(resposta, "Excluir permanentemente")
        self.assertContains(resposta, "Esta ação é irreversível")

    def test_exclui_qualquer_status_e_preserva_apartamento_e_leitura(self):
        for status in Fatura.Status.values:
            with self.subTest(status=status):
                fatura = self.criar_fatura(status)
                resposta = self.client.post(
                    reverse("faturas:excluir", args=[fatura.id]),
                    follow=True,
                )

                self.assertRedirects(resposta, reverse("faturas:lista"))
                self.assertFalse(Fatura.objects.filter(pk=fatura.id).exists())
                self.assertTrue(
                    Apartamento.objects.filter(pk=self.apartamento.id).exists()
                )
                self.assertTrue(Leitura.objects.filter(pk=self.leitura.id).exists())

    def test_apos_exclusao_permite_gerar_novamente_pelas_regras_normais(self):
        fatura = gerar_fatura_mensal(self.leitura.id)
        self.client.post(reverse("faturas:excluir", args=[fatura.id]))

        nova_fatura = gerar_fatura_mensal(self.leitura.id)

        self.assertNotEqual(nova_fatura.id, fatura.id)
        self.assertEqual(Fatura.objects.filter(mes=7, ano=2026).count(), 1)

    def test_id_inexistente_retorna_404(self):
        resposta = self.client.get(reverse("faturas:excluir", args=[999999]))
        self.assertEqual(resposta.status_code, 404)

    def test_usuario_nao_staff_nao_pode_excluir(self):
        fatura = self.criar_fatura()
        usuario = get_user_model().objects.create_user(
            username="morador-exclusao-fatura",
            password="senha-de-teste",
        )
        self.client.force_login(usuario)

        resposta = self.client.post(
            reverse("faturas:excluir", args=[fatura.id])
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(Fatura.objects.filter(pk=fatura.id).exists())

    def test_service_exclui_diretamente_sem_remover_vinculos(self):
        fatura = self.criar_fatura()

        identificacao = excluir_fatura(fatura.id)

        self.assertIn("mês 07/2026", identificacao)
        self.assertFalse(Fatura.objects.filter(pk=fatura.id).exists())
        self.assertTrue(Apartamento.objects.filter(pk=self.apartamento.id).exists())
        self.assertTrue(Leitura.objects.filter(pk=self.leitura.id).exists())


class FechamentoMensalServiceTests(TestCase):
    def criar_apartamento(self, numero, *, com_leitura=True):
        apartamento = Apartamento.objects.create(
            numero=numero,
            leitura_base_agua=Decimal("0.00"),
            leitura_base_gas=Decimal("0.00"),
        )
        if com_leitura:
            Leitura.objects.create(
                apartamento=apartamento,
                mes=7,
                ano=2026,
                leitura_agua=Decimal("1.00"),
                leitura_gas=Decimal("1.00"),
            )
        return apartamento

    def test_nenhum_apartamento_retorna_resumo_zerado(self):
        resultado = executar_fechamento_mensal(7, 2026)

        self.assertEqual(resultado.apartamentos_analisados, 0)
        self.assertEqual(resultado.faturas_geradas, 0)
        self.assertEqual(resultado.faturas_existentes, 0)
        self.assertEqual(resultado.total_sem_leitura, 0)

    def test_um_apartamento_com_leitura_gera_fatura(self):
        apartamento = self.criar_apartamento("101")

        resultado = executar_fechamento_mensal(7, 2026)

        self.assertEqual(resultado.apartamentos_analisados, 1)
        self.assertEqual(resultado.faturas_geradas, 1)
        self.assertTrue(
            Fatura.objects.filter(
                apartamento=apartamento,
                mes=7,
                ano=2026,
            ).exists()
        )

    def test_varios_apartamentos_classificam_resultado_corretamente(self):
        novo = self.criar_apartamento("101")
        existente = self.criar_apartamento("102")
        sem_leitura = self.criar_apartamento(
            "103",
            com_leitura=False,
        )
        leitura_existente = existente.leituras.get(mes=7, ano=2026)
        gerar_fatura_mensal(leitura_existente.id)

        resultado = executar_fechamento_mensal(7, 2026)

        self.assertEqual(resultado.apartamentos_analisados, 3)
        self.assertEqual(resultado.faturas_geradas, 1)
        self.assertEqual(resultado.faturas_existentes, 1)
        self.assertEqual(resultado.total_sem_leitura, 1)
        self.assertEqual(
            resultado.apartamentos_sem_leitura,
            (sem_leitura,),
        )
        self.assertTrue(novo.faturas.filter(mes=7, ano=2026).exists())

    def test_todas_existentes_nao_gera_novamente(self):
        for numero in ("101", "102"):
            apartamento = self.criar_apartamento(numero)
            leitura = apartamento.leituras.get(mes=7, ano=2026)
            gerar_fatura_mensal(leitura.id)

        resultado = executar_fechamento_mensal(7, 2026)

        self.assertEqual(resultado.faturas_geradas, 0)
        self.assertEqual(resultado.faturas_existentes, 2)
        self.assertEqual(Fatura.objects.count(), 2)

    def test_execucao_repetida_e_idempotente(self):
        self.criar_apartamento("101")
        self.criar_apartamento("102")

        primeira = executar_fechamento_mensal(7, 2026)
        segunda = executar_fechamento_mensal(7, 2026)

        self.assertEqual(primeira.faturas_geradas, 2)
        self.assertEqual(segunda.faturas_geradas, 0)
        self.assertEqual(segunda.faturas_existentes, 2)
        self.assertEqual(Fatura.objects.count(), 2)

    def test_reutiliza_service_de_geracao_individual(self):
        self.criar_apartamento("101")

        with patch(
            "faturas.services.gerar_fatura_mensal",
            wraps=gerar_fatura_mensal,
        ) as gerar:
            executar_fechamento_mensal(7, 2026)

        gerar.assert_called_once()

    def test_fechamento_por_condominio_nao_faz_consultas_por_apartamento(self):
        for numero in range(1, 7):
            self.criar_apartamento(str(numero), com_leitura=False)

        with CaptureQueriesContext(connection) as consultas:
            resultado = executar_fechamento_mensal_por_condominio(
                Condominio.objects.get(),
                7,
                2026,
            )

        sql = [consulta["sql"].lower() for consulta in consultas]
        self.assertEqual(
            sum('from "leituras"' in consulta for consulta in sql),
            1,
        )
        self.assertEqual(
            sum('from "faturas"' in consulta for consulta in sql),
            1,
        )
        self.assertEqual(resultado.total_sem_leitura, 6)

    def test_mes_e_ano_invalidos_sao_rejeitados(self):
        for mes, ano in ((0, 2026), (13, 2026), (7, 0), (7, 10000)):
            with self.subTest(mes=mes, ano=ano):
                with self.assertRaises(ValueError):
                    executar_fechamento_mensal(mes, ano)

    def test_erro_inesperado_reverte_todo_o_lote(self):
        self.criar_apartamento("101")
        self.criar_apartamento("102")
        original = gerar_fatura_mensal
        chamadas = 0

        def gerar_com_falha(leitura_id):
            nonlocal chamadas
            chamadas += 1
            if chamadas == 2:
                raise RuntimeError("falha simulada")
            return original(leitura_id)

        with patch(
            "faturas.services.gerar_fatura_mensal",
            side_effect=gerar_com_falha,
        ):
            with self.assertRaisesRegex(RuntimeError, "falha simulada"):
                executar_fechamento_mensal(7, 2026)

        self.assertFalse(Fatura.objects.exists())


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
        TarifaGas.objects.update(data_fim_vigencia=date(2025, 12, 31))
        TarifaGas.objects.create(
            nome="Tarifa 2026",
            valor_por_m3=Decimal("30.00"),
            data_inicio_vigencia=date(2026, 1, 1),
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

        TarifaGas.objects.update(data_fim_vigencia=date(2026, 1, 31))
        TarifaGas.objects.create(
            nome="Tarifa fevereiro",
            valor_por_m3=Decimal("25.00"),
            data_inicio_vigencia=date(2026, 2, 1),
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

    def test_gerador_escreve_no_destino_em_memoria(self):
        fatura = Fatura.objects.create(
            apartamento=self.apartamento,
            mes=1,
            ano=2026,
            consumo_agua=0,
            consumo_gas=0,
            apartamento_numero_emissao=self.apartamento.numero,
        )

        destino = BytesIO()
        gerar_pdf_fatura(fatura, destino)
        destino.seek(0)
        conteudo = destino.read()

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

        destino = BytesIO()
        gerar_pdf_fatura(
            fatura,
            destino,
            configuracao=obter_configuracao(),
        )
        destino.seek(0)
        self.assertTrue(destino.read(4).startswith(b"%PDF"))

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
                BytesIO(),
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

    def test_pdf_exibe_fechamento_financeiro_da_fatura_paga(self):
        fatura = Fatura.objects.create(
            apartamento=self.apartamento,
            mes=1,
            ano=2026,
            consumo_agua=0,
            consumo_gas=0,
            valor_aluguel=Decimal("1000.00"),
            valor_total=Decimal("1000.00"),
            apartamento_numero_emissao=self.apartamento.numero,
        )
        Fatura.objects.filter(pk=fatura.pk).update(
            status=Fatura.Status.PAGA,
            data_vencimento=date(2026, 1, 10),
            data_pagamento=date(2026, 1, 14),
            dias_em_atraso=4,
            valor_original=Decimal("1000.00"),
            valor_multa_aplicada=Decimal("20.00"),
            valor_juros_aplicados=Decimal("4.00"),
            valor_pago=Decimal("1024.00"),
            valor_final=Decimal("1024.00"),
            forma_pagamento=Fatura.FormaPagamento.PIX,
        )
        fatura.refresh_from_db()

        with patch("faturas.pdf.canvas.Canvas") as canvas_mock:
            pdf_mock = canvas_mock.return_value
            pdf_mock.stringWidth.return_value = 0
            gerar_pdf_fatura(
                fatura,
                BytesIO(),
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
            "VENCIMENTO",
            "10/01/2026",
            "Pagamento: 14/01/2026 · 4 dias em atraso",
            "Forma: PIX",
            "VALOR ORIGINAL",
            "R$ 1.000,00",
            "MULTA",
            "R$ 20,00",
            "JUROS",
            "R$ 4,00",
            "VALOR EFETIVAMENTE PAGO",
            "R$ 1.024,00",
        ):
            with self.subTest(esperado=esperado):
                self.assertIn(esperado, conteudo)

    def test_pdf_informa_origem_e_valor_da_bonificacao(self):
        fatura = Fatura.objects.create(
            apartamento=self.apartamento,
            mes=1,
            ano=2026,
            consumo_agua=0,
            consumo_gas=0,
            valor_aluguel=Decimal("100.00"),
            valor_total=Decimal("100.00"),
            origem_bonificacao_emissao=(
                Fatura.OrigemBonificacao.ESPECIFICA
            ),
            tipo_bonificacao_emissao=(
                Fatura.TipoBonificacao.VALOR_FIXO
            ),
            valor_bonificacao_fixa_emissao=Decimal("10.00"),
            apartamento_numero_emissao=self.apartamento.numero,
        )

        with patch("faturas.pdf.canvas.Canvas") as canvas_mock:
            pdf_mock = canvas_mock.return_value
            pdf_mock.stringWidth.return_value = 0
            gerar_pdf_fatura(
                fatura,
                BytesIO(),
                configuracao=obter_configuracao(),
            )

        textos = " ".join(
            chamada.args[2]
            for chamada in (
                pdf_mock.drawString.call_args_list
                + pdf_mock.drawRightString.call_args_list
            )
        )
        self.assertIn(
            "Bonificação Específica da fatura: R$ 10,00",
            textos,
        )
        self.assertIn("R$ 90,00", textos)

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
                "pix": "financeiro@example.com",
                "favorecido_nome": "Condomínio Teste",
                "instrucoes_pagamento": "Envie o comprovante.",
                "mensagem_cabecalho": "Cobrança mensal.",
                "texto_juridico": "Documento sem valor fiscal.",
                "cidade_assinatura": "Curitiba",
                "responsavel_emissao": "João",
                "cargo_responsavel": "Síndico",
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
            gerar_pdf_fatura(
                fatura,
                BytesIO(),
                configuracao=configuracao,
            )

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
            "financeiro@example.com",
            "Envie o comprovante.",
            "Cobrança mensal.",
            "Documento sem valor fiscal.",
            "João",
            "Síndico",
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
        destino_sem_logo = BytesIO()
        gerar_pdf_fatura(
            fatura,
            destino_sem_logo,
            configuracao=configuracao,
        )

        with TemporaryDirectory() as pasta:
            with self.settings(MEDIA_ROOT=pasta):
                configuracao.logo.save(
                    "invalida.png",
                    ContentFile(b"isto nao e uma imagem"),
                    save=True,
                )
                destino_logo_invalida = BytesIO()
                gerar_pdf_fatura(
                    fatura,
                    destino_logo_invalida,
                    configuracao=configuracao,
                )
                destino_logo_invalida.seek(0)
                self.assertTrue(
                    destino_logo_invalida.read(4).startswith(b"%PDF")
                )

    def test_pdf_usa_logo_padrao_e_logo_personalizada(self):
        configuracao = obter_configuracao()
        configuracao.logo = None
        logo_bytes = b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
            "AAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        fatura = Fatura.objects.create(
            apartamento=self.apartamento,
            mes=1,
            ano=2026,
            consumo_agua=0,
            consumo_gas=0,
            apartamento_numero_emissao=self.apartamento.numero,
        )
        with TemporaryDirectory() as pasta_base:
            Path(pasta_base, "Logo.png").write_bytes(logo_bytes)
            with (
                self.settings(BASE_DIR=Path(pasta_base)),
                patch("faturas.pdf.canvas.Canvas") as canvas_mock,
            ):
                canvas_mock.return_value.stringWidth.return_value = 0
                gerar_pdf_fatura(
                    fatura,
                    BytesIO(),
                    configuracao=configuracao,
                )
            self.assertTrue(canvas_mock.return_value.drawImage.called)

        with TemporaryDirectory() as pasta, self.settings(MEDIA_ROOT=pasta):
            configuracao.logo.save(
                "personalizada.png",
                ContentFile(logo_bytes),
                save=True,
            )
            with patch("faturas.pdf.canvas.Canvas") as canvas_custom:
                canvas_custom.return_value.stringWidth.return_value = 0
                gerar_pdf_fatura(fatura, BytesIO(), configuracao=configuracao)
            self.assertTrue(canvas_custom.return_value.drawImage.called)

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
        motivo = MotivoAlteracaoStatusForm(
            acao="estornar_pagamento"
        )

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
            motivo.fields["motivo"].widget.attrs["class"],
            "form-control",
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


class DownloadPdfFaturaTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="operador-download-pdf",
            password="senha-de-teste",
            is_staff=True,
        )
        self.client.force_login(usuario)
        apartamento = Apartamento.objects.create(
            numero="101 / Sul",
            bloco="A",
        )
        self.fatura = Fatura.objects.create(
            apartamento=apartamento,
            mes=7,
            ano=2026,
            consumo_agua=0,
            consumo_gas=0,
            valor_aluguel=Decimal("1000.00"),
            valor_total=Decimal("1000.00"),
            apartamento_numero_emissao=apartamento.numero,
            apartamento_bloco_emissao=apartamento.bloco,
        )

    def baixar(self):
        return self.client.get(
            reverse("faturas:baixar_pdf", args=[self.fatura.id])
        )

    def test_download_retorna_pdf_como_anexo_sem_criar_fatura(self):
        quantidade_antes = Fatura.objects.count()

        resposta = self.baixar()
        conteudo = b"".join(resposta.streaming_content)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["Content-Type"], "application/pdf")
        self.assertIn("attachment", resposta["Content-Disposition"])
        self.assertIn(
            "fatura-apartamento-101-sul-07-2026.pdf",
            resposta["Content-Disposition"],
        )
        self.assertTrue(conteudo.startswith(b"%PDF"))
        self.assertEqual(Fatura.objects.count(), quantidade_antes)

    def test_dois_downloads_consecutivos_funcionam(self):
        for _ in range(2):
            resposta = self.baixar()
            conteudo = b"".join(resposta.streaming_content)

            self.assertEqual(resposta.status_code, 200)
            self.assertTrue(conteudo.startswith(b"%PDF"))

        self.assertEqual(Fatura.objects.count(), 1)

    def test_fatura_inexistente_retorna_404(self):
        resposta = self.client.get(
            reverse("faturas:baixar_pdf", args=[999999])
        )

        self.assertEqual(resposta.status_code, 404)

    @patch("faturas.views.gerar_pdf_fatura_bytes")
    def test_download_usa_valores_atualizados_do_banco(self, gerar_pdf):
        self.fatura.valor_aluguel = Decimal("1250.00")
        self.fatura.valor_total = Decimal("1250.00")
        self.fatura.save(update_fields=["valor_aluguel", "valor_total"])

        def escrever_pdf(fatura):
            self.assertEqual(fatura.valor_aluguel, Decimal("1250.00"))
            self.assertEqual(fatura.valor_total, Decimal("1250.00"))
            return b"%PDF-1.4 atualizado"

        gerar_pdf.side_effect = escrever_pdf

        resposta = self.baixar()
        conteudo = b"".join(resposta.streaming_content)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(conteudo, b"%PDF-1.4 atualizado")
        gerar_pdf.assert_called_once()

    def test_helper_binario_reutiliza_gerador_de_pdf(self):
        conteudo = gerar_pdf_fatura_bytes(self.fatura)
        self.assertTrue(conteudo.startswith(b"%PDF"))


class DownloadZipFaturasMensaisTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="operador-download-zip",
            password="senha-de-teste",
            is_staff=True,
        )
        self.client.force_login(self.usuario)
        self.apartamento_a = Apartamento.objects.create(
            numero="101 / Sul",
            bloco="A/B",
        )
        self.apartamento_b = Apartamento.objects.create(numero="101 / Sul")
        self.pendente = self.criar_fatura(self.apartamento_a)
        self.paga = self.criar_fatura(
            self.apartamento_b,
            status=Fatura.Status.PAGA,
        )
        self.cancelada = self.criar_fatura(
            Apartamento.objects.create(numero="303"),
            status=Fatura.Status.CANCELADA,
        )
        self.outro_mes = self.criar_fatura(
            Apartamento.objects.create(numero="404"),
            mes=10,
        )
        self.outro_ano = self.criar_fatura(
            Apartamento.objects.create(numero="505"),
            ano=2025,
        )
        self.url = reverse(
            "faturas:baixar_faturas_mes",
            args=[2026, 11],
        )

    @staticmethod
    def criar_fatura(
        apartamento,
        *,
        mes=11,
        ano=2026,
        status=Fatura.Status.PENDENTE,
    ):
        return Fatura.objects.create(
            apartamento=apartamento,
            mes=mes,
            ano=ano,
            consumo_agua=0,
            consumo_gas=0,
            valor_aluguel=Decimal("100.00"),
            valor_total=Decimal("100.00"),
            status=status,
            apartamento_numero_emissao=apartamento.numero,
            apartamento_bloco_emissao=apartamento.bloco,
        )

    def abrir_zip(self, resposta):
        return ZipFile(BytesIO(resposta.content))

    def test_staff_baixa_zip_valido_com_pendentes_e_pagas(self):
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["Content-Type"], "application/zip")
        self.assertIn(
            'filename="faturas_2026_11.zip"',
            resposta["Content-Disposition"],
        )
        with self.abrir_zip(resposta) as arquivo:
            nomes = arquivo.namelist()
            self.assertEqual(len(nomes), 2)
            self.assertEqual(len(nomes), len(set(nomes)))
            self.assertTrue(all(nome.endswith(".pdf") for nome in nomes))
            self.assertTrue(all("/" not in nome and "\\" not in nome for nome in nomes))
            ids = {self.pendente.id, self.paga.id}
            self.assertTrue(
                all(any(f"fatura-{fatura_id}_" in nome for fatura_id in ids)
                    for nome in nomes)
            )
            for nome in nomes:
                self.assertTrue(arquivo.read(nome).startswith(b"%PDF"))

    def test_nao_inclui_cancelada_outro_mes_ou_outro_ano(self):
        resposta = self.client.get(self.url)
        with self.abrir_zip(resposta) as arquivo:
            nomes = " ".join(arquivo.namelist())
        for fatura in (self.cancelada, self.outro_mes, self.outro_ano):
            self.assertNotIn(f"fatura-{fatura.id}_", nomes)

    def test_inclui_fatura_existente_e_recem_gerada_no_fechamento(self):
        apartamentos = [
            Apartamento.objects.create(
                numero=f"LOTE-{indice}",
                leitura_base_agua=Decimal("0.00"),
                leitura_base_gas=Decimal("0.00"),
            )
            for indice in (1, 2)
        ]
        leituras = [
            Leitura.objects.create(
                apartamento=apartamento,
                mes=9,
                ano=2027,
                leitura_agua=Decimal("1.00"),
                leitura_gas=Decimal("1.00"),
            )
            for apartamento in apartamentos
        ]
        existente = gerar_fatura_mensal(leituras[0].id)
        resultado = executar_fechamento_mensal(9, 2027)
        self.assertEqual(resultado.faturas_existentes, 1)
        self.assertEqual(resultado.faturas_geradas, 1)
        gerada = Fatura.objects.get(leitura=leituras[1])

        resposta = self.client.get(
            reverse("faturas:baixar_faturas_mes", args=[2027, 9])
        )
        with self.abrir_zip(resposta) as arquivo:
            nomes = " ".join(arquivo.namelist())
        self.assertIn(f"fatura-{existente.id}_", nomes)
        self.assertIn(f"fatura-{gerada.id}_", nomes)

    def test_periodo_sem_faturas_e_periodos_invalidos_retornam_404(self):
        urls = (
            reverse("faturas:baixar_faturas_mes", args=[2026, 12]),
            reverse("faturas:baixar_faturas_mes", args=[2026, 13]),
            reverse("faturas:baixar_faturas_mes", args=[1999, 11]),
        )
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_acesso_exige_usuario_staff(self):
        self.client.logout()
        resposta_anonima = self.client.get(self.url)
        self.assertRedirects(
            resposta_anonima,
            f"/admin/login/?next={self.url}",
        )
        usuario_comum = get_user_model().objects.create_user(
            username="morador-download-zip",
            password="senha-de-teste",
        )
        self.client.force_login(usuario_comum)
        resposta_sem_permissao = self.client.get(self.url)
        self.assertEqual(resposta_sem_permissao.status_code, 302)
        self.assertIn("/admin/login/", resposta_sem_permissao.url)

    @patch(
        "faturas.views.gerar_pdf_fatura_bytes",
        side_effect=RuntimeError("falha simulada"),
    )
    def test_falha_de_pdf_interrompe_zip_com_resposta_segura(self, _gerar):
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 500)
        self.assertContains(
            resposta,
            "Não foi possível gerar o arquivo",
            status_code=500,
        )
        self.assertNotEqual(resposta["Content-Type"], "application/zip")


class RegrasStatusFaturaTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="operador-status",
            password="senha-de-teste",
            is_staff=True,
        )
        self.client.force_login(self.usuario)
        self.apartamento = Apartamento.objects.create(numero="501")

    def criar_fatura(self, status=Fatura.Status.PENDENTE, mes=1):
        return Fatura.objects.create(
            apartamento=self.apartamento,
            mes=mes,
            ano=2026,
            consumo_agua=0,
            consumo_gas=0,
            valor_aluguel=Decimal("100.00"),
            valor_total=Decimal("100.00"),
            status=status,
            apartamento_numero_emissao=self.apartamento.numero,
        )

    def test_transicoes_permitidas_registram_datas_historico_e_usuario(self):
        casos = (
            (
                marcar_fatura_como_paga,
                Fatura.Status.PAGA,
                HistoricoFinanceiroFatura.Acao.PAGAMENTO_CONFIRMADO,
                "data_pagamento",
            ),
            (
                cancelar_fatura,
                Fatura.Status.CANCELADA,
                HistoricoFinanceiroFatura.Acao.FATURA_CANCELADA,
                "data_cancelamento",
            ),
        )
        for mes, (service, novo_status, acao, campo_data) in enumerate(
            casos,
            start=1,
        ):
            with self.subTest(novo_status=novo_status):
                fatura = self.criar_fatura(mes=mes)
                quantidade_antes = Fatura.objects.count()

                atualizada, alterada = service(
                    fatura.id,
                    usuario=self.usuario,
                )

                self.assertTrue(alterada)
                self.assertEqual(atualizada.status, novo_status)
                self.assertIsNotNone(getattr(atualizada, campo_data))
                self.assertEqual(Fatura.objects.count(), quantidade_antes)
                evento = atualizada.historico_financeiro.get()
                self.assertEqual(
                    evento.status_anterior,
                    Fatura.Status.PENDENTE,
                )
                self.assertEqual(evento.novo_status, novo_status)
                self.assertEqual(evento.acao, acao)
                self.assertEqual(evento.motivo, "")
                self.assertEqual(evento.usuario, self.usuario)
                self.assertIsNotNone(evento.criado_em)
                self.assertEqual(
                    evento.valores_anteriores["status"],
                    Fatura.Status.PENDENTE,
                )
                self.assertEqual(
                    evento.valores_novos["status"],
                    novo_status,
                )

    def test_criacao_registra_usuario_e_snapshot_financeiro(self):
        fatura = cadastrar_fatura(
            apartamento_id=self.apartamento.id,
            mes=12,
            ano=2026,
            consumo_agua=0,
            consumo_gas=0,
            valor_aluguel=Decimal("100.00"),
            desconto=Decimal("10.00"),
            usuario=self.usuario,
        )

        evento = fatura.historico_financeiro.get()
        self.assertEqual(
            evento.acao,
            HistoricoFinanceiroFatura.Acao.FATURA_CRIADA,
        )
        self.assertEqual(evento.usuario, self.usuario)
        self.assertEqual(evento.valores_anteriores, {})
        self.assertEqual(evento.valores_novos["desconto"], "10.00")
        self.assertEqual(evento.valores_novos["valor_total"], "90.00")

    def test_edicao_registra_desconto_e_bonificacao_antes_e_depois(self):
        fatura = self.criar_fatura()

        editar_fatura(
            fatura.id,
            desconto=Decimal("10.00"),
            valor_bonificacao=Decimal("5.00"),
            dia_limite_bonificacao=5,
            usuario=self.usuario,
        )

        evento = fatura.historico_financeiro.get()
        self.assertEqual(
            evento.acao,
            HistoricoFinanceiroFatura.Acao.VALORES_FINANCEIROS_ALTERADOS,
        )
        self.assertEqual(evento.usuario, self.usuario)
        self.assertEqual(evento.valores_anteriores["desconto"], "0.00")
        self.assertEqual(evento.valores_novos["desconto"], "10.00")
        self.assertEqual(
            evento.valores_anteriores["valor_bonificacao"],
            "0.00",
        )
        self.assertEqual(
            evento.valores_novos["valor_bonificacao"],
            "5.00",
        )

    def test_historico_registra_criacao_alteracao_e_remocao_do_bonus(self):
        fatura = self.criar_fatura()

        editar_fatura(
            fatura.id,
            modo_bonificacao=Fatura.OrigemBonificacao.ESPECIFICA,
            tipo_bonificacao=Fatura.TipoBonificacao.PERCENTUAL,
            bonificacao_especifica=Decimal("7.500"),
            usuario=self.usuario,
        )
        editar_fatura(
            fatura.id,
            modo_bonificacao=Fatura.OrigemBonificacao.NENHUMA,
            usuario=self.usuario,
        )

        eventos = list(
            fatura.historico_financeiro.order_by("id")
        )
        self.assertEqual(len(eventos), 2)
        self.assertEqual(
            eventos[0].valores_novos["origem_bonificacao_emissao"],
            Fatura.OrigemBonificacao.ESPECIFICA,
        )
        self.assertEqual(
            eventos[1].valores_anteriores[
                "origem_bonificacao_emissao"
            ],
            Fatura.OrigemBonificacao.ESPECIFICA,
        )
        self.assertEqual(
            eventos[1].valores_novos["origem_bonificacao_emissao"],
            Fatura.OrigemBonificacao.NENHUMA,
        )
        self.assertTrue(
            all(evento.usuario == self.usuario for evento in eventos)
        )

    def test_estorno_e_reabertura_exigem_motivo_e_limpam_datas(self):
        paga = self.criar_fatura(mes=1)
        marcar_fatura_como_paga(paga.id, usuario=self.usuario)
        cancelada = self.criar_fatura(mes=2)
        cancelar_fatura(cancelada.id, usuario=self.usuario)

        casos = (
            (
                paga,
                estornar_pagamento,
                "Pagamento marcado na fatura errada.",
                HistoricoFinanceiroFatura.Acao.PAGAMENTO_ESTORNADO,
                "data_pagamento",
            ),
            (
                cancelada,
                reabrir_fatura,
                "Cancelamento lançado por engano.",
                HistoricoFinanceiroFatura.Acao.FATURA_REABERTA,
                "data_cancelamento",
            ),
        )
        for fatura, service, motivo, acao, campo_data in casos:
            with self.subTest(acao=acao):
                atualizada, alterada = service(
                    fatura.id,
                    motivo,
                    usuario=self.usuario,
                )

                self.assertTrue(alterada)
                self.assertEqual(
                    atualizada.status,
                    Fatura.Status.PENDENTE,
                )
                self.assertIsNone(getattr(atualizada, campo_data))
                if acao == HistoricoFinanceiroFatura.Acao.PAGAMENTO_ESTORNADO:
                    self.assertIsNone(atualizada.valor_final)
                    self.assertIsNone(atualizada.valor_pago)
                    self.assertEqual(atualizada.dias_em_atraso, 0)
                    self.assertEqual(atualizada.dias_antecipados, 0)
                    self.assertEqual(
                        atualizada.valor_bonificacao_aplicada,
                        Decimal("0.00"),
                    )
                evento = atualizada.historico_financeiro.first()
                self.assertEqual(evento.acao, acao)
                self.assertEqual(evento.motivo, motivo)
                self.assertEqual(evento.usuario, self.usuario)
                editar_fatura(
                    atualizada.id,
                    valor_aluguel=Decimal("150.00"),
                )
                atualizada.refresh_from_db()
                self.assertEqual(
                    atualizada.valor_aluguel,
                    Decimal("150.00"),
                )

    def test_motivo_invalido_e_bloqueado_no_service(self):
        casos = (None, "", "   ", "abc", "x" * 501)
        for mes, motivo in enumerate(casos, start=1):
            with self.subTest(motivo=motivo):
                fatura = self.criar_fatura(
                    status=Fatura.Status.PAGA,
                    mes=mes,
                )
                with self.assertRaises(RegraNegocioFaturaError):
                    estornar_pagamento(fatura.id, motivo)
                fatura.refresh_from_db()
                self.assertEqual(fatura.status, Fatura.Status.PAGA)
                self.assertFalse(fatura.historico_financeiro.exists())

    def test_transicoes_diretas_entre_encerradas_sao_bloqueadas(self):
        paga = self.criar_fatura(status=Fatura.Status.PAGA, mes=1)
        cancelada = self.criar_fatura(
            status=Fatura.Status.CANCELADA,
            mes=2,
        )

        with self.assertRaises(RegraNegocioFaturaError):
            cancelar_fatura(paga.id)
        with self.assertRaises(RegraNegocioFaturaError):
            marcar_fatura_como_paga(cancelada.id)

        self.assertFalse(HistoricoFinanceiroFatura.objects.exists())

    def test_repeticao_da_mesma_acao_nao_duplica_historico(self):
        pendente = self.criar_fatura(mes=3)
        _, alterada = estornar_pagamento(pendente.id, None)
        self.assertFalse(alterada)
        self.assertFalse(pendente.historico_financeiro.exists())

        paga = self.criar_fatura(mes=1)
        marcar_fatura_como_paga(paga.id, usuario=self.usuario)
        _, alterada = marcar_fatura_como_paga(
            paga.id,
            usuario=self.usuario,
        )
        self.assertFalse(alterada)
        self.assertEqual(paga.historico_financeiro.count(), 1)

        cancelada = self.criar_fatura(mes=2)
        cancelar_fatura(cancelada.id, usuario=self.usuario)
        _, alterada = cancelar_fatura(
            cancelada.id,
            usuario=self.usuario,
        )
        self.assertFalse(alterada)
        self.assertEqual(cancelada.historico_financeiro.count(), 1)

    def test_duas_requisicoes_iguais_criam_um_unico_historico(self):
        fatura = self.criar_fatura()
        url = reverse("faturas:marcar_como_paga", args=[fatura.id])

        dados_pagamento = {
            "data_pagamento": "2026-01-10",
            "forma_pagamento": "pix",
            "observacoes_pagamento": "",
        }
        primeira = self.client.post(url, dados_pagamento)
        segunda = self.client.post(url, dados_pagamento)

        self.assertEqual(primeira.status_code, 302)
        self.assertEqual(segunda.status_code, 302)
        self.assertEqual(fatura.historico_financeiro.count(), 1)
        self.assertEqual(Fatura.objects.count(), 1)

    def test_edicao_financeira_obedece_ao_status(self):
        pendente = self.criar_fatura(mes=1)
        editar_fatura(
            pendente.id,
            valor_aluguel=Decimal("120.00"),
            desconto=Decimal("10.00"),
        )
        pendente.refresh_from_db()
        self.assertEqual(pendente.valor_total, Decimal("110.00"))

        for mes, status in enumerate(
            (Fatura.Status.PAGA, Fatura.Status.CANCELADA),
            start=2,
        ):
            with self.subTest(status=status):
                fatura = self.criar_fatura(status=status, mes=mes)
                with self.assertRaisesRegex(
                    RegraNegocioFaturaError,
                    status,
                ):
                    editar_fatura(
                        fatura.id,
                        valor_aluguel=Decimal("999.00"),
                    )
                fatura.refresh_from_db()
                self.assertEqual(
                    fatura.valor_aluguel,
                    Decimal("100.00"),
                )

    def test_endpoints_de_acao_rejeitam_get(self):
        fatura = self.criar_fatura()
        endpoints = (
            "marcar_como_paga",
            "cancelar",
            "estornar_pagamento",
            "reabrir",
        )
        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                resposta = self.client.get(
                    reverse(f"faturas:{endpoint}", args=[fatura.id])
                )
                self.assertEqual(resposta.status_code, 405)

    def test_post_invalido_nao_altera_fatura(self):
        fatura = self.criar_fatura(status=Fatura.Status.PAGA)
        resposta = self.client.post(
            reverse("faturas:estornar_pagamento", args=[fatura.id]),
            {"motivo": "   "},
        )
        fatura.refresh_from_db()
        self.assertRedirects(
            resposta,
            reverse(
                "faturas:confirmar_estornar_pagamento",
                args=[fatura.id],
            ),
        )
        self.assertEqual(fatura.status, Fatura.Status.PAGA)
        self.assertFalse(fatura.historico_financeiro.exists())

    def test_endpoint_especifico_ignora_status_arbitrario(self):
        fatura = self.criar_fatura()
        self.client.post(
            reverse("faturas:marcar_como_paga", args=[fatura.id]),
            {
                "status": Fatura.Status.CANCELADA,
                "data_pagamento": "2026-01-10",
                "forma_pagamento": "pix",
            },
        )

        fatura.refresh_from_db()
        self.assertEqual(fatura.status, Fatura.Status.PAGA)
        self.assertEqual(
            fatura.historico_financeiro.get().novo_status,
            Fatura.Status.PAGA,
        )

    def test_confirmacao_exibe_mensagem_e_formulario_adequados(self):
        paga = self.criar_fatura(status=Fatura.Status.PAGA)
        resposta = self.client.get(
            reverse(
                "faturas:confirmar_estornar_pagamento",
                args=[paga.id],
            )
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Estornar pagamento da fatura?")
        self.assertContains(
            resposta,
            "A fatura voltará ao status pendente",
        )
        self.assertContains(resposta, 'name="motivo"')
        self.assertContains(
            resposta,
            reverse("faturas:estornar_pagamento", args=[paga.id]),
        )

        pendente = self.criar_fatura(mes=2)
        resposta_pagamento = self.client.get(
            reverse(
                "faturas:confirmar_marcar_como_paga",
                args=[pendente.id],
            )
        )
        self.assertContains(resposta_pagamento, 'name="data_pagamento"')
        self.assertContains(resposta_pagamento, 'name="forma_pagamento"')
        self.assertContains(
            resposta_pagamento,
            'name="observacoes_pagamento"',
        )
        self.assertNotContains(resposta_pagamento, 'name="valor_final"')
        for rotulo in (
            "Valor original",
            "Descontos",
            "Bonificação",
            "Multa",
            "Juros",
            "Valor final",
        ):
            with self.subTest(rotulo=rotulo):
                self.assertContains(resposta_pagamento, rotulo)

    def test_endpoint_previsao_retorna_calculo_sem_alterar_fatura(self):
        atualizar_configuracao(
            {
                "percentual_multa_padrao": Decimal("2.000"),
                "percentual_juros_padrao": Decimal("0.100"),
                "tipo_juros": "diario",
            }
        )
        fatura = self.criar_fatura()

        resposta = self.client.get(
            reverse("faturas:previsao_pagamento", args=[fatura.id]),
            {"data_pagamento": "2026-01-12"},
        )
        fatura.refresh_from_db()

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["multa"], "2.00")
        self.assertEqual(resposta.json()["juros"], "0.20")
        self.assertEqual(resposta.json()["valor_final"], "102.20")
        self.assertEqual(fatura.status, Fatura.Status.PENDENTE)
        self.assertIsNone(fatura.valor_final)

    def test_endpoints_exigem_autenticacao_de_equipe(self):
        fatura = self.criar_fatura()
        self.client.logout()
        url = reverse("faturas:marcar_como_paga", args=[fatura.id])

        resposta = self.client.post(url)

        self.assertRedirects(
            resposta,
            f"/admin/login/?next={url}",
        )

    def test_id_inexistente_retorna_404(self):
        resposta = self.client.post(
            reverse("faturas:marcar_como_paga", args=[999999])
        )
        self.assertEqual(resposta.status_code, 404)

    def test_post_financeiro_nao_edita_fatura_encerrada(self):
        for mes, status in enumerate(
            (Fatura.Status.PAGA, Fatura.Status.CANCELADA),
            start=1,
        ):
            with self.subTest(status=status):
                fatura = self.criar_fatura(status=status, mes=mes)

                resposta = self.client.post(
                    reverse(
                        "faturas:alterar_valores",
                        args=[fatura.id],
                    ),
                    {
                        "valor_aluguel": "999.00",
                        "desconto": "0.00",
                    },
                    follow=True,
                )

                fatura.refresh_from_db()
                self.assertEqual(
                    fatura.valor_aluguel,
                    Decimal("100.00"),
                )
                self.assertContains(
                    resposta,
                    (
                        "Não é possível editar valores de uma fatura "
                        f"{status}."
                    ),
                )

    def test_template_exibe_apenas_acoes_compativeis_com_status(self):
        pendente = self.criar_fatura(mes=1)
        resposta_pendente = self.client.get(
            reverse("faturas:detalhes", args=[pendente.id])
        )
        self.assertContains(resposta_pendente, "Marcar como paga")
        self.assertContains(resposta_pendente, "Cancelar fatura")
        self.assertContains(resposta_pendente, "Editar valores da fatura")

        paga = self.criar_fatura(status=Fatura.Status.PAGA, mes=2)
        resposta_paga = self.client.get(
            reverse("faturas:detalhes", args=[paga.id])
        )
        self.assertNotContains(resposta_paga, "Marcar como paga")
        self.assertNotContains(resposta_paga, "Cancelar fatura")
        self.assertContains(resposta_paga, "Estornar pagamento")
        self.assertNotContains(
            resposta_paga,
            reverse("faturas:alterar_valores", args=[paga.id]),
        )
        self.assertContains(
            resposta_paga,
            "valores financeiros estão bloqueados para edição",
        )

        cancelada = self.criar_fatura(
            status=Fatura.Status.CANCELADA,
            mes=3,
        )
        resposta_cancelada = self.client.get(
            reverse("faturas:detalhes", args=[cancelada.id])
        )
        self.assertContains(resposta_cancelada, "Reabrir fatura")
        self.assertNotContains(resposta_cancelada, "Estornar pagamento")

    def test_historico_e_motivo_aparecem_nos_detalhes(self):
        fatura = self.criar_fatura()
        marcar_fatura_como_paga(fatura.id, usuario=self.usuario)
        estornar_pagamento(
            fatura.id,
            "Pagamento lançado na unidade errada.",
            usuario=self.usuario,
        )

        resposta = self.client.get(
            reverse("faturas:detalhes", args=[fatura.id])
        )

        self.assertContains(resposta, "Histórico financeiro")
        self.assertContains(resposta, "Pagamento estornado")
        self.assertContains(
            resposta,
            "Pagamento lançado na unidade errada.",
        )
        self.assertContains(resposta, self.usuario.username)
        self.assertContains(resposta, "Valor anterior")
        self.assertContains(resposta, "Valor novo")
        self.assertContains(
            resposta,
            "Editar valores da fatura",
        )


class FaturaPresentationTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="operador-faturas",
            password="senha-de-teste",
            is_staff=True,
        )
        self.client.force_login(usuario)

    @patch("faturas.views.listar_faturas_por_condominio", return_value=[])
    def test_lista_usa_layout_padrao_e_exibe_estado_vazio(self, _listar):
        resposta = self.client.get(reverse("faturas:lista"))

        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, "faturas/lista.html")
        self.assertTemplateUsed(resposta, "base.html")
        self.assertContains(resposta, "Nenhuma fatura encontrada")
        self.assertContains(resposta, reverse("faturas:gerar"))

    @patch("faturas.views.listar_faturas_por_condominio")
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
        self.assertContains(
            resposta,
            reverse("faturas:baixar_pdf", args=[7]),
        )

    def test_tela_fechamento_mensal_usa_post_e_exibe_resumo(self):
        apartamento = Apartamento.objects.create(
            numero="601",
            leitura_base_agua=Decimal("0.00"),
            leitura_base_gas=Decimal("0.00"),
        )
        Leitura.objects.create(
            apartamento=apartamento,
            mes=7,
            ano=2026,
            leitura_agua=Decimal("1.00"),
            leitura_gas=Decimal("1.00"),
        )
        url = reverse("faturas:fechamento_mensal")

        resposta_get = self.client.get(url)
        resposta_post = self.client.post(
            url,
            {"mes": "7", "ano": "2026"},
        )

        self.assertEqual(resposta_get.status_code, 200)
        self.assertContains(resposta_get, "Fechamento Mensal")
        self.assertContains(resposta_get, "Executar fechamento")
        self.assertEqual(resposta_post.status_code, 200)
        self.assertContains(resposta_post, "Fechamento concluído")
        self.assertContains(resposta_post, "Faturas geradas")
        self.assertContains(resposta_post, ">1<", html=False)
        self.assertContains(resposta_post, "Baixar faturas do mês")
        self.assertContains(
            resposta_post,
            reverse(
                "faturas:baixar_faturas_mes",
                args=[2026, 7],
            ),
        )
        self.assertEqual(Fatura.objects.count(), 1)

    def test_fechamento_lista_apartamentos_sem_leitura(self):
        Apartamento.objects.create(numero="602")

        resposta = self.client.post(
            reverse("faturas:fechamento_mensal"),
            {"mes": "7", "ano": "2026"},
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Pendências")
        self.assertContains(resposta, "Apartamento 602")
        self.assertContains(resposta, "Total sem leitura: 1")

    def test_post_invalido_nao_executa_fechamento(self):
        Apartamento.objects.create(numero="603")

        resposta = self.client.post(
            reverse("faturas:fechamento_mensal"),
            {"mes": "99", "ano": "0"},
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Fatura.objects.exists())
        self.assertNotContains(resposta, "Fechamento concluído")

    def test_fechamento_sem_faturas_nao_exibe_botao_de_download(self):
        resposta = self.client.post(
            reverse("faturas:fechamento_mensal"),
            {"mes": "8", "ano": "2026"},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Nenhuma fatura pendente ou paga")
        self.assertNotContains(resposta, "Baixar faturas do mês")

    def test_geracao_usa_formulario_padrao_e_mantem_cancelamento(self):
        resposta = self.client.get(reverse("faturas:gerar"))

        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, "faturas/gerar.html")
        self.assertTemplateUsed(resposta, "components/form_field.html")
        self.assertContains(resposta, "Gerar fatura")
        self.assertContains(resposta, "Valor do aluguel")
        self.assertContains(resposta, "Desconto")
        self.assertContains(
            resposta,
            "Usar bonificação padrão do condomínio",
        )
        self.assertContains(resposta, "Definir bonificação específica")
        self.assertContains(resposta, "Não aplicar bonificação")
        self.assertContains(resposta, "faturas/js/gerar_fatura.js")
        self.assertContains(resposta, reverse("faturas:lista"))

    def test_geracao_por_leitura_abre_formulario_pre_preenchido(self):
        apartamento = Apartamento.objects.create(
            numero="302",
            valor_aluguel=Decimal("1250.50"),
            leitura_base_agua=Decimal("0.00"),
            leitura_base_gas=Decimal("0.00"),
        )
        leitura = Leitura.objects.create(
            apartamento=apartamento,
            mes=1,
            ano=2026,
            leitura_agua=Decimal("1.00"),
            leitura_gas=Decimal("1.00"),
        )

        resposta = self.client.get(
            reverse("faturas:gerar"),
            {"leitura": leitura.id},
        )

        self.assertEqual(resposta.status_code, 200)
        form = resposta.context["form"]
        self.assertEqual(form.initial["leitura"], leitura)
        self.assertEqual(
            form.initial["valor_aluguel"],
            Decimal("1250.50"),
        )
        self.assertEqual(form.initial["desconto"], Decimal("0.00"))
        self.assertContains(
            resposta,
            f'<option value="{leitura.id}" selected>',
            html=False,
        )

    def test_geracao_por_leitura_cria_uma_fatura_e_redireciona(self):
        apartamento = Apartamento.objects.create(
            numero="304",
            valor_aluguel=Decimal("900.00"),
            leitura_base_agua=Decimal("0.00"),
            leitura_base_gas=Decimal("0.00"),
        )
        leitura = Leitura.objects.create(
            apartamento=apartamento,
            mes=1,
            ano=2026,
            leitura_agua=Decimal("1.00"),
            leitura_gas=Decimal("1.00"),
        )

        resposta = self.client.post(
            reverse("faturas:gerar"),
            {
                "leitura": leitura.id,
                "valor_aluguel": "850.00",
                "desconto": "10.00",
            },
        )

        fatura = Fatura.objects.get(
            apartamento=apartamento,
            mes=1,
            ano=2026,
        )
        self.assertRedirects(
            resposta,
            reverse("faturas:detalhes", args=[fatura.id]),
        )
        self.assertEqual(Fatura.objects.count(), 1)
        self.assertEqual(fatura.valor_aluguel, Decimal("850.00"))
        self.assertEqual(fatura.desconto, Decimal("10.00"))

    def test_tentativa_duplicada_redireciona_para_fatura_existente(self):
        apartamento = Apartamento.objects.create(numero="305")
        leitura = Leitura.objects.create(
            apartamento=apartamento,
            mes=1,
            ano=2026,
            leitura_agua=Decimal("1.00"),
            leitura_gas=Decimal("1.00"),
        )
        fatura = Fatura.objects.create(
            apartamento=apartamento,
            leitura=leitura,
            mes=1,
            ano=2026,
            consumo_agua=0,
            consumo_gas=0,
        )

        resposta_get = self.client.get(
            reverse("faturas:gerar"),
            {"leitura": leitura.id},
        )
        resposta_post = self.client.post(
            reverse("faturas:gerar"),
            {
                "leitura": leitura.id,
                "valor_aluguel": "0.00",
                "desconto": "0.00",
            },
        )

        destino = reverse("faturas:detalhes", args=[fatura.id])
        self.assertRedirects(resposta_get, destino)
        self.assertRedirects(resposta_post, destino)
        self.assertEqual(Fatura.objects.count(), 1)

    def test_url_manual_com_leitura_inexistente_retorna_erro_amigavel(self):
        resposta = self.client.get(
            reverse("faturas:gerar"),
            {"leitura": 999999},
            follow=True,
        )

        self.assertRedirects(resposta, reverse("leituras:lista"))
        self.assertContains(resposta, "Leitura não encontrada.")

    def test_geracao_sem_leitura_anterior_exibe_orientacao(self):
        apartamento = Apartamento.objects.create(numero="306")
        leitura = Leitura.objects.create(
            apartamento=apartamento,
            mes=1,
            ano=2026,
            leitura_agua=Decimal("1.00"),
            leitura_gas=Decimal("1.00"),
        )

        resposta = self.client.post(
            reverse("faturas:gerar"),
            {
                "leitura": leitura.id,
                "valor_aluguel": "0.00",
                "desconto": "0.00",
            },
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Leituras-base necessárias")
        self.assertFalse(Fatura.objects.filter(leitura=leitura).exists())

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

    @patch("faturas.views.consultar_fatura_no_condominio")
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
            historico_financeiro=SimpleNamespace(
                select_related=lambda *args: SimpleNamespace(
                    all=lambda: []
                )
            ),
        )

        resposta = self.client.get(reverse("faturas:detalhes", args=[7]))

        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, "faturas/detalhes.html")
        self.assertContains(resposta, "Apartamento 101")
        self.assertContains(resposta, "Paga")
        self.assertContains(
            resposta,
            reverse("faturas:baixar_pdf", args=[7]),
        )
        self.assertContains(
            resposta,
            reverse(
                "faturas:confirmar_estornar_pagamento",
                args=[7],
            ),
        )
        self.assertContains(
            resposta,
            "valores financeiros estão bloqueados para edição",
        )
