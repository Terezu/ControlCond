from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from .forms import ConfiguracaoCondominioForm
from .services import atualizar_configuracao, obter_configuracao


@staff_member_required
@never_cache
@require_safe
def detalhes_configuracao(request):
    return render(
        request,
        "configuracoes/detalhes.html",
        {"configuracao": obter_configuracao(request=request)},
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
