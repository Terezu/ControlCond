from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.utils.text import slugify
from django.views.decorators.cache import never_cache

from .forms import GerarFaturaForm
from .services import gerar_fatura_mensal, listar_faturas, consultar_fatura
from .pdf import gerar_pdf_fatura


@staff_member_required
@never_cache
def lista_faturas(request):
    return render(
        request,
        "faturas/lista.html",
        {
            "faturas": listar_faturas(),
        },
    )


@staff_member_required
@never_cache
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


@staff_member_required
@never_cache
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

@staff_member_required
@never_cache
def visualizar_pdf_fatura(request, fatura_id):
    try:
        fatura = consultar_fatura(fatura_id)
    except ValueError as erro:
        raise Http404(str(erro)) from erro

    arquivo_pdf = gerar_pdf_fatura(fatura)

    nome_arquivo = (
        f"fatura_"
        f"{slugify(fatura.apartamento_numero_emissao) or fatura.id}_"
        f"{fatura.mes:02d}_"
        f"{fatura.ano}.pdf"
    )

    return FileResponse(
        arquivo_pdf,
        content_type="application/pdf",
        filename=nome_arquivo,
    )
