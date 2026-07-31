from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from condominios.services import obter_condominio_ativo
from condominios.permissions import Permissao, usuario_possui_permissao

from .forms import ContratoForm, FiltrarContratosForm, RescindirContratoForm
from .permissions import usuario_pode_rescindir_contrato
from .selectors import classificar_contratos, filtrar_contratos
from .services import (
    cadastrar_contrato,
    consultar_contrato,
    editar_contrato,
    rescindir_contrato,
)


def _dados_contrato(form):
    dados = form.cleaned_data
    return {
        "apartamento_id": dados["apartamento"].id,
        "pessoa_contratante_id": dados["pessoa_contratante"].id,
        "responsavel_financeiro_id": dados["responsavel_financeiro"].id,
        "data_inicio": dados["data_inicio"],
        "data_termino": dados["data_termino"],
        "observacoes": dados["observacoes"],
    }


def _restringir_pessoas_contratos(request, condominio, contratos):
    if usuario_possui_permissao(
        request.user,
        condominio,
        Permissao.VISUALIZAR_DADOS_PESSOAIS_SENSIVEIS,
    ):
        return
    pessoas = {}
    for contrato in contratos:
        pessoas[contrato.pessoa_contratante.id] = contrato.pessoa_contratante
        pessoas[contrato.responsavel_financeiro.id] = (
            contrato.responsavel_financeiro
        )
    for pessoa in pessoas.values():
        pessoa.cpf = "Informação restrita"
        pessoa.rg = "Informação restrita"
        pessoa.email = "Informação restrita"
        pessoa.telefone = "Informação restrita"
        pessoa.observacoes = None


@login_required
@never_cache
@require_safe
def lista_contratos(request):
    condominio = obter_condominio_ativo(request)
    form = FiltrarContratosForm(
        request.GET or None, condominio=condominio
    )
    filtros = {}
    if form.is_valid():
        filtros = {
            campo: form.cleaned_data[campo]
            for campo in form.fields
        }
    aba = request.GET.get("aba") or ""
    contratos = filtrar_contratos(
        condominio,
        aba=aba,
        incluir_dados_sensiveis=usuario_possui_permissao(
            request.user,
            condominio,
            Permissao.VISUALIZAR_DADOS_PESSOAIS_SENSIVEIS,
        ),
        **filtros,
    )
    pagina = Paginator(contratos, 10).get_page(request.GET.get("page"))
    for contrato in pagina:
        contrato.situacao = contrato.calcular_situacao()
    _restringir_pessoas_contratos(
        request, condominio, pagina.object_list
    )
    resumo = classificar_contratos(condominio)
    parametros = request.GET.copy()
    parametros.pop("page", None)
    return render(
        request,
        "contratos/lista.html",
        {
            "contratos": pagina,
            "pagina_contratos": pagina,
            "form_filtros": form,
            "aba_ativa": aba,
            "resumo": {
                chave: queryset.count()
                for chave, queryset in resumo.items()
            },
            "parametros_filtros": parametros.urlencode(),
        },
    )


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def novo_contrato(request):
    condominio = obter_condominio_ativo(request)
    form = ContratoForm(
        request.POST or None, condominio=condominio
    )
    if request.method == "POST" and form.is_valid():
        try:
            contrato = cadastrar_contrato(
                condominio=condominio,
                usuario=request.user,
                **_dados_contrato(form),
            )
        except ValueError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Contrato cadastrado com sucesso.")
            return redirect("contratos:detalhes", contrato_id=contrato.id)
    return render(
        request,
        "contratos/formulario.html",
        {"form": form, "titulo": "Cadastrar contrato"},
    )


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def editar_dados_contrato(request, contrato_id):
    condominio = obter_condominio_ativo(request)
    try:
        contrato = consultar_contrato(
            contrato_id, condominio=condominio
        )
    except ValueError as exc:
        raise Http404(str(exc)) from exc
    _restringir_pessoas_contratos(request, condominio, [contrato])
    form = ContratoForm(
        request.POST or None,
        instance=contrato,
        condominio=condominio,
    )
    if request.method == "POST" and form.is_valid():
        try:
            contrato = editar_contrato(
                contrato.id,
                condominio=condominio,
                usuario=request.user,
                **_dados_contrato(form),
            )
        except ValueError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Contrato atualizado com sucesso.")
            return redirect("contratos:detalhes", contrato_id=contrato.id)
    return render(
        request,
        "contratos/formulario.html",
        {
            "form": form,
            "titulo": "Editar contrato",
            "contrato": contrato,
        },
    )


@login_required
@never_cache
@require_safe
def detalhes_contrato(request, contrato_id):
    condominio = obter_condominio_ativo(request)
    try:
        contrato = consultar_contrato(
            contrato_id, condominio=condominio
        )
    except ValueError as exc:
        raise Http404(str(exc)) from exc
    _restringir_pessoas_contratos(request, condominio, [contrato])
    return render(
        request,
        "contratos/detalhes.html",
        {
            "contrato": contrato,
            "pode_rescindir": (
                contrato.pode_ser_rescindido()
                and usuario_pode_rescindir_contrato(
                    request.user, condominio
                )
            ),
        },
    )


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def rescindir(request, contrato_id):
    condominio = obter_condominio_ativo(request)
    if not usuario_pode_rescindir_contrato(request.user, condominio):
        raise PermissionDenied(
            "Somente proprietários podem rescindir contratos."
        )
    try:
        contrato = consultar_contrato(
            contrato_id, condominio=condominio
        )
    except ValueError as exc:
        raise Http404(str(exc)) from exc
    if not contrato.pode_ser_rescindido():
        raise Http404("Este contrato não pode ser rescindido.")
    form = RescindirContratoForm(
        request.POST or None,
        initial={"data_rescisao": timezone.localdate()},
    )
    if request.method == "POST" and form.is_valid():
        try:
            rescindir_contrato(
                contrato.id,
                condominio=condominio,
                usuario=request.user,
                justificativa=form.cleaned_data["justificativa"],
                data_rescisao=form.cleaned_data["data_rescisao"],
            )
        except ValueError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Contrato rescindido com sucesso.")
            return redirect("contratos:detalhes", contrato_id=contrato.id)
    return render(
        request,
        "contratos/rescindir.html",
        {"contrato": contrato, "form": form},
    )


@login_required
@never_cache
@require_safe
def historico_apartamento(request, apartamento_id):
    condominio = obter_condominio_ativo(request)
    contratos = filtrar_contratos(
        condominio, apartamento=apartamento_id
    )
    if not contratos.exists():
        from apartamentos.models import Apartamento
        if not Apartamento.objects.filter(
            pk=apartamento_id, condominio=condominio
        ).exists():
            raise Http404("Apartamento não encontrado.")
    for contrato in contratos:
        contrato.situacao = contrato.calcular_situacao()
    _restringir_pessoas_contratos(request, condominio, contratos)
    return render(
        request,
        "contratos/historico.html",
        {"contratos": contratos, "apartamento_id": apartamento_id},
    )
