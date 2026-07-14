from django.urls import path

from . import views

app_name = "faturas"

urlpatterns = [
    path("", views.lista_faturas, name="lista"),
    path("gerar/", views.gerar_fatura, name="gerar"),
]
