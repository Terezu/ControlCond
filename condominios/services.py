from django.core.exceptions import PermissionDenied

from .models import Condominio, VinculoUsuarioCondominio


CHAVE_CONDOMINIO_ATIVO = "condominio_ativo_id"


def listar_condominios_do_usuario(usuario):
    if not getattr(usuario, "is_authenticated", False):
        return Condominio.objects.none()
    if usuario.is_superuser:
        return Condominio.objects.filter(ativo=True).order_by("nome", "id")
    return (
        Condominio.objects
        .filter(
            ativo=True,
            vinculos_usuarios__usuario=usuario,
            vinculos_usuarios__ativo=True,
        )
        .distinct()
        .order_by("nome", "id")
    )


def listar_condominios_do_request(request):
    disponiveis = getattr(request, "_condominios_disponiveis", None)
    if disponiveis is None:
        disponiveis = tuple(listar_condominios_do_usuario(request.user))
        request._condominios_disponiveis = disponiveis
    return disponiveis


def obter_vinculo_usuario_condominio(usuario, condominio):
    if not getattr(usuario, "is_authenticated", False):
        return None
    return (
        VinculoUsuarioCondominio.objects
        .select_related("condominio", "usuario")
        .filter(
            usuario=usuario,
            condominio=condominio,
            ativo=True,
            condominio__ativo=True,
        )
        .first()
    )


def usuario_tem_acesso_ao_condominio(usuario, condominio):
    if getattr(usuario, "is_superuser", False):
        return bool(condominio and condominio.ativo)
    return obter_vinculo_usuario_condominio(usuario, condominio) is not None


def obter_condominio_unico_do_usuario(usuario):
    condominios = list(listar_condominios_do_usuario(usuario)[:2])
    return condominios[0] if len(condominios) == 1 else None


def definir_condominio_ativo(request, condominio):
    if not usuario_tem_acesso_ao_condominio(request.user, condominio):
        raise PermissionDenied("Usuário sem acesso ao condomínio.")
    request.session[CHAVE_CONDOMINIO_ATIVO] = condominio.pk
    return condominio


def obter_condominio_ativo(request):
    if hasattr(request, "_condominio_ativo"):
        armazenado = request._condominio_ativo
        if armazenado is None:
            return None
        if usuario_tem_acesso_ao_condominio(request.user, armazenado):
            return armazenado
        request.session.pop(CHAVE_CONDOMINIO_ATIVO, None)
        del request._condominio_ativo
        request._condominios_disponiveis = tuple(
            listar_condominios_do_usuario(request.user)
        )
    condominio_id = request.session.get(CHAVE_CONDOMINIO_ATIVO)
    if condominio_id:
        condominio = Condominio.objects.filter(pk=condominio_id).first()
        if condominio and usuario_tem_acesso_ao_condominio(
            request.user, condominio
        ):
            request._condominio_ativo = condominio
            return condominio
        request.session.pop(CHAVE_CONDOMINIO_ATIVO, None)
        request._condominios_disponiveis = tuple(
            listar_condominios_do_usuario(request.user)
        )

    disponiveis = listar_condominios_do_request(request)
    unico = disponiveis[0] if len(disponiveis) == 1 else None
    if unico:
        request.session[CHAVE_CONDOMINIO_ATIVO] = unico.pk
        request._condominio_ativo = unico
        return unico
    request._condominio_ativo = None
    return None
