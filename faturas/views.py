from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.utils.text import slugify
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe
from django.core.paginator import Paginator

from .forms import (
    AlterarStatusFaturaForm,
    FiltrarFaturasForm,
    GerarFaturaForm,
)
from .services import (
    consultar_fatura,
    editar_fatura,
    gerar_fatura_mensal,
    listar_faturas,
)
from .pdf import gerar_pdf_fatura


@staff_member_required
@never_cache
@require_safe
def lista_faturas(request):
    form_filtros = FiltrarFaturasForm(request.GET or None)

    filtros = {}

    if form_filtros.is_valid():
        apartamento = form_filtros.cleaned_data["apartamento"]

        filtros = {
            "apartamento_id": (
                apartamento.id
                if apartamento is not None
                else None
            ),
            "bloco": form_filtros.cleaned_data["bloco"],
            "mes": form_filtros.cleaned_data["mes"] or None,
            "ano": form_filtros.cleaned_data["ano"],
            "status": form_filtros.cleaned_data["status"],
        }

        if filtros["mes"] is not None:
            filtros["mes"] = int(filtros["mes"])

    faturas = listar_faturas(**filtros)

    paginator = Paginator(
        faturas,
        10,
    )

    numero_pagina = request.GET.get("page")
    pagina_faturas = paginator.get_page(numero_pagina)

    parametros_filtros = request.GET.copy()
    parametros_filtros.pop("page", None)

    return render(
        request,
        "faturas/lista.html",
        {
            "faturas": pagina_faturas,
            "pagina_faturas": pagina_faturas,
            "form_filtros": form_filtros,
            "parametros_filtros": parametros_filtros.urlencode(),
        },
    )


@staff_member_required
@never_cache
@require_safe
@staff_member_required
@never_cache
@require_safe
def detalhes_fatura(request, fatura_id):
    try:
        fatura = consultar_fatura(fatura_id)
    except ValueError as erro:
        raise Http404(str(erro)) from erro

    form_status = AlterarStatusFaturaForm(fatura=fatura)

    return render(
        request,
        "faturas/detalhes.html",
        {
            "fatura": fatura,
            "form_status": form_status,
        },
    )


@staff_member_required
@never_cache
@require_http_methods(["POST"])
def alterar_status_fatura(request, fatura_id):
    try:
        fatura = consultar_fatura(fatura_id)
    except ValueError as erro:
        raise Http404(str(erro)) from erro

    form = AlterarStatusFaturaForm(
        request.POST,
        fatura=fatura,
    )

    if not form.is_valid():
        messages.error(
            request,
            "Não foi possível alterar o status da fatura.",
        )

        return redirect(
            "faturas:detalhes",
            fatura_id=fatura.id,
        )

    novo_status = form.cleaned_data["status"]

    try:
        editar_fatura(
            fatura.id,
            status=novo_status,
        )
    except ValueError as erro:
        messages.error(request, str(erro))
    else:
        messages.success(
            request,
            (
                "Status da fatura alterado para "
                f"“{dict(fatura.Status.choices)[novo_status]}”."
            ),
        )

    return redirect(
        "faturas:detalhes",
        fatura_id=fatura.id,
    )

@staff_member_required
@never_cache
@require_http_methods(["GET", "POST"])
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
@require_safe
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
