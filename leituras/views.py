from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from apartamentos.models import Apartamento

from .forms import FiltrarLeiturasForm, LeituraForm
from .services import cadastrar_leitura, listar_leituras


@staff_member_required
@never_cache
@require_safe
def lista_leituras(request):
    form_filtros = FiltrarLeiturasForm(request.GET or None)
    filtros = {}

    if form_filtros.is_valid():
        apartamento = form_filtros.cleaned_data["apartamento"]
        mes = form_filtros.cleaned_data["mes"] or None
        filtros = {
            "apartamento_id": apartamento.id if apartamento else None,
            "bloco": form_filtros.cleaned_data["bloco"],
            "mes": int(mes) if mes is not None else None,
            "ano": form_filtros.cleaned_data["ano"],
        }

    paginator = Paginator(listar_leituras(**filtros), 10)
    pagina_leituras = paginator.get_page(request.GET.get("page"))
    parametros_filtros = request.GET.copy()
    parametros_filtros.pop("page", None)

    return render(
        request,
        "leituras/lista.html",
        {
            "leituras": pagina_leituras,
            "pagina_leituras": pagina_leituras,
            "form_filtros": form_filtros,
            "parametros_filtros": parametros_filtros.urlencode(),
        },
    )


@staff_member_required
@never_cache
@require_http_methods(["GET", "POST"])
def nova_leitura(request, apartamento_id):
    apartamento = get_object_or_404(
        Apartamento,
        pk=apartamento_id,
    )

    if request.method == "POST":
        form = LeituraForm(request.POST)

        if form.is_valid():
            try:
                cadastrar_leitura(
                    apartamento=apartamento,
                    mes=form.cleaned_data["mes"],
                    ano=form.cleaned_data["ano"],
                    leitura_agua=form.cleaned_data["leitura_agua"],
                    leitura_gas=form.cleaned_data["leitura_gas"],
                )
            except ValueError as exc:
                form.add_error(None, str(exc))
            else:
                messages.success(
                    request,
                    "Leitura cadastrada com sucesso."
                )

                return redirect(
                    "apartamentos:detalhes",
                    apartamento_id=apartamento.id,
                )
    else:
        form = LeituraForm()

    return render(
        request,
        "leituras/nova.html",
        {
            "apartamento": apartamento,
            "form": form,
        }
    )
