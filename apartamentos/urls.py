from django.urls import path

from . import views

app_name = "apartamentos"

urlpatterns = [
    path("", views.lista_apartamentos, name="lista"),
    path("novo/", views.novo_apartamento, name="novo"),
    path(
        "<int:apartamento_id>/editar/",
        views.editar_dados_apartamento,
        name="editar",
    ),
    path(
        "<int:apartamento_id>/",
        views.detalhes_apartamento,
        name="detalhes"
    ),
]
