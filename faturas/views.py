from django.contrib import messages
from django.shortcuts import redirect, render

from .forms import GerarFaturaForm
from .services import gerar_fatura_mensal, listar_faturas


def lista_faturas(request):
    return render(
        request,
        "faturas/lista.html",
        {
            "faturas": listar_faturas(),
        },
    )


def gerar_fatura(request):
    if request.method == "POST":
        form = GerarFaturaForm(request.POST)

        if form.is_valid():
            leitura = form.cleaned_data["leitura"]

            try:
                fatura = gerar_fatura_mensal(leitura.id)
            except ValueError as erro:
                form.add_error("leitura", str(erro))
            else:
                messages.success(
                    request,
                    (
                        f"Fatura do apartamento "
                        f"{fatura.apartamento.numero}, referente a "
                        f"{fatura.mes:02d}/{fatura.ano}, gerada com sucesso."
                    ),
                )

                return redirect("faturas:lista")
    else:
        form = GerarFaturaForm()

    return render(
        request,
        "faturas/gerar.html",
        {
            "form": form,
        },
    )
