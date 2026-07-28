from django.urls import path

from . import views

app_name = "configuracoes"

urlpatterns = [
    path("", views.detalhes_configuracao, name="detalhes"),
    path("editar/", views.editar_configuracao, name="editar"),
    path(
        "institucionais/",
        views.detalhes_configuracao_institucional,
        name="institucionais",
    ),
    path(
        "institucionais/editar/",
        views.editar_configuracao_institucional,
        name="institucionais_editar",
    ),
    path(
        "operacionais/",
        views.detalhes_configuracao_operacional,
        name="operacionais",
    ),
    path(
        "operacionais/editar/",
        views.editar_configuracao_operacional,
        name="operacionais_editar",
    ),
    path(
        "globais/",
        views.detalhes_configuracao_global,
        name="globais",
    ),
    path(
        "globais/editar/",
        views.editar_configuracao_global,
        name="globais_editar",
    ),
    path("tarifas/agua/", views.listar_tabelas_agua, name="tabelas_agua"),
    path("tarifas/agua/nova/", views.editar_tabela_agua, name="tabela_agua_nova"),
    path("tarifas/agua/<int:tabela_id>/", views.detalhe_tabela_agua, name="tabela_agua_detalhe"),
    path("tarifas/agua/<int:tabela_id>/editar/", views.editar_tabela_agua, name="tabela_agua_editar"),
    path("tarifas/agua/<int:tabela_id>/duplicar/", views.duplicar_tabela_agua, name="tabela_agua_duplicar"),
    path("tarifas/agua/<int:regra_id>/encerrar/", views.encerrar_vigencia, {"tipo": "agua"}, name="tabela_agua_encerrar"),
    path("tarifas/gas/", views.listar_tarifas_gas, name="tarifas_gas"),
    path("tarifas/gas/nova/", views.editar_tarifa_gas, name="tarifa_gas_nova"),
    path("tarifas/gas/<int:tarifa_id>/editar/", views.editar_tarifa_gas, name="tarifa_gas_editar"),
    path("tarifas/gas/<int:tarifa_id>/duplicar/", views.duplicar_tarifa_gas, name="tarifa_gas_duplicar"),
    path("tarifas/gas/<int:regra_id>/encerrar/", views.encerrar_vigencia, {"tipo": "gas"}, name="tarifa_gas_encerrar"),
]
