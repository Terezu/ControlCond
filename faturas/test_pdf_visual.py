import hashlib
import json
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase

from apartamentos.models import Apartamento
from configuracoes.services import obter_configuracao
from condominios.models import Condominio

from .models import Fatura
from .pdf import gerar_pdf_fatura


SNAPSHOT_PATH = (
    Path(__file__).resolve().parent
    / "test_snapshots"
    / "pdf_layout.json"
)
METODOS_VISUAIS = {
    "drawRightString",
    "drawString",
    "line",
    "roundRect",
    "setFillColor",
    "setFont",
    "setLineWidth",
    "setStrokeColor",
    "showPage",
}


def _normalizar_argumento(argumento):
    if isinstance(argumento, float):
        return round(argumento, 2)
    if hasattr(argumento, "hexval"):
        return argumento.hexval()
    return argumento


def _assinatura_visual(pdf_mock):
    comandos = []
    for chamada in pdf_mock.method_calls:
        metodo = chamada[0]
        if metodo not in METODOS_VISUAIS:
            continue
        argumentos = list(chamada.args)
        if metodo in {"drawString", "drawRightString"}:
            # O texto é propositalmente descartado: o snapshot protege apenas
            # geometria, alinhamento e hierarquia tipográfica.
            argumentos = argumentos[:2]
        comandos.append(
            {
                "metodo": metodo,
                "args": [
                    _normalizar_argumento(argumento)
                    for argumento in argumentos
                ],
                "kwargs": {
                    chave: _normalizar_argumento(valor)
                    for chave, valor in sorted(chamada.kwargs.items())
                },
            }
        )
    serializado = json.dumps(
        comandos,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return {
        "comandos": len(comandos),
        "sha256": hashlib.sha256(serializado).hexdigest(),
    }


class PdfLayoutSnapshotTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.condominio = Condominio.objects.get()
        cls.apartamento = Apartamento.objects.create(
            condominio=cls.condominio,
            numero="VISUAL",
            bloco="PDF",
        )

    def _fatura(self, mes, *, paga=False):
        fatura = Fatura.objects.create(
            apartamento=self.apartamento,
            mes=mes,
            ano=2026,
            consumo_agua=12,
            consumo_gas=4,
            valor_agua=Decimal("117.66"),
            valor_gas=Decimal("84.08"),
            valor_aluguel=Decimal("1200.00"),
            valor_condominio=Decimal("350.00"),
            valor_iptu=Decimal("75.00"),
            desconto=Decimal("50.00"),
            valor_total=Decimal("1776.74"),
            apartamento_numero_emissao=self.apartamento.numero,
            apartamento_bloco_emissao=self.apartamento.bloco,
        )
        if paga:
            Fatura.objects.filter(pk=fatura.pk).update(
                status=Fatura.Status.PAGA,
                valor_original=Decimal("1826.74"),
                valor_multa_aplicada=Decimal("35.53"),
                valor_juros_aplicados=Decimal("7.10"),
                valor_final=Decimal("1819.37"),
                valor_pago=Decimal("1819.37"),
                data_pagamento=fatura.data_vencimento,
                forma_pagamento=Fatura.FormaPagamento.PIX,
            )
            fatura.refresh_from_db()
        return fatura

    def test_estrutura_visual_permanece_compativel_com_snapshots(self):
        snapshots = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        configuracao = obter_configuracao(self.condominio)

        for cenario, fatura in (
            ("pendente", self._fatura(1)),
            ("paga", self._fatura(2, paga=True)),
        ):
            with self.subTest(cenario=cenario):
                with (
                    patch("faturas.pdf.canvas.Canvas") as canvas_mock,
                    patch("faturas.pdf._desenhar_logo"),
                ):
                    pdf_mock = canvas_mock.return_value
                    pdf_mock.stringWidth.return_value = 0
                    gerar_pdf_fatura(
                        fatura,
                        BytesIO(),
                        configuracao=configuracao,
                    )

                atual = _assinatura_visual(pdf_mock)
                self.assertEqual(
                    atual,
                    snapshots["cenarios"][cenario],
                    (
                        "A estrutura visual do PDF mudou. Revise a alteração "
                        "e atualize o snapshot somente se ela for intencional."
                    ),
                )
