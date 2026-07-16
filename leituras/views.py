from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache

from apartamentos.models import Apartamento

from .forms import LeituraForm
from .services import cadastrar_leitura


@staff_member_required
@never_cache
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
