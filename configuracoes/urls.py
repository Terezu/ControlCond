from django.urls import path

from . import views

app_name = "configuracoes"

urlpatterns = [
    path("", views.detalhes_configuracao, name="detalhes"),
    path("editar/", views.editar_configuracao, name="editar"),
]
