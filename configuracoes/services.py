from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from .models import CHAVE_CONFIGURACAO, ConfiguracaoCondominio
from .validators import formatar_cep, formatar_cnpj


@transaction.atomic
def obter_configuracao(request=None):
    if request is not None:
        configuracao_em_memoria = getattr(
            request,
            "_configuracao_condominio",
            None,
        )
        if configuracao_em_memoria is not None:
            return configuracao_em_memoria

    configuracao, _ = ConfiguracaoCondominio.objects.get_or_create(
        chave=CHAVE_CONFIGURACAO,
    )
    if request is not None:
        request._configuracao_condominio = configuracao
    return configuracao


@transaction.atomic
def atualizar_configuracao(dados):
    configuracao, _ = (
        ConfiguracaoCondominio.objects
        .select_for_update()
        .get_or_create(chave=CHAVE_CONFIGURACAO)
    )

    campos_editaveis = {
        campo.name
        for campo in ConfiguracaoCondominio._meta.fields
        if campo.editable and campo.name not in {"id", "chave"}
    }
    for campo in campos_editaveis:
        if campo in dados:
            valor = dados[campo]
            if isinstance(valor, str):
                valor = valor.strip()
            if campo == "cnpj":
                valor = formatar_cnpj(valor)
            elif campo == "cep":
                valor = formatar_cep(valor)
            elif campo == "estado" and isinstance(valor, str):
                valor = valor.upper()
            setattr(configuracao, campo, None if valor is False else valor)

    try:
        configuracao.full_clean()
        configuracao.save()
    except ValidationError as exc:
        raise ValueError(" ".join(exc.messages)) from exc
    except IntegrityError as exc:
        raise ValueError(
            "As configurações violam uma regra de integridade."
        ) from exc

    return configuracao
