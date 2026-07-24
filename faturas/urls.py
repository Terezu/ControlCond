from django.urls import path

from . import views

app_name = "faturas"

urlpatterns = [
    path("", views.lista_faturas, name="lista"),
    path("gerar/", views.gerar_fatura, name="gerar"),
    path(
        "valor-aluguel-leitura/",
        views.valor_aluguel_leitura,
        name="valor_aluguel_leitura",
    ),
    path(
        "<int:fatura_id>/pdf/",
        views.baixar_pdf_fatura,
        name="baixar_pdf",
    ),
    path(
        "<int:fatura_id>/marcar-como-paga/confirmar/",
        views.confirmar_marcar_como_paga,
        name="confirmar_marcar_como_paga",
    ),
    path(
        "<int:fatura_id>/marcar-como-paga/",
        views.marcar_como_paga,
        name="marcar_como_paga",
    ),
    path(
        "<int:fatura_id>/cancelar/confirmar/",
        views.confirmar_cancelar,
        name="confirmar_cancelar",
    ),
    path(
        "<int:fatura_id>/cancelar/",
        views.cancelar,
        name="cancelar",
    ),
    path(
        "<int:fatura_id>/estornar-pagamento/confirmar/",
        views.confirmar_estornar_pagamento,
        name="confirmar_estornar_pagamento",
    ),
    path(
        "<int:fatura_id>/estornar-pagamento/",
        views.estornar_pagamento_fatura,
        name="estornar_pagamento",
    ),
    path(
        "<int:fatura_id>/reabrir/confirmar/",
        views.confirmar_reabrir,
        name="confirmar_reabrir",
    ),
    path(
        "<int:fatura_id>/reabrir/",
        views.reabrir,
        name="reabrir",
    ),
    path(
        "<int:fatura_id>/valores/",
        views.alterar_valores_fatura,
        name="alterar_valores",
    ),
    path(
        "<int:fatura_id>/",
        views.detalhes_fatura,
        name="detalhes",
    ),
]
