from condominios.permissions import Permissao, usuario_possui_permissao


def usuario_pode_rescindir_contrato(usuario, condominio):
    return usuario_possui_permissao(
        usuario, condominio, Permissao.RESCINDIR_CONTRATO
    )
