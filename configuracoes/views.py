from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from .forms import (
    ConfiguracaoCondominioForm,
    DuplicarRegraForm,
    EncerrarVigenciaForm,
    FaixaTarifaAguaFormSet,
    TabelaTarifariaAguaForm,
    TarifaGasForm,
)
from .models import TabelaTarifariaAgua, TarifaGas
from .services import (
    atualizar_configuracao,
    obter_configuracao,
    obter_tabela_agua_vigente,
    obter_tarifa_gas_vigente,
    salvar_regra_vigencia,
)


@staff_member_required
@never_cache
@require_safe
def detalhes_configuracao(request):
    from django.utils import timezone
    hoje = timezone.localdate()
    try:
        tabela_agua = obter_tabela_agua_vigente(hoje.month, hoje.year)
    except ValueError:
        tabela_agua = None
    try:
        tarifa_gas = obter_tarifa_gas_vigente(hoje.month, hoje.year)
    except ValueError:
        tarifa_gas = None
    return render(
        request,
        "configuracoes/detalhes.html",
        {
            "configuracao": obter_configuracao(request=request),
            "tabela_agua_vigente": tabela_agua,
            "tarifa_gas_vigente": tarifa_gas,
        },
    )


@staff_member_required
@never_cache
@require_http_methods(["GET", "POST"])
def editar_configuracao(request):
    configuracao = obter_configuracao(request=request)
    form = ConfiguracaoCondominioForm(
        request.POST or None,
        request.FILES or None,
        instance=configuracao,
    )
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                atualizar_configuracao(form.cleaned_data)
        except ValueError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(
                request,
                "Configurações atualizadas com sucesso.",
            )
            return redirect("configuracoes:detalhes")

    return render(
        request,
        "configuracoes/formulario.html",
        {
            "configuracao": configuracao,
            "form": form,
        },
    )


@staff_member_required
@never_cache
@require_safe
def listar_tabelas_agua(request):
    return render(request, "configuracoes/tabelas_agua.html", {
        "tabelas": TabelaTarifariaAgua.objects.prefetch_related("faixas"),
    })


@staff_member_required
@never_cache
@require_http_methods(["GET", "POST"])
def editar_tabela_agua(request, tabela_id=None):
    tabela = (
        get_object_or_404(TabelaTarifariaAgua, pk=tabela_id)
        if tabela_id else TabelaTarifariaAgua()
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
                tabela = salvar_regra_vigencia(form.save(commit=False))
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


@staff_member_required
@never_cache
@require_safe
def detalhe_tabela_agua(request, tabela_id):
    tabela = get_object_or_404(
        TabelaTarifariaAgua.objects.prefetch_related("faixas"), pk=tabela_id
    )
    return render(request, "configuracoes/tabela_agua_detalhe.html", {
        "tabela": tabela,
    })


@staff_member_required
@never_cache
@require_http_methods(["GET", "POST"])
def duplicar_tabela_agua(request, tabela_id):
    origem = get_object_or_404(
        TabelaTarifariaAgua.objects.prefetch_related("faixas"), pk=tabela_id
    )
    form = DuplicarRegraForm(request.POST or None, initial={"nome": f"Cópia de {origem.nome}"})
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                nova = TabelaTarifariaAgua(
                    nome=form.cleaned_data["nome"],
                    data_inicio_vigencia=form.cleaned_data["data_inicio_vigencia"],
                    ativa=False,
                )
                salvar_regra_vigencia(nova)
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


@staff_member_required
@never_cache
@require_safe
def listar_tarifas_gas(request):
    return render(request, "configuracoes/tarifas_gas.html", {
        "tarifas": TarifaGas.objects.all(),
    })


@staff_member_required
@never_cache
@require_http_methods(["GET", "POST"])
def editar_tarifa_gas(request, tarifa_id=None):
    tarifa = get_object_or_404(TarifaGas, pk=tarifa_id) if tarifa_id else TarifaGas()
    if tarifa.pk and tarifa.foi_utilizada and request.method == "POST":
        messages.error(request, "Tarifas já utilizadas não podem ser alteradas.")
        return redirect("configuracoes:tarifas_gas")
    form = TarifaGasForm(request.POST or None, instance=tarifa)
    if request.method == "POST" and form.is_valid():
        try:
            salvar_regra_vigencia(form.save(commit=False))
        except (ValidationError, ValueError) as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Tarifa de gás salva com sucesso.")
            return redirect("configuracoes:tarifas_gas")
    return render(request, "configuracoes/tarifa_gas_form.html", {
        "form": form, "tarifa": tarifa,
    })


@staff_member_required
@never_cache
@require_http_methods(["GET", "POST"])
def duplicar_tarifa_gas(request, tarifa_id):
    origem = get_object_or_404(TarifaGas, pk=tarifa_id)
    form = DuplicarRegraForm(
        request.POST or None, initial={"nome": f"Cópia de {origem.nome}"}
    )
    if request.method == "POST" and form.is_valid():
        try:
            nova = TarifaGas(
                nome=form.cleaned_data["nome"],
                valor_por_m3=origem.valor_por_m3,
                data_inicio_vigencia=form.cleaned_data["data_inicio_vigencia"],
                ativa=False,
                observacoes=origem.observacoes,
            )
            salvar_regra_vigencia(nova)
        except (ValidationError, ValueError) as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Tarifa duplicada para revisão.")
            return redirect("configuracoes:tarifa_gas_editar", tarifa_id=nova.pk)
    return render(request, "configuracoes/duplicar_regra.html", {
        "form": form, "titulo": "Duplicar tarifa de gás", "origem": origem,
    })


@staff_member_required
@never_cache
@require_http_methods(["POST"])
def encerrar_vigencia(request, tipo, regra_id):
    modelo = TabelaTarifariaAgua if tipo == "agua" else TarifaGas if tipo == "gas" else None
    if modelo is None:
        from django.http import Http404
        raise Http404
    regra = get_object_or_404(modelo, pk=regra_id)
    form = EncerrarVigenciaForm(request.POST)
    if form.is_valid():
        regra.data_fim_vigencia = form.cleaned_data["data_fim_vigencia"]
        try:
            salvar_regra_vigencia(regra)
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
