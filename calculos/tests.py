from django.test import SimpleTestCase

from .services import calcular_consumo_agua, calcular_consumo_gas


class CalcularConsumoTest(SimpleTestCase):
    def test_primeira_leitura_tem_consumo_zero(self):
        self.assertEqual(calcular_consumo_agua(None, 10), 0)
        self.assertEqual(calcular_consumo_gas(None, 5), 0)

    def test_leitura_atual_nao_pode_ser_menor(self):
        with self.assertRaisesMessage(
            ValueError,
            "A leitura atual de água não pode ser menor que a anterior.",
        ):
            calcular_consumo_agua(10, 9)
