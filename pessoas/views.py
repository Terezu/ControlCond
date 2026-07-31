from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from condominios.services import obter_condominio_ativo
from condominios.permissions import Permissao, usuario_possui_permissao

from .forms import (
    EditarVinculoPessoaApartamentoForm,
    EncerrarVinculoForm,
    FiltrarPessoasForm,
    PessoaForm,
    VinculoPessoaApartamentoForm,
)
from .models import VinculoPessoaApartamento
from .services import (
    cadastrar_pessoa,
    consultar_detalhes_pessoa,
    consultar_pessoa,
    criar_vinculo,
    editar_pessoa,
    editar_vinculo,
    encerrar_vinculo,
    listar_pessoas,
)


def _dados_pessoa(form):
    return {
        campo: form.cleaned_data[campo]
        for campo in form._meta.fields
    }


def _pode_ver_sensiveis(request, condominio):
    return usuario_possui_permissao(
        request.user,
        condominio,
        Permissao.VISUALIZAR_DADOS_PESSOAIS_SENSIVEIS,
    )


def _restringir_dados_sensiveis(pessoa):
    pessoa.cpf = "Informação restrita"
    pessoa.rg = "Informação restrita"
    pessoa.email = "Informação restrita"
    pessoa.telefone = "Informação restrita"
    pessoa.data_nascimento = None
    pessoa.observacoes = None
    return pessoa


@login_required
@never_cache
@require_safe
def lista_pessoas(request):
    condominio = obter_condominio_ativo(request)
    form_filtros = FiltrarPessoasForm(request.GET or None)
    filtros = {}
    if form_filtros.is_valid():
        filtros = {
            campo: form_filtros.cleaned_data[campo]
            for campo in ("busca", "situacao", "tipo_vinculo")
        }
    pode_ver_sensiveis = _pode_ver_sensiveis(request, condominio)
    pagina = Paginator(
        listar_pessoas(
            condominio=condominio,
            incluir_sensiveis=pode_ver_sensiveis,
            **filtros,
        ),
        10,
    ).get_page(request.GET.get("page"))
    if not pode_ver_sensiveis:
        for pessoa in pagina.object_list:
            _restringir_dados_sensiveis(pessoa)
    parametros = request.GET.copy()
    parametros.pop("page", None)
    return render(
        request,
        "pessoas/lista.html",
        {
            "pessoas": pagina,
            "pagina_pessoas": pagina,
            "form_filtros": form_filtros,
            "parametros_filtros": parametros.urlencode(),
        },
    )


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def nova_pessoa(request):
    condominio = obter_condominio_ativo(request)
    form = PessoaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            pessoa = cadastrar_pessoa(
                condominio=condominio,
                **_dados_pessoa(form),
            )
        except ValueError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Pessoa cadastrada com sucesso.")
            return redirect("pessoas:detalhes", pessoa_id=pessoa.id)
    return render(
        request,
        "pessoas/formulario.html",
        {"form": form, "titulo": "Cadastrar pessoa"},
    )


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def editar_dados_pessoa(request, pessoa_id):
    condominio = obter_condominio_ativo(request)
    try:
        pessoa = consultar_pessoa(pessoa_id, condominio=condominio)
    except ValueError as exc:
        raise Http404(str(exc)) from exc
    form = PessoaForm(request.POST or None, instance=pessoa)
    if request.method == "POST" and form.is_valid():
        try:
            pessoa = editar_pessoa(
                pessoa_id,
                condominio=condominio,
                **_dados_pessoa(form),
            )
        except ValueError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Pessoa atualizada com sucesso.")
            return redirect("pessoas:detalhes", pessoa_id=pessoa.id)
    return render(
        request,
        "pessoas/formulario.html",
        {"form": form, "titulo": "Editar pessoa", "pessoa": pessoa},
    )


@login_required
@never_cache
@require_safe
def detalhes_pessoa(request, pessoa_id):
    condominio = obter_condominio_ativo(request)
    try:
        pessoa = consultar_detalhes_pessoa(
            pessoa_id, condominio=condominio
        )
    except ValueError as exc:
        raise Http404(str(exc)) from exc
    vinculos = list(pessoa.vinculos_apartamentos.all())
    contratos = {
        item.id: item
        for item in (
            list(pessoa.contratos_como_contratante.all())
            + list(pessoa.contratos_como_responsavel_financeiro.all())
        )
    }
    for contrato in contratos.values():
        contrato.situacao = contrato.calcular_situacao()
    pode_ver_sensiveis = _pode_ver_sensiveis(request, condominio)
    if not pode_ver_sensiveis:
        _restringir_dados_sensiveis(pessoa)
    return render(
        request,
        "pessoas/detalhes.html",
        {
            "pessoa": pessoa,
            "vinculos": vinculos,
            "contratos": sorted(
                contratos.values(),
                key=lambda item: (item.data_inicio, item.id),
                reverse=True,
            ),
            "pode_visualizar_dados_sensiveis": pode_ver_sensiveis,
        },
    )


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def novo_vinculo(request, pessoa_id):
    condominio = obter_condominio_ativo(request)
    try:
        pessoa = consultar_pessoa(pessoa_id, condominio=condominio)
    except ValueError as exc:
        raise Http404(str(exc)) from exc
    form = VinculoPessoaApartamentoForm(
        request.POST or None, condominio=condominio
    )
    if request.method == "POST" and form.is_valid():
        try:
            criar_vinculo(
                condominio=condominio,
                pessoa_id=pessoa.id,
                apartamento_id=form.cleaned_data["apartamento"].id,
                tipo=form.cleaned_data["tipo"],
                data_inicio=form.cleaned_data["data_inicio"],
                usuario=request.user,
            )
        except ValueError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Vínculo criado com sucesso.")
            return redirect("pessoas:detalhes", pessoa_id=pessoa.id)
    return render(
        request,
        "pessoas/formulario_vinculo.html",
        {"form": form, "pessoa": pessoa},
    )


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def editar_vinculo_pessoa(request, pessoa_id, vinculo_id):
    condominio = obter_condominio_ativo(request)
    try:
        pessoa = consultar_pessoa(pessoa_id, condominio=condominio)
        vinculo = pessoa.vinculos_apartamentos.select_related(
            "apartamento"
        ).get(pk=vinculo_id)
    except (ValueError, VinculoPessoaApartamento.DoesNotExist) as exc:
        raise Http404("Vínculo não encontrado.") from exc
    form = EditarVinculoPessoaApartamentoForm(
        request.POST or None,
        instance=vinculo,
        condominio=condominio,
    )
    if request.method == "POST" and form.is_valid():
        try:
            editar_vinculo(
                vinculo.id,
                condominio=condominio,
                apartamento_id=form.cleaned_data["apartamento"].id,
                tipo=form.cleaned_data["tipo"],
                data_inicio=form.cleaned_data["data_inicio"],
                usuario=request.user,
            )
        except ValueError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Vínculo atualizado com sucesso.")
            return redirect("pessoas:detalhes", pessoa_id=pessoa.id)
    return render(
        request,
        "pessoas/formulario_vinculo.html",
        {
            "form": form,
            "pessoa": pessoa,
            "vinculo": vinculo,
            "titulo": "Editar vínculo",
        },
    )


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def encerrar_vinculo_pessoa(request, pessoa_id, vinculo_id):
    condominio = obter_condominio_ativo(request)
    try:
        pessoa = consultar_pessoa(pessoa_id, condominio=condominio)
        vinculo = pessoa.vinculos_apartamentos.select_related(
            "apartamento"
        ).get(pk=vinculo_id)
    except (ValueError, VinculoPessoaApartamento.DoesNotExist) as exc:
        raise Http404("Vínculo não encontrado.") from exc
    form = EncerrarVinculoForm(
        request.POST or None, data_inicio=vinculo.data_inicio
    )
    if request.method == "POST" and form.is_valid():
        try:
            encerrar_vinculo(
                vinculo.id,
                condominio=condominio,
                data_fim=form.cleaned_data["data_fim"],
                usuario=request.user,
            )
        except ValueError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Vínculo encerrado com sucesso.")
            return redirect("pessoas:detalhes", pessoa_id=pessoa.id)
    return render(
        request,
        "pessoas/encerrar_vinculo.html",
        {"form": form, "pessoa": pessoa, "vinculo": vinculo},
    )
