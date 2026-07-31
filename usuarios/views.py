from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from condominios.models import VinculoUsuarioCondominio
from condominios.permissions import (
    Permissao,
    permissao_condominio_required,
    usuario_possui_permissao,
)
from condominios.services import (
    listar_condominios_do_usuario,
    obter_condominio_ativo,
)

from .forms import (
    CadastrarUsuarioForm,
    EditarAcessoForm,
    JustificativaContaForm,
    RemocaoSeguraUsuarioForm,
)
from .services import (
    alterar_acesso,
    analisar_exclusao_usuario,
    cadastrar_usuario,
    desativar_conta_usuario,
    executar_remocao_segura_usuario,
    papeis_gerenciaveis,
    reativar_conta_usuario,
)


@login_required
@never_cache
@require_safe
def perfil(request):
    return render(request, "usuarios/perfil.html", {
        "vinculos": (
            request.user.vinculos_condominios
            .select_related("condominio")
            .filter(ativo=True, condominio__ativo=True)
        )
    })


@permissao_condominio_required(Permissao.GERENCIAR_USUARIOS)
@never_cache
@require_safe
def lista_usuarios(request):
    condominio = obter_condominio_ativo(request)
    vinculos = (
        VinculoUsuarioCondominio.objects
        .filter(condominio=condominio)
        .select_related("usuario")
    )
    busca = request.GET.get("busca", "").strip()
    papel = request.GET.get("papel", "")
    if busca:
        vinculos = vinculos.filter(
            Q(usuario__username__icontains=busca)
            | Q(usuario__email__icontains=busca)
            | Q(usuario__first_name__icontains=busca)
            | Q(usuario__last_name__icontains=busca)
        )
    if papel:
        vinculos = vinculos.filter(papel=papel)
    for campo in ("ativo", "conta_ativa"):
        valor = request.GET.get(campo)
        if valor in {"0", "1"}:
            filtro = {"ativo": valor == "1"} if campo == "ativo" else {
                "usuario__is_active": valor == "1"
            }
            vinculos = vinculos.filter(**filtro)
    permitidos = papeis_gerenciaveis(request.user, condominio)
    for vinculo in vinculos:
        vinculo.pode_editar_acesso = (
            vinculo.papel in permitidos
            and (
                request.user.is_superuser
                or not vinculo.usuario.is_superuser
            )
        )
    return render(request, "usuarios/lista.html", {
        "vinculos": vinculos,
        "papeis": VinculoUsuarioCondominio.Papel.choices,
        "filtros": request.GET,
    })


@permissao_condominio_required(Permissao.GERENCIAR_USUARIOS)
@never_cache
@require_http_methods(["GET", "POST"])
def novo_usuario(request):
    condominio = obter_condominio_ativo(request)
    form = CadastrarUsuarioForm(
        request.POST or None,
        executor=request.user,
        condominio=condominio,
    )
    if request.method == "POST" and form.is_valid():
        try:
            usuario, _ = cadastrar_usuario(
                executor=request.user,
                condominio=condominio,
                **form.cleaned_data,
            )
        except ValidationError as exc:
            for mensagem in exc.messages:
                form.add_error("senha_temporaria", mensagem)
        except (ValueError, PermissionDenied) as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Usuário e acesso criados com sucesso.")
            return redirect("usuarios:detalhes", usuario_id=usuario.id)
    return render(request, "usuarios/formulario.html", {
        "form": form, "titulo": "Cadastrar usuário",
    })


@permissao_condominio_required(Permissao.GERENCIAR_USUARIOS)
@never_cache
@require_http_methods(["GET", "POST"])
def editar_acesso(request, vinculo_id):
    condominio = obter_condominio_ativo(request)
    try:
        vinculo = (
            VinculoUsuarioCondominio.objects.select_related("usuario")
            .get(pk=vinculo_id, condominio=condominio)
        )
    except VinculoUsuarioCondominio.DoesNotExist as exc:
        raise Http404("Acesso não encontrado.") from exc
    if (
        vinculo.papel not in papeis_gerenciaveis(
            request.user, condominio
        )
        or (vinculo.usuario.is_superuser and not request.user.is_superuser)
    ):
        raise PermissionDenied("Você não pode alterar este usuário.")
    form = EditarAcessoForm(
        request.POST or None,
        executor=request.user,
        condominio=condominio,
        vinculo=vinculo,
        initial={
            "papel": vinculo.papel,
            "ativo": vinculo.ativo,
            "conta_ativa": vinculo.usuario.is_active,
        },
    )
    if request.method == "POST" and form.is_valid():
        try:
            alterar_acesso(
                vinculo.id,
                executor=request.user,
                condominio=condominio,
                **form.cleaned_data,
            )
        except (ValueError, PermissionDenied) as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Acesso atualizado com sucesso.")
            return redirect("usuarios:detalhes", usuario_id=vinculo.usuario_id)
    return render(request, "usuarios/formulario.html", {
        "form": form, "titulo": "Editar acesso", "vinculo": vinculo,
    })


@permissao_condominio_required(Permissao.GERENCIAR_USUARIOS)
@never_cache
@require_safe
def detalhes_usuario(request, usuario_id):
    condominio = obter_condominio_ativo(request)
    User = get_user_model()
    try:
        usuario = User.objects.get(
            pk=usuario_id,
            vinculos_condominios__condominio=condominio,
        )
    except User.DoesNotExist as exc:
        raise Http404("Usuário não encontrado.") from exc
    return render(request, "usuarios/detalhes.html", {
        "usuario_detalhe": usuario,
        "vinculos": usuario.vinculos_condominios.select_related("condominio"),
        "vinculo_atual": usuario.vinculos_condominios.get(condominio=condominio),
        "pode_editar_acesso": (
            usuario.vinculos_condominios.get(condominio=condominio).papel
            in papeis_gerenciaveis(request.user, condominio)
            and (request.user.is_superuser or not usuario.is_superuser)
        ),
    })


def _exigir_global(request):
    if not usuario_possui_permissao(
        request.user, None, Permissao.EXCLUIR_USUARIO_PERMANENTEMENTE
    ):
        raise PermissionDenied(
            "Somente Administradores Globais acessam esta ação."
        )


@login_required
@never_cache
@require_safe
def lista_usuarios_globais(request):
    _exigir_global(request)
    User = get_user_model()
    usuarios = User.objects.order_by("username", "id")
    busca = request.GET.get("busca", "").strip()
    if busca:
        usuarios = usuarios.filter(
            Q(username__icontains=busca)
            | Q(email__icontains=busca)
            | Q(first_name__icontains=busca)
            | Q(last_name__icontains=busca)
        )
    return render(request, "usuarios/lista_global.html", {
        "usuarios_globais": usuarios,
        "busca": busca,
    })


@login_required
@never_cache
@require_safe
def analisar_remocao_usuario(request, usuario_id):
    _exigir_global(request)
    usuario = get_user_model().objects.filter(pk=usuario_id).first()
    if usuario is None:
        raise Http404("Usuário não encontrado.")
    analise = analisar_exclusao_usuario(usuario)
    form = RemocaoSeguraUsuarioForm(
        confirmacao_exigida=analise.confirmacao_exigida
    )
    return render(request, "usuarios/analisar_remocao.html", {
        "usuario_alvo": usuario,
        "analise": analise,
        "form": form,
    })


@login_required
@never_cache
@require_http_methods(["POST"])
def executar_remocao_usuario(request, usuario_id):
    _exigir_global(request)
    usuario = get_user_model().objects.filter(pk=usuario_id).first()
    if usuario is None:
        raise Http404("Usuário não encontrado.")
    analise = analisar_exclusao_usuario(usuario)
    form = RemocaoSeguraUsuarioForm(
        request.POST,
        confirmacao_exigida=analise.confirmacao_exigida,
    )
    if form.is_valid():
        try:
            executar_remocao_segura_usuario(
                usuario.pk, executor=request.user, **form.cleaned_data
            )
        except (ValueError, PermissionDenied) as exc:
            form.add_error(None, str(exc))
        else:
            acao = (
                "anonimizado preservando o histórico"
                if analise.anonimizacao_obrigatoria
                else "excluído permanentemente"
            )
            messages.success(request, f"Usuário {acao} com sucesso.")
            return redirect("usuarios:lista_global")
    return render(request, "usuarios/analisar_remocao.html", {
        "usuario_alvo": usuario,
        "analise": analise,
        "form": form,
    })


def _alterar_situacao_global(request, usuario_id, *, reativar):
    _exigir_global(request)
    usuario = get_user_model().objects.filter(pk=usuario_id).first()
    if usuario is None:
        raise Http404("Usuário não encontrado.")
    form = JustificativaContaForm(request.POST)
    if form.is_valid():
        service = (
            reativar_conta_usuario if reativar else desativar_conta_usuario
        )
        try:
            service(
                usuario.pk,
                executor=request.user,
                justificativa=form.cleaned_data["justificativa"],
            )
        except (ValueError, PermissionDenied) as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(
                request,
                "Conta reativada com sucesso."
                if reativar else "Conta desativada com sucesso.",
            )
            return redirect("usuarios:lista_global")
    return render(request, "usuarios/confirmar_situacao_conta.html", {
        "usuario_alvo": usuario,
        "form": form,
        "reativar": reativar,
    })


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def desativar_conta(request, usuario_id):
    return _alterar_situacao_global(
        request, usuario_id, reativar=False
    )


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def reativar_conta(request, usuario_id):
    return _alterar_situacao_global(
        request, usuario_id, reativar=True
    )
