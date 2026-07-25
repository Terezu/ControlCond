from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from .forms import ConfiguracaoCondominioForm, FaixaTarifaAguaFormSet
from .models import FaixaTarifaAgua
from .services import atualizar_configuracao, obter_configuracao


@staff_member_required
@never_cache
@require_safe
def detalhes_configuracao(request):
    return render(
        request,
        "configuracoes/detalhes.html",
        {
            "configuracao": obter_configuracao(request=request),
            "faixas_agua": FaixaTarifaAgua.objects.order_by("ordem", "id"),
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
    formset_faixas = FaixaTarifaAguaFormSet(
        (
            request.POST
            if request.method == "POST" and "agua-TOTAL_FORMS" in request.POST
            else None
        ),
        queryset=FaixaTarifaAgua.objects.order_by("ordem", "id"),
        prefix="agua",
    )

    if (
        request.method == "POST"
        and form.is_valid()
        and (not formset_faixas.is_bound or formset_faixas.is_valid())
    ):
        try:
            with transaction.atomic():
                atualizar_configuracao(form.cleaned_data)
                if formset_faixas.is_bound:
                    formset_faixas.save()
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
            "formset_faixas": formset_faixas,
        },
    )
