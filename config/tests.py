import os
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import OperationalError
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import path, reverse

from .settings import _env_bool, _env_int


def _erro_interno_para_teste(request):
    raise RuntimeError("erro interno simulado")


urlpatterns = [path("erro-500/", _erro_interno_para_teste)]


class VariaveisDeAmbienteTests(SimpleTestCase):
    def test_opcoes_do_banco_respeitam_o_backend(self):
        banco = settings.DATABASES["default"]
        if banco["ENGINE"] == "django.db.backends.sqlite3":
            self.assertEqual(banco["OPTIONS"]["transaction_mode"], "IMMEDIATE")
        else:
            self.assertNotIn("transaction_mode", banco.get("OPTIONS", {}))

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


class HealthCheckTests(TestCase):
    def test_banco_disponivel_retorna_resposta_minima(self):
        resposta = self.client.get(reverse("healthz"))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), {"status": "ok"})
        conteudo = resposta.content.decode()
        for dado_sensivel in ("DATABASE_URL", "SECRET_KEY", "usuario", "senha"):
            self.assertNotIn(dado_sensivel, conteudo)

    def test_head_tambem_e_aceito(self):
        resposta = self.client.head(reverse("healthz"))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.content, b"")

    def test_metodo_nao_permitido_retorna_405(self):
        resposta = self.client.post(reverse("healthz"))

        self.assertEqual(resposta.status_code, 405)

    @patch("config.views.connection.cursor", side_effect=OperationalError)
    def test_banco_indisponivel_retorna_503(self, cursor):
        resposta = self.client.get(reverse("healthz"))

        self.assertEqual(resposta.status_code, 503)
        self.assertEqual(resposta.json(), {"status": "unavailable"})
        cursor.assert_called_once_with()


class PaginaErroInternoTests(SimpleTestCase):
    @override_settings(DEBUG=False, ROOT_URLCONF="config.tests")
    def test_erro_500_usa_pagina_publica_sem_detalhes_internos(self):
        cliente = Client(raise_request_exception=False)

        resposta = cliente.get("/erro-500/")

        self.assertEqual(resposta.status_code, 500)
        self.assertContains(
            resposta,
            "Não foi possível concluir esta solicitação",
            status_code=500,
        )
        self.assertNotContains(
            resposta,
            "erro interno simulado",
            status_code=500,
        )
        self.assertNotContains(resposta, "Traceback", status_code=500)
