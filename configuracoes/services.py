from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from .models import (
    CHAVE_CONFIGURACAO,
    ConfiguracaoCondominio,
    FaixaTarifaAgua,
)
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


obter_configuracoes = obter_configuracao


def obter_faixas_agua_ativas():
    faixas = tuple(
        FaixaTarifaAgua.objects
        .filter(ativa=True)
        .order_by("ordem", "id")
    )
    if not faixas:
        raise ValueError(
            "A tabela de cobrança de água não está configurada. "
            "Cadastre ao menos uma faixa ativa nas Configurações."
        )
    if faixas[0].consumo_inicial != 0:
        raise ValueError(
            "A tabela de água é inválida: a primeira faixa deve começar em zero."
        )
    for indice, faixa in enumerate(faixas):
        if faixa.consumo_final is None and indice != len(faixas) - 1:
            raise ValueError(
                "A tabela de água é inválida: somente a última faixa "
                "pode ter final aberto."
            )
        if indice:
            anterior = faixas[indice - 1]
            if (
                anterior.consumo_final is None
                or faixa.consumo_inicial != anterior.consumo_final + 1
            ):
                raise ValueError(
                    "A tabela de água possui lacunas ou sobreposições."
                )
    return faixas


@transaction.atomic
def atualizar_configuracao(dados):
    configuracao, _ = (
        ConfiguracaoCondominio.objects
        .select_for_update()
        .get_or_create(chave=CHAVE_CONFIGURACAO)
    )

    campos_editaveis = {
        campo.name: campo
        for campo in ConfiguracaoCondominio._meta.fields
        if campo.editable and campo.name not in {"id", "chave"}
    }
    for campo, definicao_campo in campos_editaveis.items():
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
            if valor is False and definicao_campo.get_internal_type() in {
                "FileField",
                "ImageField",
            }:
                valor = None
            setattr(configuracao, campo, valor)

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
