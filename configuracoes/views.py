from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from .forms import (
    ConfiguracaoCondominioForm,
    ConfiguracaoGlobalForm,
    ConfiguracaoInstitucionalForm,
    ConfiguracaoOperacionalForm,
    DuplicarRegraForm,
    EncerrarVigenciaForm,
    FaixaTarifaAguaFormSet,
    TabelaTarifariaAguaForm,
    TarifaGasForm,
)
from .models import TabelaTarifariaAgua, TarifaGas
from .services import (
    atualizar_configuracao,
    atualizar_configuracao_global,
    atualizar_configuracao_institucional,
    atualizar_configuracao_operacional,
    obter_configuracao,
    obter_configuracao_global,
    obter_tabela_agua_vigente,
    obter_tarifa_gas_vigente,
    salvar_regra_vigencia,
)
from condominios.services import obter_condominio_ativo
from condominios.permissions import (
    Permissao,
    permissao_condominio_required,
    usuario_possui_permissao,
)


@login_required
@never_cache
@require_safe
def detalhes_configuracao(request):
    condominio = obter_condominio_ativo(request)
    if request.user.is_superuser:
        return redirect("configuracoes:globais")
    if usuario_possui_permissao(
        request.user, condominio,
        Permissao.VISUALIZAR_CONFIGURACOES_INSTITUCIONAIS,
    ):
        return redirect("configuracoes:institucionais")
    if usuario_possui_permissao(
        request.user, condominio,
        Permissao.VISUALIZAR_CONFIGURACOES_OPERACIONAIS,
    ):
        return redirect("configuracoes:operacionais")
    raise PermissionDenied("Seu cargo não permite acessar configurações.")


@permissao_condominio_required(
    Permissao.ALTERAR_CONFIGURACOES_INSTITUCIONAIS
)
@never_cache
@require_http_methods(["GET", "POST"])
def editar_configuracao(request):
    return editar_configuracao_institucional(request)


@permissao_condominio_required(
    Permissao.VISUALIZAR_CONFIGURACOES_INSTITUCIONAIS
)
@never_cache
@require_safe
def detalhes_configuracao_institucional(request):
    condominio = obter_condominio_ativo(request)
    return render(request, "configuracoes/institucionais.html", {
        "configuracao": obter_configuracao(condominio),
    })


@permissao_condominio_required(
    Permissao.ALTERAR_CONFIGURACOES_INSTITUCIONAIS
)
@never_cache
@require_http_methods(["GET", "POST"])
def editar_configuracao_institucional(request):
    condominio = obter_condominio_ativo(request)
    configuracao = obter_configuracao(condominio)
    form = ConfiguracaoInstitucionalForm(
        request.POST or None,
        request.FILES or None,
        instance=configuracao,
    )
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                atualizar_configuracao_institucional(
                    condominio, form.cleaned_data, usuario=request.user
                )
        except ValueError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(
                request,
                "Configurações institucionais atualizadas com sucesso.",
            )
            return redirect("configuracoes:institucionais")

    return render(
        request,
        "configuracoes/institucionais_form.html",
        {
            "configuracao": configuracao,
            "form": form,
        },
    )


def _contexto_operacional(condominio):
    from django.utils import timezone
    hoje = timezone.localdate()
    try:
        tabela_agua = obter_tabela_agua_vigente(
            condominio, hoje.month, hoje.year
        )
    except ValueError:
        tabela_agua = None
    try:
        tarifa_gas = obter_tarifa_gas_vigente(
            condominio, hoje.month, hoje.year
        )
    except ValueError:
        tarifa_gas = None
    return {
        "configuracao": obter_configuracao(condominio),
        "tabela_agua_vigente": tabela_agua,
        "tarifa_gas_vigente": tarifa_gas,
    }


@permissao_condominio_required(
    Permissao.VISUALIZAR_CONFIGURACOES_OPERACIONAIS
)
@never_cache
@require_safe
def detalhes_configuracao_operacional(request):
    return render(
        request,
        "configuracoes/operacionais.html",
        _contexto_operacional(obter_condominio_ativo(request)),
    )


@permissao_condominio_required(
    Permissao.ALTERAR_CONFIGURACOES_OPERACIONAIS
)
@never_cache
@require_http_methods(["GET", "POST"])
def editar_configuracao_operacional(request):
    condominio = obter_condominio_ativo(request)
    configuracao = obter_configuracao(condominio)
    form = ConfiguracaoOperacionalForm(
        request.POST or None, instance=configuracao
    )
    if request.method == "POST" and form.is_valid():
        try:
            atualizar_configuracao_operacional(
                condominio, form.cleaned_data, usuario=request.user
            )
        except ValueError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(
                request, "Configurações operacionais atualizadas com sucesso."
            )
            return redirect("configuracoes:operacionais")
    return render(request, "configuracoes/operacionais_form.html", {
        "configuracao": configuracao,
        "form": form,
    })


@login_required
@never_cache
@require_safe
def detalhes_configuracao_global(request):
    if not request.user.is_superuser:
        raise PermissionDenied(
            "Somente Administradores Globais acessam esta área."
        )
    return render(request, "configuracoes/globais.html", {
        "configuracao_global": obter_configuracao_global(),
    })


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def editar_configuracao_global(request):
    if not request.user.is_superuser:
        raise PermissionDenied(
            "Somente Administradores Globais alteram a plataforma."
        )
    configuracao = obter_configuracao_global()
    form = ConfiguracaoGlobalForm(request.POST or None, instance=configuracao)
    if request.method == "POST" and form.is_valid():
        atualizar_configuracao_global(
            form.cleaned_data, usuario=request.user
        )
        messages.success(
            request, "Configurações globais atualizadas com sucesso."
        )
        return redirect("configuracoes:globais")
    return render(request, "configuracoes/globais_form.html", {
        "form": form,
        "configuracao_global": configuracao,
    })


@permissao_condominio_required(
    Permissao.VISUALIZAR_CONFIGURACOES_OPERACIONAIS
)
@never_cache
@require_safe
def listar_tabelas_agua(request):
    condominio = obter_condominio_ativo(request)
    return render(request, "configuracoes/tabelas_agua.html", {
        "tabelas": TabelaTarifariaAgua.objects.filter(
            condominio=condominio
        ).prefetch_related("faixas"),
    })


@permissao_condominio_required(
    Permissao.ALTERAR_CONFIGURACOES_OPERACIONAIS
)
@never_cache
@require_http_methods(["GET", "POST"])
def editar_tabela_agua(request, tabela_id=None):
    condominio = obter_condominio_ativo(request)
    tabela = (
        get_object_or_404(
            TabelaTarifariaAgua, pk=tabela_id, condominio=condominio
        )
        if tabela_id else TabelaTarifariaAgua(condominio=condominio)
    )
    bloqueada = bool(tabela.pk and tabela.foi_utilizada)
    if bloqueada and request.method == "POST":
        messages.error(request, "Tabelas já utilizadas não podem ser alteradas.")
        return redirect("configuracoes:tabela_agua_detalhe", tabela_id=tabela.pk)
    form = TabelaTarifariaAguaForm(request.POST or None, instance=tabela)
    formset = FaixaTarifaAguaFormSet(
        request.POST or None, instance=tabela, prefix="faixas"
    )
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        try:
            with transaction.atomic():
                tabela = salvar_regra_vigencia(
                    form.save(commit=False), usuario=request.user
                )
                formset.instance = tabela
                formset.save()
                from .services import validar_tabela_agua
                validar_tabela_agua(tabela)
        except (ValidationError, ValueError) as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Tabela de água salva com sucesso.")
            return redirect("configuracoes:tabela_agua_detalhe", tabela_id=tabela.pk)
    return render(request, "configuracoes/tabela_agua_form.html", {
        "form": form, "formset": formset, "tabela": tabela,
    })


@permissao_condominio_required(
    Permissao.VISUALIZAR_CONFIGURACOES_OPERACIONAIS
)
@never_cache
@require_safe
def detalhe_tabela_agua(request, tabela_id):
    condominio = obter_condominio_ativo(request)
    tabela = get_object_or_404(
        TabelaTarifariaAgua.objects.prefetch_related("faixas"),
        pk=tabela_id,
        condominio=condominio,
    )
    return render(request, "configuracoes/tabela_agua_detalhe.html", {
        "tabela": tabela,
    })


@permissao_condominio_required(
    Permissao.ALTERAR_CONFIGURACOES_OPERACIONAIS
)
@never_cache
@require_http_methods(["GET", "POST"])
def duplicar_tabela_agua(request, tabela_id):
    condominio = obter_condominio_ativo(request)
    origem = get_object_or_404(
        TabelaTarifariaAgua.objects.prefetch_related("faixas"),
        pk=tabela_id,
        condominio=condominio,
    )
    form = DuplicarRegraForm(request.POST or None, initial={"nome": f"Cópia de {origem.nome}"})
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                nova = TabelaTarifariaAgua(
                    condominio=condominio,
                    nome=form.cleaned_data["nome"],
                    data_inicio_vigencia=form.cleaned_data["data_inicio_vigencia"],
                    ativa=False,
                )
                salvar_regra_vigencia(nova, usuario=request.user)
                for faixa in origem.faixas.order_by("ordem"):
                    faixa.pk = None
                    faixa.tabela = nova
                    faixa.save()
        except (ValidationError, ValueError) as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Tabela duplicada; revise as faixas e ative-a.")
            return redirect("configuracoes:tabela_agua_editar", tabela_id=nova.pk)
    return render(request, "configuracoes/duplicar_regra.html", {
        "form": form, "titulo": "Duplicar tabela de água", "origem": origem,
    })


@permissao_condominio_required(
    Permissao.VISUALIZAR_CONFIGURACOES_OPERACIONAIS
)
@never_cache
@require_safe
def listar_tarifas_gas(request):
    condominio = obter_condominio_ativo(request)
    return render(request, "configuracoes/tarifas_gas.html", {
        "tarifas": TarifaGas.objects.filter(condominio=condominio),
    })


@permissao_condominio_required(
    Permissao.ALTERAR_CONFIGURACOES_OPERACIONAIS
)
@never_cache
@require_http_methods(["GET", "POST"])
def editar_tarifa_gas(request, tarifa_id=None):
    condominio = obter_condominio_ativo(request)
    tarifa = (
        get_object_or_404(
            TarifaGas, pk=tarifa_id, condominio=condominio
        ) if tarifa_id else TarifaGas(condominio=condominio)
    )
    if tarifa.pk and tarifa.foi_utilizada and request.method == "POST":
        messages.error(request, "Tarifas já utilizadas não podem ser alteradas.")
        return redirect("configuracoes:tarifas_gas")
    form = TarifaGasForm(request.POST or None, instance=tarifa)
    if request.method == "POST" and form.is_valid():
        try:
            salvar_regra_vigencia(
                form.save(commit=False), usuario=request.user
            )
        except (ValidationError, ValueError) as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Tarifa de gás salva com sucesso.")
            return redirect("configuracoes:tarifas_gas")
    return render(request, "configuracoes/tarifa_gas_form.html", {
        "form": form, "tarifa": tarifa,
    })


@permissao_condominio_required(
    Permissao.ALTERAR_CONFIGURACOES_OPERACIONAIS
)
@never_cache
@require_http_methods(["GET", "POST"])
def duplicar_tarifa_gas(request, tarifa_id):
    condominio = obter_condominio_ativo(request)
    origem = get_object_or_404(
        TarifaGas, pk=tarifa_id, condominio=condominio
    )
    form = DuplicarRegraForm(
        request.POST or None, initial={"nome": f"Cópia de {origem.nome}"}
    )
    if request.method == "POST" and form.is_valid():
        try:
            nova = TarifaGas(
                nome=form.cleaned_data["nome"],
                condominio=condominio,
                valor_por_m3=origem.valor_por_m3,
                data_inicio_vigencia=form.cleaned_data["data_inicio_vigencia"],
                ativa=False,
                observacoes=origem.observacoes,
            )
            salvar_regra_vigencia(nova, usuario=request.user)
        except (ValidationError, ValueError) as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Tarifa duplicada para revisão.")
            return redirect("configuracoes:tarifa_gas_editar", tarifa_id=nova.pk)
    return render(request, "configuracoes/duplicar_regra.html", {
        "form": form, "titulo": "Duplicar tarifa de gás", "origem": origem,
    })


@permissao_condominio_required(
    Permissao.ALTERAR_CONFIGURACOES_OPERACIONAIS
)
@never_cache
@require_http_methods(["POST"])
def encerrar_vigencia(request, tipo, regra_id):
    modelo = TabelaTarifariaAgua if tipo == "agua" else TarifaGas if tipo == "gas" else None
    if modelo is None:
        from django.http import Http404
        raise Http404
    regra = get_object_or_404(
        modelo, pk=regra_id, condominio=obter_condominio_ativo(request)
    )
    form = EncerrarVigenciaForm(request.POST)
    if form.is_valid():
        regra.data_fim_vigencia = form.cleaned_data["data_fim_vigencia"]
        try:
            salvar_regra_vigencia(regra, usuario=request.user)
        except (ValidationError, ValueError) as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Vigência encerrada com sucesso.")
    else:
        messages.error(request, "Informe uma data final válida.")
    return redirect(
        "configuracoes:tabelas_agua"
        if tipo == "agua" else "configuracoes:tarifas_gas"
    )
