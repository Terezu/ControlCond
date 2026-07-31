from django.urls import path

from . import views

app_name = "contratos"

urlpatterns = [
    path("", views.lista_contratos, name="lista"),
    path("novo/", views.novo_contrato, name="novo"),
    path("<int:contrato_id>/", views.detalhes_contrato, name="detalhes"),
    path(
        "<int:contrato_id>/editar/",
        views.editar_dados_contrato,
        name="editar",
    ),
    path(
        "<int:contrato_id>/rescindir/",
        views.rescindir,
        name="rescindir",
    ),
    path(
        "apartamento/<int:apartamento_id>/historico/",
        views.historico_apartamento,
        name="historico_apartamento",
    ),
]
