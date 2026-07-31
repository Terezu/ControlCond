from django.urls import path

from . import views

app_name = "pessoas"

urlpatterns = [
    path("", views.lista_pessoas, name="lista"),
    path("nova/", views.nova_pessoa, name="nova"),
    path("<int:pessoa_id>/", views.detalhes_pessoa, name="detalhes"),
    path(
        "<int:pessoa_id>/editar/",
        views.editar_dados_pessoa,
        name="editar",
    ),
    path(
        "<int:pessoa_id>/vinculos/novo/",
        views.novo_vinculo,
        name="novo_vinculo",
    ),
    path(
        "<int:pessoa_id>/vinculos/<int:vinculo_id>/editar/",
        views.editar_vinculo_pessoa,
        name="editar_vinculo",
    ),
    path(
        "<int:pessoa_id>/vinculos/<int:vinculo_id>/encerrar/",
        views.encerrar_vinculo_pessoa,
        name="encerrar_vinculo",
    ),
]
