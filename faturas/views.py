from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render

from .forms import GerarFaturaForm
from .services import gerar_fatura_mensal, listar_faturas, consultar_fatura


def lista_faturas(request):
    return render(
        request,
        "faturas/lista.html",
        {
            "faturas": listar_faturas(),
        },
    )


def detalhes_fatura(request, fatura_id):
    try:
        fatura = consultar_fatura(fatura_id)
    except ValueError as erro:
        raise Http404(str(erro))

    return render(
        request,
        "faturas/detalhes.html",
        {
            "fatura": fatura,
        },
    )


def gerar_fatura(request):
    apartamento_sem_leitura_base = None

    if request.method == "POST":
        form = GerarFaturaForm(request.POST)

        if form.is_valid():
            leitura = form.cleaned_data["leitura"]

            try:
                fatura = gerar_fatura_mensal(leitura.id)
            except ValueError as erro:
                form.add_error("leitura", str(erro))

                apartamento = leitura.apartamento

                if (
                    apartamento.leitura_base_agua is None
                    or apartamento.leitura_base_gas is None
                ):
                    apartamento_sem_leitura_base = apartamento
            else:
                messages.success(
                    request,
                    (
                        f"Fatura do apartamento "
                        f"{fatura.apartamento.numero}, referente a "
                        f"{fatura.mes:02d}/{fatura.ano}, gerada com sucesso."
                    ),
                )

                return redirect(
                    "faturas:detalhes",
                    fatura_id=fatura.id,
                )
    else:
        form = GerarFaturaForm()

    return render(
        request,
        "faturas/gerar.html",
        {
            "form": form,
            "apartamento_sem_leitura_base": apartamento_sem_leitura_base,
        },
    )

