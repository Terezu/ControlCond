from django.urls import path

from . import views

app_name = "apartamentos"

urlpatterns = [
    path("", views.lista_apartamentos, name="lista"),
    path(
        "<int:apartamento_id>/",
        views.detalhes_apartamento,
        name="detalhes"
    ),
]
