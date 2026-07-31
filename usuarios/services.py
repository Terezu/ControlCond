from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.contrib.sessions.models import Session
from django.utils import timezone
from dataclasses import dataclass

from condominios.models import VinculoUsuarioCondominio
from condominios.permissions import (
    Permissao,
    exigir_permissao,
    papel_atual,
)

from .deletion_guard import autorizar_exclusao_usuario
from .models import (
    AuditoriaAcesso,
    AuditoriaRemocaoUsuario,
    EstadoPrivacidadeUsuario,
)


P = VinculoUsuarioCondominio.Papel
PAPEIS_PROPRIETARIO = {
    P.PROPRIETARIO,
    P.PROPRIETARIO_ADMINISTRATIVO,
}
PAPEIS_ADMINISTRACAO_OPERACIONAL = {
    P.ADMINISTRADOR,
    P.PROPRIETARIO_ADMINISTRATIVO,
}


def papeis_gerenciaveis(executor, condominio):
    if executor.is_superuser:
        return {
            P.PROPRIETARIO,
            P.PROPRIETARIO_ADMINISTRATIVO,
            P.ADMINISTRADOR,
            P.OPERADOR,
            P.CONSULTA,
        }
    por_papel = {
        P.PROPRIETARIO: {P.ADMINISTRADOR},
        P.PROPRIETARIO_ADMINISTRATIVO: {
            P.ADMINISTRADOR, P.OPERADOR, P.CONSULTA,
        },
        P.ADMINISTRADOR: {P.OPERADOR, P.CONSULTA},
    }
    return por_papel.get(papel_atual(executor, condominio), set())


def _proteger_alteracao(
    executor,
    condominio,
    usuario,
    papel,
    ativo,
    vinculo=None,
    conta_ativa=True,
):
    exigir_permissao(
        executor, condominio, Permissao.GERENCIAR_USUARIOS
    )
    permitidos = papeis_gerenciaveis(executor, condominio)
    if papel not in permitidos:
        raise PermissionDenied("Você não pode conceder este cargo.")
    if vinculo and vinculo.papel not in permitidos:
        raise PermissionDenied("Você não pode alterar este usuário.")
    if getattr(usuario, "is_superuser", False) and not executor.is_superuser:
        raise PermissionDenied(
            "Administradores Globais só podem ser alterados globalmente."
        )
    if executor == usuario and vinculo and papel != vinculo.papel:
        raise PermissionDenied("Você não pode alterar o próprio papel.")
    if executor == usuario and vinculo and vinculo.ativo is False and ativo:
        raise PermissionDenied("Você não pode reativar o próprio acesso.")
    if vinculo and vinculo.papel in PAPEIS_PROPRIETARIO and (
        papel not in PAPEIS_PROPRIETARIO or not ativo or not conta_ativa
    ):
        outros = VinculoUsuarioCondominio.objects.filter(
            condominio=condominio,
            papel__in=PAPEIS_PROPRIETARIO,
            ativo=True,
            usuario__is_active=True,
        ).exclude(pk=vinculo.pk)
        if not outros.exists():
            raise ValueError(
                "Não é possível desativar ou remover o último proprietário ativo."
            )
    if vinculo and vinculo.papel in PAPEIS_ADMINISTRACAO_OPERACIONAL and (
        papel not in PAPEIS_ADMINISTRACAO_OPERACIONAL
        or not ativo
        or not conta_ativa
    ):
        outros = VinculoUsuarioCondominio.objects.filter(
            condominio=condominio,
            papel__in=PAPEIS_ADMINISTRACAO_OPERACIONAL,
            ativo=True,
            usuario__is_active=True,
        ).exclude(pk=vinculo.pk)
        if not outros.exists():
            raise ValueError(
                "Não é possível desativar o último administrador operacional ativo."
            )
    if conta_ativa != usuario.is_active:
        raise PermissionDenied(
            "Use o fluxo global específico para alterar a situação da conta."
        )


@transaction.atomic
def cadastrar_usuario(
    *,
    executor,
    condominio,
    username,
    email,
    first_name,
    last_name,
    senha_temporaria,
    papel,
    ativo=True,
    origem="painel",
    justificativa="",
):
    User = get_user_model()
    if User.objects.filter(username__iexact=username).exists():
        raise ValueError("Já existe um usuário com este nome.")
    if email and User.objects.filter(email__iexact=email).exists():
        raise ValueError("Já existe um usuário com este e-mail.")
    usuario = User(
        username=username.strip(),
        email=email.strip().lower(),
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        is_active=ativo,
    )
    _proteger_alteracao(
        executor, condominio, usuario, papel, ativo, conta_ativa=ativo
    )
    validate_password(senha_temporaria, usuario)
    usuario.set_password(senha_temporaria)
    try:
        usuario.full_clean()
        usuario.save()
        vinculo = VinculoUsuarioCondominio.objects.create(
            usuario=usuario,
            condominio=condominio,
            papel=papel,
            ativo=ativo,
        )
    except IntegrityError as exc:
        raise ValueError("Não foi possível criar o usuário.") from exc
    AuditoriaAcesso.objects.create(
        executor=executor,
        usuario_afetado=usuario,
        condominio=condominio,
        acao="criacao",
        papel_posterior=papel,
        ativo_posterior=ativo,
        origem=origem,
        justificativa=(justificativa or "").strip(),
        operacao_global=executor.is_superuser,
    )
    return usuario, vinculo


@transaction.atomic
def alterar_acesso(
    vinculo_id,
    *,
    executor,
    condominio,
    papel,
    ativo,
    conta_ativa,
    origem="painel",
    justificativa="",
):
    try:
        vinculo = (
            VinculoUsuarioCondominio.objects.select_for_update()
            .select_related("usuario")
            .get(pk=vinculo_id, condominio=condominio)
        )
    except VinculoUsuarioCondominio.DoesNotExist as exc:
        raise ValueError("Acesso não encontrado.") from exc
    _proteger_alteracao(
        executor,
        condominio,
        vinculo.usuario,
        papel,
        ativo,
        vinculo,
        conta_ativa,
    )
    justificativa = (justificativa or "").strip()
    if vinculo.ativo and not ativo and not justificativa:
        raise ValueError("Informe a justificativa para desativar o vínculo.")
    anterior_papel, anterior_ativo = vinculo.papel, vinculo.ativo
    vinculo.papel, vinculo.ativo = papel, ativo
    vinculo.save(update_fields=["papel", "ativo", "atualizado_em"])
    vinculo.usuario.is_active = conta_ativa
    vinculo.usuario.save(update_fields=["is_active"])
    AuditoriaAcesso.objects.create(
        executor=executor,
        usuario_afetado=vinculo.usuario,
        condominio=condominio,
        acao="alteracao",
        papel_anterior=anterior_papel,
        papel_posterior=papel,
        ativo_anterior=anterior_ativo,
        ativo_posterior=ativo,
        origem=origem,
        justificativa=justificativa,
        operacao_global=executor.is_superuser,
    )
    return vinculo


@dataclass(frozen=True)
class AnaliseExclusaoUsuario:
    usuario_id: int
    exclusao_fisica_permitida: bool
    anonimizacao_obrigatoria: bool
    referencias: dict
    impedimentos: tuple
    alertas: tuple

    @property
    def acao_prevista(self):
        return (
            "anonimizacao"
            if self.anonimizacao_obrigatoria
            else "exclusao_fisica"
        )

    @property
    def confirmacao_exigida(self):
        return (
            "ANONIMIZAR USUARIO"
            if self.anonimizacao_obrigatoria
            else "EXCLUIR USUARIO"
        )


def _validar_global(executor):
    if not getattr(executor, "is_active", False):
        raise PermissionDenied("Administrador Global inativo.")
    exigir_permissao(
        executor, None, Permissao.EXCLUIR_USUARIO_PERMANENTEMENTE
    )


def _justificativa_obrigatoria(justificativa):
    justificativa = (justificativa or "").strip()
    if not justificativa:
        raise ValueError("A justificativa é obrigatória.")
    return justificativa


def _invalidar_sessoes_usuario(usuario_id):
    removidas = 0
    for sessao in Session.objects.all().iterator():
        try:
            dados = sessao.get_decoded()
        except Exception:
            continue
        if str(dados.get("_auth_user_id")) == str(usuario_id):
            sessao.delete()
            removidas += 1
    return removidas


def _usuario_anonimizado(usuario):
    try:
        return usuario.estado_privacidade.anonimizado
    except EstadoPrivacidadeUsuario.DoesNotExist:
        return False


def analisar_exclusao_usuario(usuario_alvo):
    referencias = {}
    modelo_privacidade = EstadoPrivacidadeUsuario
    for relacao in usuario_alvo._meta.related_objects:
        if relacao.related_model is modelo_privacidade:
            continue
        campo = relacao.field
        filtro = {campo.name: usuario_alvo}
        quantidade = relacao.related_model._default_manager.filter(
            **filtro
        ).count()
        if quantidade:
            modulo = relacao.related_model._meta.app_label
            tipo = relacao.related_model._meta.verbose_name_plural
            chave = f"{modulo}.{relacao.related_model._meta.model_name}"
            referencias[chave] = {
                "modulo": modulo,
                "tipo": str(tipo),
                "quantidade": quantidade,
            }
    tem_historico = bool(referencias)
    impedimentos = tuple(
        f"{item['tipo']}: {item['quantidade']}"
        for item in referencias.values()
    )
    alertas = ["Esta ação é irreversível."]
    if tem_historico:
        alertas.append(
            "As referências históricas exigem anonimização da conta."
        )
    return AnaliseExclusaoUsuario(
        usuario_id=usuario_alvo.pk,
        exclusao_fisica_permitida=not tem_historico,
        anonimizacao_obrigatoria=tem_historico,
        referencias=referencias,
        impedimentos=impedimentos,
        alertas=tuple(alertas),
    )


def _proteger_global_ativo(usuario_alvo):
    if not usuario_alvo.is_superuser or not usuario_alvo.is_active:
        return
    User = get_user_model()
    outros = User.objects.select_for_update().filter(
        is_superuser=True, is_active=True
    ).exclude(pk=usuario_alvo.pk)
    if not outros.exists():
        raise ValueError(
            "Não é possível desativar o último Administrador Global ativo."
        )


def _proteger_funcoes_condominiais_essenciais(usuario_alvo):
    vinculos = usuario_alvo.vinculos_condominios.filter(ativo=True)
    for vinculo in vinculos:
        if vinculo.papel in PAPEIS_PROPRIETARIO:
            existe_outro = VinculoUsuarioCondominio.objects.filter(
                condominio=vinculo.condominio,
                papel__in=PAPEIS_PROPRIETARIO,
                ativo=True,
                usuario__is_active=True,
            ).exclude(usuario=usuario_alvo).exists()
            if not existe_outro:
                raise ValueError(
                    "Não é possível desativar o último proprietário ativo."
                )
        if vinculo.papel in PAPEIS_ADMINISTRACAO_OPERACIONAL:
            existe_outro = VinculoUsuarioCondominio.objects.filter(
                condominio=vinculo.condominio,
                papel__in=PAPEIS_ADMINISTRACAO_OPERACIONAL,
                ativo=True,
                usuario__is_active=True,
            ).exclude(usuario=usuario_alvo).exists()
            if not existe_outro:
                raise ValueError(
                    "Não é possível desativar o último administrador operacional ativo."
                )


def _auditar_remocao(
    *, executor, usuario_id, acao, justificativa, resultado,
    anterior, posterior, referencias, origem
):
    return AuditoriaRemocaoUsuario.objects.create(
        executor=executor,
        executor_id_interno=executor.pk,
        usuario_alvo_id=usuario_id,
        acao=acao,
        justificativa=justificativa,
        origem=origem,
        resultado=resultado,
        situacao_anterior=anterior,
        situacao_posterior=posterior,
        modulos_com_referencias=referencias,
        operacao_global=True,
    )


@transaction.atomic
def desativar_conta_usuario(
    usuario_id, *, executor, justificativa, origem="painel_global"
):
    _validar_global(executor)
    justificativa = _justificativa_obrigatoria(justificativa)
    User = get_user_model()
    usuario = User.objects.select_for_update().get(pk=usuario_id)
    if usuario == executor:
        raise PermissionDenied("Você não pode desativar a própria conta.")
    if _usuario_anonimizado(usuario):
        raise ValueError("A conta já foi anonimizada.")
    _proteger_global_ativo(usuario)
    _proteger_funcoes_condominiais_essenciais(usuario)
    anterior = {"is_active": usuario.is_active}
    usuario.is_active = False
    usuario.last_login = timezone.now()
    usuario.save(update_fields=["is_active", "last_login"])
    _invalidar_sessoes_usuario(usuario.pk)
    _auditar_remocao(
        executor=executor,
        usuario_id=usuario.pk,
        acao=AuditoriaRemocaoUsuario.Acao.DESATIVACAO_CONTA,
        justificativa=justificativa,
        resultado="conta_desativada",
        anterior=anterior,
        posterior={"is_active": False},
        referencias={},
        origem=origem,
    )
    return usuario


@transaction.atomic
def reativar_conta_usuario(
    usuario_id, *, executor, justificativa, origem="painel_global"
):
    _validar_global(executor)
    justificativa = _justificativa_obrigatoria(justificativa)
    User = get_user_model()
    usuario = User.objects.select_for_update().get(pk=usuario_id)
    if _usuario_anonimizado(usuario):
        raise ValueError("Uma conta anonimizada não pode ser reativada.")
    anterior = {"is_active": usuario.is_active}
    usuario.is_active = True
    usuario.save(update_fields=["is_active"])
    _auditar_remocao(
        executor=executor,
        usuario_id=usuario.pk,
        acao=AuditoriaRemocaoUsuario.Acao.REATIVACAO_CONTA,
        justificativa=justificativa,
        resultado="conta_reativada",
        anterior=anterior,
        posterior={"is_active": True},
        referencias={},
        origem=origem,
    )
    return usuario


@transaction.atomic
def anonimizar_usuario(
    usuario_id, *, executor, justificativa, origem="painel_global"
):
    _validar_global(executor)
    justificativa = _justificativa_obrigatoria(justificativa)
    User = get_user_model()
    usuario = User.objects.select_for_update().get(pk=usuario_id)
    if usuario == executor:
        raise PermissionDenied("Você não pode anonimizar a própria conta.")
    if _usuario_anonimizado(usuario):
        raise ValueError("A conta já foi anonimizada.")
    _proteger_global_ativo(usuario)
    _proteger_funcoes_condominiais_essenciais(usuario)
    analise = analisar_exclusao_usuario(usuario)
    if not analise.anonimizacao_obrigatoria:
        raise ValueError("A conta não possui histórico; utilize a exclusão física.")
    estado, _ = EstadoPrivacidadeUsuario.objects.get_or_create(usuario=usuario)
    identificador = estado.identificador_anonimo.hex
    anterior = {
        "is_active": usuario.is_active,
        "is_superuser": usuario.is_superuser,
        "is_staff": usuario.is_staff,
    }
    usuario.username = f"usuario_anonimo_{identificador}"
    usuario.email = f"anonimo_{identificador}@invalid.local"
    usuario.first_name = ""
    usuario.last_name = ""
    usuario.is_active = False
    usuario.is_staff = False
    usuario.is_superuser = False
    usuario.set_unusable_password()
    usuario.save(update_fields=[
        "username", "email", "first_name", "last_name", "is_active",
        "is_staff", "is_superuser", "password",
    ])
    usuario.groups.clear()
    usuario.user_permissions.clear()
    VinculoUsuarioCondominio.objects.filter(
        usuario=usuario, ativo=True
    ).update(ativo=False, atualizado_em=timezone.now())
    estado.anonimizado_em = timezone.now()
    estado.anonimizado_por = executor
    estado.save(update_fields=["anonimizado_em", "anonimizado_por"])
    _invalidar_sessoes_usuario(usuario.pk)
    _auditar_remocao(
        executor=executor,
        usuario_id=usuario.pk,
        acao=AuditoriaRemocaoUsuario.Acao.ANONIMIZACAO,
        justificativa=justificativa,
        resultado="anonimizacao_concluida",
        anterior=anterior,
        posterior={"is_active": False, "anonimizado": True},
        referencias=analise.referencias,
        origem=origem,
    )
    return usuario


@transaction.atomic
def excluir_usuario_permanentemente(
    usuario_id, *, executor, justificativa, origem="painel_global"
):
    _validar_global(executor)
    justificativa = _justificativa_obrigatoria(justificativa)
    User = get_user_model()
    usuario = User.objects.select_for_update().get(pk=usuario_id)
    if usuario == executor:
        raise PermissionDenied("Você não pode excluir a própria conta.")
    if _usuario_anonimizado(usuario):
        raise ValueError("A conta já foi anonimizada.")
    _proteger_global_ativo(usuario)
    analise = analisar_exclusao_usuario(usuario)
    if not analise.exclusao_fisica_permitida:
        raise ValueError("Existem referências históricas; anonimização obrigatória.")
    alvo_id = usuario.pk
    _invalidar_sessoes_usuario(alvo_id)
    _auditar_remocao(
        executor=executor,
        usuario_id=alvo_id,
        acao=AuditoriaRemocaoUsuario.Acao.EXCLUSAO_FISICA,
        justificativa=justificativa,
        resultado="exclusao_fisica_concluida",
        anterior={"is_active": usuario.is_active},
        posterior={"excluido": True},
        referencias={},
        origem=origem,
    )
    with autorizar_exclusao_usuario():
        usuario.delete()
    return alvo_id


@transaction.atomic
def executar_remocao_segura_usuario(
    usuario_id, *, executor, justificativa, confirmacao,
    ciente, origem="painel_global"
):
    _validar_global(executor)
    if not ciente:
        raise ValueError("Confirme que está ciente da irreversibilidade.")
    User = get_user_model()
    usuario = User.objects.select_for_update().get(pk=usuario_id)
    analise = analisar_exclusao_usuario(usuario)
    if (confirmacao or "").strip() != analise.confirmacao_exigida:
        raise ValueError(
            f'Digite exatamente "{analise.confirmacao_exigida}".'
        )
    if analise.anonimizacao_obrigatoria:
        return anonimizar_usuario(
            usuario.pk, executor=executor, justificativa=justificativa,
            origem=origem,
        )
    return excluir_usuario_permanentemente(
        usuario.pk, executor=executor, justificativa=justificativa,
        origem=origem,
    )


def desativar_vinculo_condominial(
    vinculo_id, *, executor, condominio, justificativa, origem="painel"
):
    vinculo = VinculoUsuarioCondominio.objects.get(
        pk=vinculo_id, condominio=condominio
    )
    return alterar_acesso(
        vinculo.pk,
        executor=executor,
        condominio=condominio,
        papel=vinculo.papel,
        ativo=False,
        conta_ativa=vinculo.usuario.is_active,
        justificativa=justificativa,
        origem=origem,
    )
