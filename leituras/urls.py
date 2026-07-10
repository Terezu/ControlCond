from django.urls import path

from . import views

app_name = "leituras"

urlpatterns = [
    path("", views.lista_leituras, name="lista"),
]

