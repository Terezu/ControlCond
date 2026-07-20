from decimal import Decimal

from django.test import SimpleTestCase

from .services import (
    calcular_agua,
    calcular_consumo_agua,
    calcular_consumo_gas,
    calcular_gas,
    calcular_valor_agua,
    calcular_valor_gas,
)


class CalculosConsumoTests(SimpleTestCase):
    def test_calcular_consumo_agua(self):
        consumo = calcular_consumo_agua(
            leitura_anterior=100,
            leitura_atual=108,
        )

        self.assertEqual(consumo, 8)

    def test_calcular_consumo_gas(self):
        consumo = calcular_consumo_gas(
            leitura_anterior=20,
            leitura_atual=23,
        )

        self.assertEqual(consumo, 3)

    def test_primeira_leitura_de_agua_exige_valor_anterior(self):
        with self.assertRaisesMessage(
            ValueError,
            "Informe a leitura anterior de água, inclusive para a primeira medição",
        ):
            calcular_consumo_agua(
                leitura_anterior=None,
                leitura_atual=100,
            )

    def test_primeira_leitura_de_gas_exige_valor_anterior(self):
        with self.assertRaisesMessage(
            ValueError,
            "Informe a leitura anterior de gás, inclusive para a primeira medição",
        ):
            calcular_consumo_gas(
                leitura_anterior=None,
                leitura_atual=20,
            )

    def test_leitura_agua_menor_que_anterior_gera_erro(self):
        with self.assertRaisesMessage(
            ValueError,
            "A leitura atual de água não pode ser menor que a anterior.",
        ):
            calcular_consumo_agua(
                leitura_anterior=100,
                leitura_atual=90,
            )

    def test_leitura_gas_menor_que_anterior_gera_erro(self):
        with self.assertRaisesMessage(
            ValueError,
            "A leitura atual de gás não pode ser menor que a anterior.",
        ):
            calcular_consumo_gas(
                leitura_anterior=30,
                leitura_atual=25,
            )

    def test_rejeita_leitura_atual_ausente_ou_nao_finita(self):
        with self.assertRaisesMessage(
            ValueError,
            "Informe a leitura atual de água.",
        ):
            calcular_consumo_agua(10, None)

        for valor in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(valor=valor), self.assertRaisesRegex(
                ValueError,
                "número finito",
            ):
                calcular_consumo_agua(10, valor)


class CalculosAguaTests(SimpleTestCase):
    def test_valor_agua_para_consumo_zero(self):
        valor = calcular_valor_agua(0)

        self.assertEqual(valor, Decimal("101.91"))

    def test_valor_agua_para_consumo_dez(self):
        valor = calcular_valor_agua(10)

        self.assertEqual(valor, Decimal("117.66"))

    def test_calcula_faixas_antes_ausentes(self):
        self.assertEqual(calcular_valor_agua(14), Decimal("187.90"))
        self.assertEqual(calcular_valor_agua(16), Decimal("223.11"))

    def test_calcula_consumo_acima_de_trinta(self):
        self.assertEqual(calcular_valor_agua(31), Decimal("501.83"))

    def test_aplica_corretamente_os_limites_das_faixas(self):
        valores_esperados = {
            5: Decimal("101.91"),
            6: Decimal("105.06"),
            11: Decimal("135.22"),
            15: Decimal("205.46"),
            20: Decimal("293.71"),
            21: Decimal("311.51"),
            30: Decimal("471.71"),
        }

        for consumo, esperado in valores_esperados.items():
            with self.subTest(consumo=consumo):
                self.assertEqual(calcular_valor_agua(consumo), esperado)

    def test_calcular_agua_retorna_dados_completos(self):
        resultado = calcular_agua(
            leitura_anterior=100,
            leitura_atual=108,
        )

        self.assertEqual(resultado["leitura_anterior"], 100)
        self.assertEqual(resultado["leitura_atual"], 108)
        self.assertEqual(resultado["consumo"], 8)
        self.assertEqual(resultado["valor"], Decimal("111.36"))

    
    def test_consumo_agua_decimal_ignora_casas_decimais(self):
        consumo = calcular_consumo_agua(
            leitura_anterior=Decimal("100.80"),
            leitura_atual=Decimal("109.95"),
        )

        self.assertEqual(consumo, 9)

    def test_consumo_decimal_nao_arredonda_para_cima(self):
        consumo = calcular_consumo_agua(
            leitura_anterior=Decimal("100.00"),
            leitura_atual=Decimal("109.99"),
        )

        self.assertEqual(consumo, 9)

    def test_valor_agua_rejeita_consumo_negativo_ou_fracionado(self):
        with self.assertRaisesRegex(ValueError, "não pode ser negativo"):
            calcular_valor_agua(-1)

        with self.assertRaisesRegex(ValueError, "número inteiro"):
            calcular_valor_agua(Decimal("1.5"))


class CalculosGasTests(SimpleTestCase):
    def test_valor_gas(self):
        valor = calcular_valor_gas(3)

        self.assertEqual(valor, Decimal("63.06"))

    def test_valor_gas_com_consumo_decimal(self):
        valor = calcular_valor_gas(1.5)

        self.assertEqual(valor, Decimal("31.53"))

    def test_calcular_gas_retorna_dados_completos(self):
        resultado = calcular_gas(
            leitura_anterior=20,
            leitura_atual=23,
        )

        self.assertEqual(resultado["leitura_anterior"], 20)
        self.assertEqual(resultado["leitura_atual"], 23)
        self.assertEqual(resultado["consumo"], 3)
        self.assertEqual(resultado["valor"], Decimal("63.06"))

    def test_consumo_gas_decimal_ignora_casas_decimais(self):
        consumo = calcular_consumo_gas(
            leitura_anterior=Decimal("20.10"),
            leitura_atual=Decimal("23.99"),
        )

        self.assertEqual(consumo, 3)

    def test_valor_gas_rejeita_consumo_negativo_ou_nao_finito(self):
        with self.assertRaisesRegex(ValueError, "não pode ser negativo"):
            calcular_valor_gas(-1)

        with self.assertRaisesRegex(ValueError, "número finito"):
            calcular_valor_gas("NaN")
