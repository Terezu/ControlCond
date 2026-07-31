from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apartamentos.models import Apartamento
from pessoas.models import Pessoa, VinculoPessoaApartamento

from .models import (
    AuditoriaRescisaoContrato,
    Contrato,
    VinculoFinanceiroContrato,
)
from .permissions import usuario_pode_rescindir_contrato
from .selectors import contratos_do_condominio
from condominios.permissions import Permissao, exigir_permissao


def _obter_entidades(condominio, apartamento_id, contratante_id, responsavel_id):
    try:
        apartamento = Apartamento.objects.get(
            pk=apartamento_id,
            condominio=condominio,
            ativo=True,
            arquivado=False,
        )
        contratante = Pessoa.objects.get(
            pk=contratante_id,
            condominio=condominio,
            situacao=Pessoa.Situacao.ATIVA,
        )
        responsavel = Pessoa.objects.get(
            pk=responsavel_id,
            condominio=condominio,
            situacao=Pessoa.Situacao.ATIVA,
        )
    except (Apartamento.DoesNotExist, Pessoa.DoesNotExist) as exc:
        raise ValueError(
            "Apartamento ou pessoa não encontrado no condomínio ativo."
        ) from exc
    return apartamento, contratante, responsavel


def _validar_periodo(data_inicio, data_termino):
    if not data_inicio or not data_termino:
        raise ValueError("Informe as datas de início e término.")
    if data_termino <= data_inicio:
        raise ValueError(
            "A data de término deve ser posterior à data de início."
        )


def _validar_sobreposicao(apartamento, data_inicio, data_termino, excluir=None):
    conflitos = Contrato.objects.filter(
        apartamento=apartamento,
        data_rescisao__isnull=True,
        data_inicio__lte=data_termino,
        data_termino__gte=data_inicio,
    )
    if excluir:
        conflitos = conflitos.exclude(pk=excluir)
    if conflitos.exists():
        raise ValueError(
            "Já existe um contrato com período sobreposto para este apartamento."
        )


def _validar_modelo(contrato):
    try:
        contrato.full_clean(validate_unique=False)
    except ValidationError as exc:
        raise ValueError(" ".join(exc.messages)) from exc


def _assegurar_responsavel_financeiro(
    pessoa, apartamento, data_inicio
):
    tipo = VinculoPessoaApartamento.Tipo.RESPONSAVEL_FINANCEIRO
    atual = (
        VinculoPessoaApartamento.objects.select_for_update()
        .filter(apartamento=apartamento, tipo=tipo, ativo=True)
        .first()
    )
    if atual and atual.pessoa_id == pessoa.id:
        if data_inicio < atual.data_inicio:
            atual.data_inicio = data_inicio
            atual.save(update_fields=["data_inicio", "atualizado_em"])
        return atual, False
    if atual:
        atual.ativo = False
        atual.data_fim = max(
            atual.data_inicio, data_inicio - timedelta(days=1)
        )
        atual.save(update_fields=["ativo", "data_fim", "atualizado_em"])
    return VinculoPessoaApartamento.objects.create(
        pessoa=pessoa,
        apartamento=apartamento,
        tipo=tipo,
        data_inicio=data_inicio,
        ativo=True,
    ), True


def _registrar_dependencia_financeira(contrato, vinculo, criado):
    dependencia = VinculoFinanceiroContrato.objects.filter(
        contrato=contrato
    ).first()
    if dependencia is None:
        VinculoFinanceiroContrato.objects.create(
            contrato=contrato,
            vinculo=vinculo,
            criado_pelo_contrato=criado,
        )
    else:
        mesma_origem = (
            dependencia.vinculo_id == vinculo.id
            and dependencia.criado_pelo_contrato
        )
        dependencia.vinculo = vinculo
        dependencia.criado_pelo_contrato = criado or mesma_origem
        dependencia.save(
            update_fields=["vinculo", "criado_pelo_contrato"]
        )


@transaction.atomic
def cadastrar_contrato(
    *,
    condominio,
    apartamento_id,
    pessoa_contratante_id,
    responsavel_financeiro_id,
    data_inicio,
    data_termino,
    observacoes=None,
    usuario=None,
):
    if usuario is not None:
        exigir_permissao(
            usuario, condominio, Permissao.GERENCIAR_CONTRATOS
        )
    _validar_periodo(data_inicio, data_termino)
    apartamento, contratante, responsavel = _obter_entidades(
        condominio,
        apartamento_id,
        pessoa_contratante_id,
        responsavel_financeiro_id,
    )
    Apartamento.objects.select_for_update().get(pk=apartamento.pk)
    _validar_sobreposicao(apartamento, data_inicio, data_termino)
    contrato = Contrato(
        condominio=condominio,
        apartamento=apartamento,
        pessoa_contratante=contratante,
        responsavel_financeiro=responsavel,
        data_inicio=data_inicio,
        data_termino=data_termino,
        observacoes=(observacoes or "").strip() or None,
    )
    _validar_modelo(contrato)
    try:
        contrato.save(force_insert=True)
    except IntegrityError as exc:
        raise ValueError("O contrato viola uma regra de integridade.") from exc
    vinculo, criado = _assegurar_responsavel_financeiro(
        responsavel, apartamento, data_inicio
    )
    _registrar_dependencia_financeira(contrato, vinculo, criado)
    return contrato


@transaction.atomic
def editar_contrato(
    contrato_id,
    *,
    condominio,
    apartamento_id,
    pessoa_contratante_id,
    responsavel_financeiro_id,
    data_inicio,
    data_termino,
    observacoes=None,
    usuario=None,
):
    if usuario is not None:
        exigir_permissao(
            usuario, condominio, Permissao.GERENCIAR_CONTRATOS
        )
    try:
        contrato = Contrato.objects.select_for_update().get(
            pk=contrato_id, condominio=condominio
        )
    except Contrato.DoesNotExist as exc:
        raise ValueError("Contrato não encontrado.") from exc
    if contrato.situacao == Contrato.Situacao.RESCINDIDO:
        raise ValueError("Um contrato rescindido não pode ser editado.")
    _validar_periodo(data_inicio, data_termino)
    apartamento, contratante, responsavel = _obter_entidades(
        condominio,
        apartamento_id,
        pessoa_contratante_id,
        responsavel_financeiro_id,
    )
    _validar_sobreposicao(
        apartamento, data_inicio, data_termino, excluir=contrato.pk
    )
    contrato.apartamento = apartamento
    contrato.pessoa_contratante = contratante
    contrato.responsavel_financeiro = responsavel
    contrato.data_inicio = data_inicio
    contrato.data_termino = data_termino
    contrato.observacoes = (observacoes or "").strip() or None
    contrato.situacao = contrato.calcular_situacao()
    _validar_modelo(contrato)
    contrato.save()
    vinculo, criado = _assegurar_responsavel_financeiro(
        responsavel, apartamento, data_inicio
    )
    _registrar_dependencia_financeira(contrato, vinculo, criado)
    return contrato


def consultar_contrato(contrato_id, *, condominio):
    try:
        contrato = contratos_do_condominio(condominio).get(pk=contrato_id)
    except Contrato.DoesNotExist as exc:
        raise ValueError("Contrato não encontrado.") from exc
    situacao = contrato.calcular_situacao()
    if contrato.situacao != situacao:
        Contrato.objects.filter(pk=contrato.pk).update(situacao=situacao)
        contrato.situacao = situacao
    return contrato


@transaction.atomic
def rescindir_contrato(
    contrato_id,
    *,
    condominio,
    usuario,
    justificativa,
    data_rescisao=None,
):
    if not usuario_pode_rescindir_contrato(usuario, condominio):
        raise PermissionDenied(
            "Somente proprietários podem rescindir contratos."
        )
    justificativa = str(justificativa or "").strip()
    if not justificativa:
        raise ValueError("Informe a justificativa da rescisão.")
    try:
        contrato = Contrato.objects.select_for_update().get(
            pk=contrato_id, condominio=condominio
        )
    except Contrato.DoesNotExist as exc:
        raise ValueError("Contrato não encontrado.") from exc
    if contrato.data_rescisao or contrato.situacao == Contrato.Situacao.RESCINDIDO:
        raise ValueError("Este contrato já foi rescindido.")
    situacao_anterior = contrato.calcular_situacao()
    if situacao_anterior == Contrato.Situacao.ENCERRADO:
        raise ValueError(
            "Um contrato encerrado naturalmente não pode ser rescindido."
        )
    agora = timezone.now()
    contrato.data_rescisao = data_rescisao or timezone.localdate()
    contrato.justificativa_rescisao = justificativa
    contrato.usuario_rescisao = usuario
    contrato.rescindido_em = agora
    contrato.situacao = Contrato.Situacao.RESCINDIDO
    _validar_modelo(contrato)
    contrato.save(
        update_fields=[
            "data_rescisao",
            "justificativa_rescisao",
            "usuario_rescisao",
            "rescindido_em",
            "situacao",
            "atualizado_em",
        ]
    )
    vinculo_encerrado = None
    dependencia = (
        VinculoFinanceiroContrato.objects.select_for_update()
        .select_related("vinculo")
        .filter(contrato=contrato)
        .first()
    )
    if dependencia and dependencia.criado_pelo_contrato:
        vinculo = dependencia.vinculo
        outro_contrato_dependente = (
            VinculoFinanceiroContrato.objects.filter(vinculo=vinculo)
            .exclude(contrato=contrato)
            .filter(
                contrato__data_rescisao__isnull=True,
                contrato__data_termino__gte=timezone.localdate(),
            )
            .exists()
        )
        if vinculo.ativo and not outro_contrato_dependente:
            vinculo.ativo = False
            vinculo.data_fim = max(
                vinculo.data_inicio, contrato.data_rescisao
            )
            vinculo.save(
                update_fields=["ativo", "data_fim", "atualizado_em"]
            )
            vinculo_encerrado = vinculo
    AuditoriaRescisaoContrato.objects.create(
        contrato=contrato,
        condominio=contrato.condominio,
        apartamento=contrato.apartamento,
        executor=usuario,
        responsavel_financeiro=contrato.responsavel_financeiro,
        vinculo_financeiro_encerrado=vinculo_encerrado,
        situacao_anterior=situacao_anterior,
        situacao_posterior=Contrato.Situacao.RESCINDIDO,
        justificativa=justificativa,
    )
    return contrato
