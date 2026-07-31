from django.urls import path
from . import views

app_name = "usuarios"
urlpatterns = [
    path("globais/", views.lista_usuarios_globais, name="lista_global"),
    path(
        "globais/<int:usuario_id>/analisar/",
        views.analisar_remocao_usuario,
        name="analisar_remocao",
    ),
    path(
        "globais/<int:usuario_id>/remover/",
        views.executar_remocao_usuario,
        name="executar_remocao",
    ),
    path(
        "globais/<int:usuario_id>/desativar/",
        views.desativar_conta,
        name="desativar_conta",
    ),
    path(
        "globais/<int:usuario_id>/reativar/",
        views.reativar_conta,
        name="reativar_conta",
    ),
    path("", views.lista_usuarios, name="lista"),
    path("novo/", views.novo_usuario, name="novo"),
    path("perfil/", views.perfil, name="perfil"),
    path("<int:usuario_id>/", views.detalhes_usuario, name="detalhes"),
    path("acesso/<int:vinculo_id>/editar/", views.editar_acesso, name="editar_acesso"),
]
