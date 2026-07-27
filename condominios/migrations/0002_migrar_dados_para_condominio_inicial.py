from django.conf import settings
from django.db import migrations
from django.utils.text import slugify


def associar_dados(apps, schema_editor):
    Condominio = apps.get_model("condominios", "Condominio")
    Vinculo = apps.get_model("condominios", "VinculoUsuarioCondominio")
    Configuracao = apps.get_model("configuracoes", "ConfiguracaoCondominio")
    TabelaAgua = apps.get_model("configuracoes", "TabelaTarifariaAgua")
    TarifaGas = apps.get_model("configuracoes", "TarifaGas")
    Apartamento = apps.get_model("apartamentos", "Apartamento")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))

    configuracao = Configuracao.objects.order_by("pk").first()
    nome = (
        configuracao.nome.strip()
        if configuracao and configuracao.nome and configuracao.nome.strip()
        else "Condomínio Inicial"
    )
    slug_base = slugify(nome) or "condominio-inicial"
    condominio, _ = Condominio.objects.get_or_create(
        slug=slug_base,
        defaults={"nome": nome, "ativo": True},
    )
    Configuracao.objects.filter(condominio__isnull=True).update(
        condominio=condominio
    )
    TabelaAgua.objects.filter(condominio__isnull=True).update(
        condominio=condominio
    )
    TarifaGas.objects.filter(condominio__isnull=True).update(
        condominio=condominio
    )
    Apartamento.objects.filter(condominio__isnull=True).update(
        condominio=condominio
    )
    for usuario in User.objects.filter(is_staff=True):
        Vinculo.objects.get_or_create(
            usuario=usuario,
            condominio=condominio,
            defaults={"papel": "administrador", "ativo": True},
        )


def reverter_associacoes(apps, schema_editor):
    apps.get_model(
        "configuracoes", "ConfiguracaoCondominio"
    ).objects.update(condominio=None)
    apps.get_model(
        "configuracoes", "TabelaTarifariaAgua"
    ).objects.update(condominio=None)
    apps.get_model(
        "configuracoes", "TarifaGas"
    ).objects.update(condominio=None)
    apps.get_model("apartamentos", "Apartamento").objects.update(
        condominio=None
    )


class Migration(migrations.Migration):
    dependencies = [
        ("condominios", "0001_initial"),
        ("configuracoes", "0004_remove_configuracaocondominio_configuracao_condominio_registro_unico_and_more"),
        ("apartamentos", "0009_apartamento_condominio"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(associar_dados, reverter_associacoes),
    ]
