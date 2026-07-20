from django.urls import path

from . import views

app_name = "faturas"

urlpatterns = [
    path("", views.lista_faturas, name="lista"),
    path("gerar/", views.gerar_fatura, name="gerar"),
    path(
        "<int:fatura_id>/pdf/",
        views.visualizar_pdf_fatura,
        name="pdf",
    ),
    path(
        "<int:fatura_id>/status/",
        views.alterar_status_fatura,
        name="alterar_status",
    ),
    path(
        "<int:fatura_id>/",
        views.detalhes_fatura,
        name="detalhes",
    ),
]
