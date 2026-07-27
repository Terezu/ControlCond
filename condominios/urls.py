from django.urls import path

from . import views

app_name = "condominios"

urlpatterns = [
    path("selecionar/", views.selecionar_condominio, name="selecionar"),
]
