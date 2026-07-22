import os
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from .settings import _env_bool, _env_int


class VariaveisDeAmbienteTests(SimpleTestCase):
    def test_sqlite_usa_transacoes_imediatas(self):
        self.assertEqual(
            settings.DATABASES["default"]["OPTIONS"]["transaction_mode"],
            "IMMEDIATE",
        )

    def test_booleano_invalido_falha_explicitamente(self):
        with patch.dict(os.environ, {"CONTROLCOND_TESTE_BOOL": "talvez"}):
            with self.assertRaises(ImproperlyConfigured):
                _env_bool("CONTROLCOND_TESTE_BOOL")

    def test_booleanos_validos_sao_interpretados(self):
        for valor, esperado in (("yes", True), ("0", False)):
            with self.subTest(valor=valor), patch.dict(
                os.environ,
                {"CONTROLCOND_TESTE_BOOL": valor},
            ):
                self.assertIs(_env_bool("CONTROLCOND_TESTE_BOOL"), esperado)

    def test_inteiro_respeita_limite_minimo(self):
        with patch.dict(os.environ, {"CONTROLCOND_TESTE_INT": "0"}):
            with self.assertRaises(ImproperlyConfigured):
                _env_int("CONTROLCOND_TESTE_INT", 20, minimo=1)
