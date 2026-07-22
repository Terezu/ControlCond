from django.urls import path

from . import views

app_name = "leituras"

urlpatterns = [
    path(
        "",
        views.lista_leituras,
        name="lista",
    ),
    path(
        "nova/<int:apartamento_id>/",
        views.nova_leitura,
        name="nova",
    ),
]
