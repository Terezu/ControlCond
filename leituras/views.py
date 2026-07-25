import logging

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from apartamentos.models import Apartamento
from condominios.services import obter_condominio_ativo

from .forms import FiltrarLeiturasForm, LeituraForm
from .models import Leitura
from .services import (
    ExclusaoLeituraBloqueadaError,
    cadastrar_leitura,
    excluir_leitura,
    listar_leituras,
)

logger = logging.getLogger(__name__)


@staff_member_required
@never_cache
@require_safe
def lista_leituras(request):
    condominio = obter_condominio_ativo(request)
    form_filtros = FiltrarLeiturasForm(
        request.GET or None, condominio=condominio
    )
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

    paginator = Paginator(
        listar_leituras(**filtros).filter(
            apartamento__condominio=condominio
        ),
        10,
    )
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
        condominio=obter_condominio_ativo(request),
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


@staff_member_required
@never_cache
@require_http_methods(["GET", "POST"])
def confirmar_exclusao_leitura(request, leitura_id):
    leitura = get_object_or_404(
        Leitura.objects.select_related("apartamento").prefetch_related(
            "faturas"
        ),
        pk=leitura_id,
        apartamento__condominio=obter_condominio_ativo(request),
    )
    fatura = leitura.faturas.first()

    if request.method == "POST":
        try:
            identificacao = excluir_leitura(leitura_id)
        except ExclusaoLeituraBloqueadaError as exc:
            fatura = leitura.faturas.first()
            messages.error(request, str(exc))
            logger.warning(
                "Exclusão de leitura bloqueada",
                extra={
                    "leitura_id": leitura_id,
                    "usuario_id": request.user.id,
                },
            )
        except ValueError as exc:
            raise Http404(str(exc)) from exc
        else:
            messages.success(
                request,
                f"{identificacao} excluída permanentemente.",
            )
            logger.info(
                "Leitura excluída permanentemente",
                extra={
                    "leitura_id": leitura_id,
                    "usuario_id": request.user.id,
                },
            )
            return redirect("leituras:lista")

    return render(
        request,
        "components/confirmar_exclusao.html",
        {
            "titulo": "Excluir leitura",
            "identificacao": str(leitura),
            "registros": (
                ("Apartamento", str(leitura.apartamento)),
                ("Mês", f"{leitura.mes:02d}/{leitura.ano}"),
                (
                    "Leitura de água",
                    leitura.leitura_agua
                    if leitura.leitura_agua is not None
                    else "Não informada",
                ),
                (
                    "Leitura de gás",
                    leitura.leitura_gas
                    if leitura.leitura_gas is not None
                    else "Não informada",
                ),
            ),
            "bloqueada": fatura is not None,
            "mensagem_bloqueio": (
                "Esta leitura não pode ser excluída porque já foi utilizada "
                "para gerar uma fatura. Exclua primeiro a fatura correspondente."
            ),
            "aviso": "Tem certeza de que deseja excluir permanentemente esta leitura?",
            "consequencia": (
                "Esta ação é irreversível e pode alterar qual leitura será "
                "considerada como anterior em futuros cálculos."
            ),
            "url_cancelar": reverse(
                "apartamentos:detalhes",
                args=[leitura.apartamento_id],
            ),
            "url_relacionado": (
                reverse("faturas:detalhes", args=[fatura.id])
                if fatura
                else None
            ),
            "texto_relacionado": "Ver fatura vinculada",
        },
    )
