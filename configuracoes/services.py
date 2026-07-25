from django.core.exceptions import ValidationError
from datetime import date

from django.db import IntegrityError, transaction
from django.db.models import Q

from .models import (
    CHAVE_CONFIGURACAO,
    ConfiguracaoCondominio,
    FaixaTarifaAgua,
    TabelaTarifariaAgua,
    TarifaGas,
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


class TarifaNaoConfiguradaError(ValueError):
    pass


class ConsumoSemFaixaError(ValueError):
    pass


def data_referencia_tarifaria(mes, ano):
    if isinstance(mes, bool) or not isinstance(mes, int) or not 1 <= mes <= 12:
        raise ValueError("O mês deve estar entre 1 e 12.")
    if isinstance(ano, bool) or not isinstance(ano, int) or not 2000 <= ano <= 9999:
        raise ValueError("Informe um ano válido.")
    return date(ano, mes, 1)


def _vigente_em(queryset, referencia):
    return queryset.filter(
        ativa=True,
        data_inicio_vigencia__lte=referencia,
    ).filter(
        Q(data_fim_vigencia__isnull=True)
        | Q(data_fim_vigencia__gte=referencia)
    )


def obter_tabela_agua_vigente(mes, ano):
    referencia = data_referencia_tarifaria(mes, ano)
    tabela = (
        _vigente_em(TabelaTarifariaAgua.objects, referencia)
        .prefetch_related("faixas")
        .order_by("-data_inicio_vigencia", "-id")
        .first()
    )
    if tabela is None:
        raise TarifaNaoConfiguradaError(
            f"Nenhuma tabela de água vigente para {mes:02d}/{ano}."
        )
    validar_tabela_agua(tabela)
    return tabela


def obter_tarifa_gas_vigente(mes, ano):
    referencia = data_referencia_tarifaria(mes, ano)
    tarifa = (
        _vigente_em(TarifaGas.objects, referencia)
        .order_by("-data_inicio_vigencia", "-id")
        .first()
    )
    if tarifa is None:
        raise TarifaNaoConfiguradaError(
            f"Nenhuma tarifa de gás vigente para {mes:02d}/{ano}."
        )
    return tarifa


def validar_tabela_agua(tabela):
    faixas = tuple(
        tabela.faixas
        .filter(ativa=True)
        .order_by("ordem", "id")
    )
    if not faixas:
        raise TarifaNaoConfiguradaError(
            "A tabela de cobrança de água não está configurada. "
            "Cadastre ao menos uma faixa ativa."
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


def obter_faixas_agua_ativas(mes=None, ano=None):
    if mes is None or ano is None:
        hoje = date.today()
        mes, ano = hoje.month, hoje.year
    return validar_tabela_agua(obter_tabela_agua_vigente(mes, ano))


@transaction.atomic
def salvar_regra_vigencia(instancia):
    type(instancia).objects.select_for_update().all()
    instancia.full_clean()
    instancia.save()
    return instancia


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

    if "valor_m3_gas" in dados:
        _sincronizar_tarifa_gas_legada(configuracao.valor_m3_gas)
    return configuracao


def _sincronizar_tarifa_gas_legada(valor):
    hoje = date.today()
    vigente = _vigente_em(TarifaGas.objects.select_for_update(), hoje).first()
    if vigente and vigente.valor_por_m3 == valor:
        return vigente
    if vigente:
        from datetime import timedelta
        vigente.data_fim_vigencia = hoje - timedelta(days=1)
        vigente.save(update_fields=["data_fim_vigencia", "atualizado_em"])
    tarifa = TarifaGas(
        nome=f"Tarifa de gás {hoje:%m/%Y}",
        valor_por_m3=valor,
        data_inicio_vigencia=hoje,
        ativa=True,
        observacoes="Criada pela ponte de compatibilidade da configuração legada.",
    )
    tarifa.full_clean()
    tarifa.save()
    return tarifa
