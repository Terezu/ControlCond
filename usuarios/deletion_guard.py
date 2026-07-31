from contextlib import contextmanager
from contextvars import ContextVar


_EXCLUSAO_USUARIO_AUTORIZADA = ContextVar(
    "exclusao_usuario_autorizada", default=False
)


def exclusao_usuario_esta_autorizada():
    return _EXCLUSAO_USUARIO_AUTORIZADA.get()


@contextmanager
def autorizar_exclusao_usuario():
    token = _EXCLUSAO_USUARIO_AUTORIZADA.set(True)
    try:
        yield
    finally:
        _EXCLUSAO_USUARIO_AUTORIZADA.reset(token)
