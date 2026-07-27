from decimal import Decimal
from datetime import date
from io import BytesIO
import logging
from zipfile import ZIP_DEFLATED, ZipFile

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import slugify
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from .forms import (
    EditarValoresFaturaForm,
    FechamentoMensalForm,
    FiltrarFaturasForm,
    GerarFaturaForm,
    MotivoAlteracaoStatusForm,
    RegistrarPagamentoForm,
)
from .models import Fatura
from configuracoes.services import obter_configuracao
from condominios.services import obter_condominio_ativo

from .pdf import gerar_pdf_fatura_bytes
from .services import (
    RegraNegocioFaturaError,
    calcular_pagamento_fatura,
    cancelar_fatura,
    consultar_fatura,
    consultar_fatura_no_condominio,
    consultar_valores_padrao_leitura,
    editar_fatura,
    excluir_fatura,
    executar_fechamento_mensal,
    executar_fechamento_mensal_por_condominio,
    estornar_pagamento,
    gerar_fatura_mensal,
    listar_faturas,
    listar_faturas_por_condominio,
    listar_faturas_para_download_mensal,
    listar_faturas_download_por_condominio,
    marcar_fatura_como_paga,
    obter_contexto_geracao_fatura,
    reabrir_fatura,
)

logger = logging.getLogger(__name__)


@staff_member_required
@never_cache
@require_safe
def lista_faturas(request):
    condominio = obter_condominio_ativo(request)
    form_filtros = FiltrarFaturasForm(
        request.GET or None, condominio=condominio
    )

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

    faturas = listar_faturas_por_condominio(condominio, **filtros)

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
        fatura = consultar_fatura_no_condominio(
            obter_condominio_ativo(request), fatura_id
        )
    except ValueError as erro:
        raise Http404(str(erro)) from erro

    form_valores = EditarValoresFaturaForm(fatura=fatura)
    historico_status = fatura.historico_status.select_related(
        "usuario"
    ).all()

    return render(
        request,
        "faturas/detalhes.html",
        {
            "fatura": fatura,
            "form_valores": form_valores,
            "historico_status": historico_status,
        },
    )


@staff_member_required
@never_cache
@require_http_methods(["GET", "POST"])
def confirmar_exclusao_fatura(request, fatura_id):
    try:
        fatura = consultar_fatura_no_condominio(
            obter_condominio_ativo(request), fatura_id
        )
    except ValueError as exc:
        raise Http404(str(exc)) from exc

    if request.method == "POST":
        try:
            identificacao = excluir_fatura(fatura_id)
        except ValueError as exc:
            raise Http404(str(exc)) from exc
        messages.success(
            request,
            f"{identificacao} foi excluída permanentemente.",
        )
        logger.info(
            "Fatura excluída permanentemente",
            extra={
                "fatura_id": fatura_id,
                "usuario_id": request.user.id,
            },
        )
        return redirect("faturas:lista")

    return render(
        request,
        "components/confirmar_exclusao.html",
        {
            "titulo": "Excluir fatura",
            "identificacao": (
                f"Fatura do mês {fatura.mes:02d}/{fatura.ano}"
            ),
            "registros": (
                ("Apartamento", str(fatura.apartamento)),
                ("Mês", f"{fatura.mes:02d}/{fatura.ano}"),
                ("Valor total", f"R$ {fatura.valor_total:.2f}"),
                ("Status atual", fatura.get_status_display()),
            ),
            "bloqueada": False,
            "aviso": "Tem certeza de que deseja excluir permanentemente esta fatura?",
            "consequencia": (
                "Esta ação é irreversível. Após a exclusão, os dados e o "
                "histórico de status desta fatura deixarão de existir."
            ),
            "url_cancelar": reverse(
                "faturas:detalhes",
                args=[fatura.id],
            ),
        },
    )


ACOES_STATUS = {
    "marcar_como_paga": {
        "titulo": "Confirmar pagamento da fatura?",
        "aviso": (
            "Após a confirmação, os valores da fatura ficarão "
            "bloqueados para edição."
        ),
        "rotulo": "Marcar como paga",
        "status_origem": Fatura.Status.PENDENTE,
        "service": marcar_fatura_como_paga,
        "mensagem_sucesso": "Pagamento da fatura confirmado.",
        "url_acao": "faturas:marcar_como_paga",
    },
    "cancelar": {
        "titulo": "Confirmar cancelamento da fatura?",
        "aviso": (
            "Após a confirmação, os valores da fatura ficarão "
            "bloqueados para edição."
        ),
        "rotulo": "Cancelar fatura",
        "status_origem": Fatura.Status.PENDENTE,
        "service": cancelar_fatura,
        "mensagem_sucesso": "Fatura cancelada.",
        "url_acao": "faturas:cancelar",
    },
    "estornar_pagamento": {
        "titulo": "Estornar pagamento da fatura?",
        "aviso": (
            "A fatura voltará ao status pendente e poderá ser "
            "editada novamente."
        ),
        "rotulo": "Estornar pagamento",
        "status_origem": Fatura.Status.PAGA,
        "service": estornar_pagamento,
        "mensagem_sucesso": "Pagamento estornado.",
        "url_acao": "faturas:estornar_pagamento",
        "exige_motivo": True,
    },
    "reabrir": {
        "titulo": "Reabrir fatura cancelada?",
        "aviso": (
            "A fatura voltará ao status pendente e poderá ser "
            "editada novamente."
        ),
        "rotulo": "Reabrir fatura",
        "status_origem": Fatura.Status.CANCELADA,
        "service": reabrir_fatura,
        "mensagem_sucesso": "Fatura reaberta.",
        "url_acao": "faturas:reabrir",
        "exige_motivo": True,
    },
}


def _obter_fatura_acao(request, fatura_id):
    return get_object_or_404(
        Fatura.objects.select_related("apartamento", "leitura"),
        pk=fatura_id,
        apartamento__condominio=obter_condominio_ativo(request),
    )


def _redirecionar_detalhes(fatura):
    return redirect("faturas:detalhes", fatura_id=fatura.id)


def _mensagem_formulario(form):
    return next(
        (
            str(erro)
            for erros in form.errors.values()
            for erro in erros
        ),
        "Verifique os dados informados.",
    )


def _confirmar_acao_status(request, fatura_id, acao):
    fatura = _obter_fatura_acao(request, fatura_id)
    configuracao = ACOES_STATUS[acao]
    if fatura.status != configuracao["status_origem"]:
        messages.error(
            request,
            "A ação solicitada não corresponde ao status atual da fatura.",
        )
        return _redirecionar_detalhes(fatura)
    if acao == "marcar_como_paga":
        form = RegistrarPagamentoForm()
        previsao_pagamento = calcular_pagamento_fatura(
            fatura,
            form.fields["data_pagamento"].initial,
        )
    elif configuracao.get("exige_motivo"):
        form = MotivoAlteracaoStatusForm(acao=acao)
    else:
        form = None
    if acao != "marcar_como_paga":
        previsao_pagamento = None
    return render(
        request,
        "faturas/confirmar_acao_status.html",
        {
            "fatura": fatura,
            "form": form,
            "previsao_pagamento": previsao_pagamento,
            **configuracao,
        },
    )


@staff_member_required
@never_cache
@require_safe
def previsao_pagamento(request, fatura_id):
    fatura = _obter_fatura_acao(request, fatura_id)
    if fatura.status != Fatura.Status.PENDENTE:
        return JsonResponse(
            {"erro": "Somente faturas pendentes podem receber pagamento."},
            status=409,
        )
    try:
        data_pagamento = date.fromisoformat(
            request.GET.get("data_pagamento", "")
        )
        resultado = calcular_pagamento_fatura(fatura, data_pagamento)
    except (TypeError, ValueError, RegraNegocioFaturaError):
        return JsonResponse(
            {"erro": "Informe uma data de pagamento válida."},
            status=400,
        )
    return JsonResponse(
        {
            "valor_original": f"{resultado.valor_original:.2f}",
            "desconto": f"{resultado.desconto:.2f}",
            "bonificacao": f"{resultado.bonificacao:.2f}",
            "multa": f"{resultado.multa:.2f}",
            "juros": f"{resultado.juros:.2f}",
            "valor_final": f"{resultado.valor_final:.2f}",
            "dias_em_atraso": resultado.dias_em_atraso,
            "dias_antecipados": resultado.dias_antecipados,
        }
    )


def _executar_acao_status(request, fatura_id, acao):
    fatura = _obter_fatura_acao(request, fatura_id)
    configuracao = ACOES_STATUS[acao]
    motivo = None
    data_pagamento = None
    forma_pagamento = None
    observacoes_pagamento = ""
    if acao == "marcar_como_paga":
        form = RegistrarPagamentoForm(request.POST)
        if not form.is_valid():
            messages.error(request, _mensagem_formulario(form))
            return redirect(
                "faturas:confirmar_marcar_como_paga",
                fatura_id=fatura.id,
            )
        data_pagamento = form.cleaned_data["data_pagamento"]
        forma_pagamento = form.cleaned_data["forma_pagamento"]
        observacoes_pagamento = form.cleaned_data[
            "observacoes_pagamento"
        ]
    elif configuracao.get("exige_motivo"):
        form = MotivoAlteracaoStatusForm(request.POST, acao=acao)
        if not form.is_valid():
            messages.error(request, _mensagem_formulario(form))
            return redirect(
                f"faturas:confirmar_{acao}",
                fatura_id=fatura.id,
            )
        motivo = form.cleaned_data["motivo"]
    try:
        argumentos = {"usuario": request.user}
        if configuracao.get("exige_motivo"):
            argumentos["motivo"] = motivo
        if acao == "marcar_como_paga":
            argumentos["data_pagamento"] = data_pagamento
            argumentos["forma_pagamento"] = forma_pagamento
            argumentos["observacoes_pagamento"] = observacoes_pagamento
        _, alterada = configuracao["service"](
            fatura.id,
            **argumentos,
        )
    except (RegraNegocioFaturaError, ValueError) as erro:
        mensagem = (
            erro.messages[0]
            if isinstance(erro, RegraNegocioFaturaError)
            else str(erro)
        )
        messages.error(request, mensagem)
    else:
        if alterada:
            messages.success(
                request,
                configuracao["mensagem_sucesso"],
            )
        else:
            messages.info(
                request,
                "A fatura já está com o status solicitado.",
            )
    return _redirecionar_detalhes(fatura)


def _criar_views_acao(acao):
    @staff_member_required
    @never_cache
    @require_safe
    def confirmar(request, fatura_id):
        return _confirmar_acao_status(request, fatura_id, acao)

    @staff_member_required
    @never_cache
    @require_http_methods(["POST"])
    def executar(request, fatura_id):
        return _executar_acao_status(request, fatura_id, acao)

    return confirmar, executar


(
    confirmar_marcar_como_paga,
    marcar_como_paga,
) = _criar_views_acao("marcar_como_paga")
confirmar_cancelar, cancelar = _criar_views_acao("cancelar")
(
    confirmar_estornar_pagamento,
    estornar_pagamento_fatura,
) = _criar_views_acao("estornar_pagamento")
confirmar_reabrir, reabrir = _criar_views_acao("reabrir")


@staff_member_required
@never_cache
@require_http_methods(["GET", "POST"])
def fechamento_mensal(request):
    condominio = obter_condominio_ativo(request)
    resultado = None
    periodo_download = None
    form = FechamentoMensalForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            resultado = executar_fechamento_mensal_por_condominio(
                condominio,
                form.cleaned_data["mes"],
                form.cleaned_data["ano"],
            )
            mes = form.cleaned_data["mes"]
            ano = form.cleaned_data["ano"]
            periodo_download = {
                "mes": mes,
                "ano": ano,
                "total_faturas": (
                    listar_faturas_download_por_condominio(
                        condominio, mes, ano
                    ).count()
                ),
            }
        except ValueError as erro:
            form.add_error(None, str(erro))
        except Exception:
            form.add_error(
                None,
                (
                    "Não foi possível concluir o fechamento. "
                    "Nenhuma fatura do lote foi mantida."
                ),
            )
    return render(
        request,
        "faturas/fechamento_mensal.html",
        {
            "form": form,
            "resultado": resultado,
            "periodo_download": periodo_download,
        },
    )


def _nome_pdf_no_zip(fatura):
    partes = [f"fatura-{fatura.id}"]
    bloco = slugify(fatura.apartamento_bloco_emissao or "")
    numero = slugify(
        fatura.apartamento_numero_emissao
        or fatura.apartamento.numero
        or ""
    )
    if bloco:
        partes.append(f"bloco-{bloco}")
    partes.append(f"apartamento-{numero or fatura.apartamento_id}")
    partes.append(f"{fatura.ano}-{fatura.mes:02d}")
    return "_".join(partes) + ".pdf"


@staff_member_required
@never_cache
@require_safe
def baixar_faturas_mes(request, ano, mes):
    condominio = obter_condominio_ativo(request)
    try:
        faturas = list(
            listar_faturas_download_por_condominio(condominio, mes, ano)
        )
    except ValueError as exc:
        raise Http404(str(exc)) from exc
    if not faturas:
        raise Http404("Nenhuma fatura disponível para este período.")

    destino = BytesIO()
    try:
        condominio = obter_condominio_ativo(request)
        configuracao = obter_configuracao(condominio)
        with ZipFile(destino, mode="w", compression=ZIP_DEFLATED) as arquivo_zip:
            for fatura in faturas:
                arquivo_zip.writestr(
                    _nome_pdf_no_zip(fatura),
                    gerar_pdf_fatura_bytes(
                        fatura,
                        configuracao=configuracao,
                    ),
                )
    except Exception:
        logger.exception(
            "Falha ao gerar ZIP de faturas para %02d/%d.",
            mes,
            ano,
            extra={"usuario_id": request.user.id},
        )
        return HttpResponse(
            "Não foi possível gerar o arquivo de faturas.",
            status=500,
            content_type="text/plain; charset=utf-8",
        )

    resposta = HttpResponse(
        destino.getvalue(),
        content_type="application/zip",
    )
    resposta["Content-Disposition"] = (
        f'attachment; filename="faturas_{ano}_{mes:02d}.zip"'
    )
    return resposta


@staff_member_required
@never_cache
@require_http_methods(["POST"])
def alterar_valores_fatura(request, fatura_id):
    try:
        fatura = consultar_fatura_no_condominio(
            obter_condominio_ativo(request), fatura_id
        )
    except ValueError as erro:
        raise Http404(str(erro)) from erro

    form = EditarValoresFaturaForm(
        request.POST,
        fatura=fatura,
    )
    if not form.is_valid():
        mensagem = next(
            (
                str(erro)
                for erros in form.errors.values()
                for erro in erros
            ),
            "Verifique o valor do aluguel e o desconto informados.",
        )
        messages.error(
            request,
            mensagem,
        )
        return redirect("faturas:detalhes", fatura_id=fatura.id)

    try:
        argumentos = {
            "valor_aluguel": form.cleaned_data["valor_aluguel"],
            "desconto": form.cleaned_data["desconto"],
        }
        for campo in (
            "valor_condominio",
            "valor_iptu",
            "valor_bonificacao",
            "dia_limite_bonificacao",
            "valor_outros",
            "observacao_outros",
        ):
            if campo in request.POST:
                argumentos[campo] = form.cleaned_data[campo]
        editar_fatura(fatura.id, **argumentos)
    except (RegraNegocioFaturaError, ValueError) as erro:
        mensagem = (
            erro.messages[0]
            if isinstance(erro, RegraNegocioFaturaError)
            else str(erro)
        )
        messages.error(request, mensagem)
    else:
        messages.success(
            request,
            "Valores financeiros da fatura atualizados com sucesso.",
        )
    return redirect("faturas:detalhes", fatura_id=fatura.id)

@staff_member_required
@never_cache
@require_http_methods(["GET", "POST"])
def gerar_fatura(request):
    condominio = obter_condominio_ativo(request)
    apartamento_sem_leitura_base = None

    if request.method == "POST":
        leitura_id = request.POST.get("leitura")
        if leitura_id:
            try:
                _, fatura_existente = obter_contexto_geracao_fatura(
                    leitura_id,
                )
            except ValueError:
                fatura_existente = None
            if fatura_existente is not None:
                messages.info(
                    request,
                    "A fatura desta leitura já foi gerada.",
                )
                return redirect(
                    "faturas:detalhes",
                    fatura_id=fatura_existente.id,
                )

        form = GerarFaturaForm(request.POST, condominio=condominio)

        if form.is_valid():
            leitura = form.cleaned_data["leitura"]

            try:
                fatura = gerar_fatura_mensal(
                    leitura.id,
                    valor_aluguel=form.cleaned_data["valor_aluguel"],
                    desconto=form.cleaned_data["desconto"],
                    valor_condominio=form.cleaned_data["valor_condominio"],
                    valor_iptu=form.cleaned_data["valor_iptu"],
                    valor_bonificacao=form.cleaned_data[
                        "valor_bonificacao"
                    ],
                    dia_limite_bonificacao=form.cleaned_data[
                        "dia_limite_bonificacao"
                    ],
                    valor_outros=form.cleaned_data["valor_outros"],
                    observacao_outros=form.cleaned_data[
                        "observacao_outros"
                    ],
                )
            except ValueError as erro:
                try:
                    _, fatura_existente = obter_contexto_geracao_fatura(
                        leitura.id,
                    )
                except ValueError:
                    fatura_existente = None

                if fatura_existente is not None:
                    messages.info(
                        request,
                        "A fatura desta leitura já foi gerada.",
                    )
                    return redirect(
                        "faturas:detalhes",
                        fatura_id=fatura_existente.id,
                    )

                form.add_error(None, str(erro))

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
        leitura_id = request.GET.get("leitura")
        if leitura_id:
            try:
                leitura, fatura_existente = obter_contexto_geracao_fatura(
                    leitura_id,
                )
            except ValueError as erro:
                messages.error(request, str(erro))
                return redirect("leituras:lista")

            if fatura_existente is not None:
                messages.info(
                    request,
                    "A fatura desta leitura já foi gerada.",
                )
                return redirect(
                    "faturas:detalhes",
                    fatura_id=fatura_existente.id,
                )

            form = GerarFaturaForm(
                initial={
                    "leitura": leitura,
                    "valor_aluguel": leitura.apartamento.valor_aluguel,
                    "valor_condominio": leitura.apartamento.valor_condominio,
                    "valor_iptu": leitura.apartamento.valor_iptu,
                    "valor_bonificacao": leitura.apartamento.valor_bonificacao,
                    "dia_limite_bonificacao": (
                        leitura.apartamento.dia_limite_bonificacao
                    ),
                    "valor_outros": Decimal("0.00"),
                    "desconto": Decimal("0.00"),
                },
                condominio=condominio,
            )
        else:
            form = GerarFaturaForm(condominio=condominio)

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
def valor_aluguel_leitura(request):
    leitura_id = request.GET.get("leitura")
    try:
        leitura_id = int(leitura_id)
        valores = consultar_valores_padrao_leitura(leitura_id)
    except (TypeError, ValueError):
        return JsonResponse(
            {"erro": "Leitura não encontrada."},
            status=404,
        )
    return JsonResponse(
        {
            chave: (
                format(valor, ".2f")
                if isinstance(valor, Decimal)
                else valor
            )
            for chave, valor in valores.items()
        }
    )

@staff_member_required
@never_cache
@require_safe
def baixar_pdf_fatura(request, fatura_id):
    fatura = get_object_or_404(
        Fatura.objects.select_related("apartamento", "leitura"),
        id=fatura_id,
        apartamento__condominio=obter_condominio_ativo(request),
    )
    buffer = BytesIO(gerar_pdf_fatura_bytes(fatura))

    apartamento = slugify(
        str(fatura.apartamento_numero_emissao)
    ) or str(fatura.id)
    nome_arquivo = (
        f"fatura-apartamento-{apartamento}-"
        f"{fatura.mes:02d}-{fatura.ano}.pdf"
    )

    return FileResponse(
        buffer,
        as_attachment=True,
        filename=nome_arquivo,
        content_type="application/pdf",
    )
