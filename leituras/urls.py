from django.urls import path

from . import views

app_name = "leituras"

urlpatterns = [
    path(
        "nova/<int:apartamento_id>/",
        views.nova_leitura,
        name="nova",
    ),
]
