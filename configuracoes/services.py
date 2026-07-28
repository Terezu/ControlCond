from django.core.exceptions import ValidationError
from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q

from .models import (
    AuditoriaConfiguracao,
    CHAVE_CONFIGURACAO,
    ConfiguracaoCondominio,
    ConfiguracaoGlobal,
    FaixaTarifaAgua,
    TabelaTarifariaAgua,
    TarifaGas,
)
from .forms import CAMPOS_INSTITUCIONAIS, CAMPOS_OPERACIONAIS
from .validators import formatar_cep, formatar_cnpj
from condominios.permissions import Permissao, exigir_permissao, papel_atual


@transaction.atomic
def obter_configuracao(condominio):
    if condominio is None:
        raise ValueError("Informe o condomínio para recuperar as configurações.")
    configuracao, _ = ConfiguracaoCondominio.objects.get_or_create(
        condominio=condominio,
        defaults={"nome": condominio.nome},
    )
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


def obter_tabela_agua_vigente(condominio, mes, ano):
    referencia = data_referencia_tarifaria(mes, ano)
    tabela = (
        _vigente_em(
            TabelaTarifariaAgua.objects.filter(condominio=condominio),
            referencia,
        )
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


def obter_tarifa_gas_vigente(condominio, mes, ano):
    referencia = data_referencia_tarifaria(mes, ano)
    tarifa = (
        _vigente_em(
            TarifaGas.objects.filter(condominio=condominio),
            referencia,
        )
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


def obter_faixas_agua_ativas(condominio, mes=None, ano=None):
    if condominio is None:
        from condominios.models import Condominio
        condominio = Condominio.objects.order_by("id").first()
    if mes is None or ano is None:
        hoje = date.today()
        mes, ano = hoje.month, hoje.year
    return validar_tabela_agua(
        obter_tabela_agua_vigente(condominio, mes, ano)
    )


@transaction.atomic
def salvar_regra_vigencia(instancia, *, usuario=None):
    if usuario is not None:
        exigir_permissao(
            usuario,
            instancia.condominio,
            Permissao.ALTERAR_CONFIGURACOES_OPERACIONAIS,
        )
    campos_auditoria = tuple(
        campo.name for campo in instancia._meta.fields
        if campo.name not in {"id", "condominio"}
    )
    anteriores = {}
    if usuario is not None and instancia.pk:
        anterior = type(instancia).objects.filter(pk=instancia.pk).first()
        if anterior:
            anteriores = _snapshot(anterior, campos_auditoria)
    type(instancia).objects.select_for_update().all()
    instancia.full_clean()
    instancia.save()
    if usuario is not None:
        _registrar_auditoria(
            usuario=usuario,
            condominio=instancia.condominio,
            tipo=AuditoriaConfiguracao.Tipo.OPERACIONAL,
            anteriores=anteriores,
            novos=_snapshot(instancia, campos_auditoria),
            origem="painel_tarifas",
        )
    return instancia


@transaction.atomic
def atualizar_configuracao(condominio, dados):
    configuracao, _ = (
        ConfiguracaoCondominio.objects
        .select_for_update()
        .get_or_create(
            condominio=condominio,
            defaults={"nome": condominio.nome},
        )
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
        _sincronizar_tarifa_gas_legada(
            condominio, configuracao.valor_m3_gas
        )
    return configuracao


def _valor_auditavel(valor):
    if hasattr(valor, "name"):
        return valor.name
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return str(valor)
    return valor


def _snapshot(instancia, campos):
    return {
        campo: _valor_auditavel(getattr(instancia, campo))
        for campo in campos
    }


def _registrar_auditoria(
    *, usuario, condominio, tipo, anteriores, novos, origem
):
    cargo = (
        "global"
        if usuario.is_superuser
        else (papel_atual(usuario, condominio) or "")
    )
    AuditoriaConfiguracao.objects.create(
        executor=usuario,
        condominio=condominio,
        cargo=cargo,
        tipo=tipo,
        valores_anteriores=anteriores,
        valores_novos=novos,
        origem=origem,
    )


@transaction.atomic
def atualizar_configuracao_institucional(
    condominio, dados, *, usuario, origem="painel"
):
    exigir_permissao(
        usuario, condominio, Permissao.ALTERAR_CONFIGURACOES_INSTITUCIONAIS
    )
    configuracao = obter_configuracao(condominio)
    anteriores = _snapshot(configuracao, CAMPOS_INSTITUCIONAIS)
    configuracao = atualizar_configuracao(
        condominio,
        {campo: valor for campo, valor in dados.items()
         if campo in CAMPOS_INSTITUCIONAIS},
    )
    novos = _snapshot(configuracao, CAMPOS_INSTITUCIONAIS)
    _registrar_auditoria(
        usuario=usuario,
        condominio=condominio,
        tipo=AuditoriaConfiguracao.Tipo.INSTITUCIONAL,
        anteriores=anteriores,
        novos=novos,
        origem=origem,
    )
    return configuracao


@transaction.atomic
def atualizar_configuracao_operacional(
    condominio, dados, *, usuario, origem="painel"
):
    exigir_permissao(
        usuario, condominio, Permissao.ALTERAR_CONFIGURACOES_OPERACIONAIS
    )
    configuracao = obter_configuracao(condominio)
    anteriores = _snapshot(configuracao, CAMPOS_OPERACIONAIS)
    configuracao = atualizar_configuracao(
        condominio,
        {campo: valor for campo, valor in dados.items()
         if campo in CAMPOS_OPERACIONAIS},
    )
    novos = _snapshot(configuracao, CAMPOS_OPERACIONAIS)
    _registrar_auditoria(
        usuario=usuario,
        condominio=condominio,
        tipo=AuditoriaConfiguracao.Tipo.OPERACIONAL,
        anteriores=anteriores,
        novos=novos,
        origem=origem,
    )
    return configuracao


def obter_configuracao_global():
    configuracao, _ = ConfiguracaoGlobal.objects.get_or_create(chave=1)
    return configuracao


@transaction.atomic
def atualizar_configuracao_global(dados, *, usuario, origem="painel"):
    if not usuario.is_superuser:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied(
            "Somente Administradores Globais alteram a plataforma."
        )
    configuracao = (
        ConfiguracaoGlobal.objects.select_for_update().filter(chave=1).first()
        or ConfiguracaoGlobal(chave=1)
    )
    campos = ("dias_retencao_padrao", "modo_manutencao", "mensagem_manutencao")
    anteriores = _snapshot(configuracao, campos)
    for campo in campos:
        if campo in dados:
            setattr(configuracao, campo, dados[campo])
    configuracao.full_clean()
    configuracao.save()
    novos = _snapshot(configuracao, campos)
    _registrar_auditoria(
        usuario=usuario,
        condominio=None,
        tipo=AuditoriaConfiguracao.Tipo.GLOBAL,
        anteriores=anteriores,
        novos=novos,
        origem=origem,
    )
    return configuracao


def _sincronizar_tarifa_gas_legada(condominio, valor):
    hoje = date.today()
    vigente = _vigente_em(
        TarifaGas.objects.select_for_update().filter(condominio=condominio),
        hoje,
    ).first()
    if vigente and vigente.valor_por_m3 == valor:
        return vigente
    if vigente:
        from datetime import timedelta
        vigente.data_fim_vigencia = hoje - timedelta(days=1)
        vigente.save(update_fields=["data_fim_vigencia", "atualizado_em"])
    tarifa = TarifaGas(
        nome=f"Tarifa de gás {hoje:%m/%Y}",
        condominio=condominio,
        valor_por_m3=valor,
        data_inicio_vigencia=hoje,
        ativa=True,
        observacoes="Criada pela ponte de compatibilidade da configuração legada.",
    )
    tarifa.full_clean()
    tarifa.save()
    return tarifa
