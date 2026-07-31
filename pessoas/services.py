from datetime import date

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from condominios.permissions import Permissao, exigir_permissao
from django.db.models import Prefetch, Q

from apartamentos.models import Apartamento
from contratos.models import Contrato

from .models import Pessoa, VinculoPessoaApartamento


def normalizar_cpf(cpf):
    cpf = "".join(
        caractere for caractere in str(cpf or "") if caractere.isdigit()
    )
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        raise ValueError("Informe um CPF válido.")

    for tamanho in (9, 10):
        soma = sum(
            int(digito) * peso
            for digito, peso in zip(
                cpf[:tamanho],
                range(tamanho + 1, 1, -1),
                strict=True,
            )
        )
        verificador = (soma * 10 % 11) % 10
        if verificador != int(cpf[tamanho]):
            raise ValueError("Informe um CPF válido.")
    return cpf


def _texto_obrigatorio(valor, mensagem):
    valor = str(valor or "").strip()
    if not valor:
        raise ValueError(mensagem)
    return valor


def _texto_opcional(valor):
    valor = str(valor or "").strip()
    return valor or None


def _validar_modelo(instancia, *, excluir=None):
    try:
        instancia.full_clean(exclude=excluir, validate_unique=False)
    except ValidationError as exc:
        raise ValueError(" ".join(exc.messages)) from exc


def _salvar(instancia, **kwargs):
    try:
        with transaction.atomic():
            instancia.save(**kwargs)
    except IntegrityError as exc:
        raise ValueError(
            "Os dados informados conflitam com um registro existente."
        ) from exc


@transaction.atomic
def cadastrar_pessoa(
    *,
    condominio,
    nome_completo,
    cpf,
    rg=None,
    email,
    telefone,
    data_nascimento=None,
    observacoes=None,
    situacao=Pessoa.Situacao.ATIVA,
):
    pessoa = Pessoa(
        condominio=condominio,
        nome_completo=_texto_obrigatorio(
            nome_completo, "Informe o nome completo."
        ),
        cpf=normalizar_cpf(cpf),
        rg=_texto_opcional(rg),
        email=_texto_obrigatorio(email, "Informe o e-mail.").lower(),
        telefone=_texto_obrigatorio(telefone, "Informe o telefone."),
        data_nascimento=data_nascimento,
        observacoes=_texto_opcional(observacoes),
        situacao=situacao,
    )
    _validar_modelo(pessoa)
    if Pessoa.objects.filter(cpf=pessoa.cpf).exists():
        raise ValueError("Já existe uma pessoa cadastrada com este CPF.")
    _salvar(pessoa, force_insert=True)
    return pessoa


@transaction.atomic
def editar_pessoa(
    pessoa_id,
    *,
    condominio,
    nome_completo,
    cpf,
    rg=None,
    email,
    telefone,
    data_nascimento=None,
    observacoes=None,
    situacao=Pessoa.Situacao.ATIVA,
):
    try:
        pessoa = (
            Pessoa.objects.select_for_update()
            .get(pk=pessoa_id, condominio=condominio)
        )
    except Pessoa.DoesNotExist as exc:
        raise ValueError("Pessoa não encontrada.") from exc

    pessoa.nome_completo = _texto_obrigatorio(
        nome_completo, "Informe o nome completo."
    )
    pessoa.cpf = normalizar_cpf(cpf)
    pessoa.rg = _texto_opcional(rg)
    pessoa.email = _texto_obrigatorio(email, "Informe o e-mail.").lower()
    pessoa.telefone = _texto_obrigatorio(
        telefone, "Informe o telefone."
    )
    pessoa.data_nascimento = data_nascimento
    pessoa.observacoes = _texto_opcional(observacoes)
    pessoa.situacao = situacao
    _validar_modelo(pessoa)
    if Pessoa.objects.filter(cpf=pessoa.cpf).exclude(pk=pessoa.pk).exists():
        raise ValueError("Já existe uma pessoa cadastrada com este CPF.")
    _salvar(pessoa)
    return pessoa


def consultar_pessoa(pessoa_id, *, condominio):
    try:
        return Pessoa.objects.get(pk=pessoa_id, condominio=condominio)
    except Pessoa.DoesNotExist as exc:
        raise ValueError("Pessoa não encontrada.") from exc


def consultar_detalhes_pessoa(pessoa_id, *, condominio):
    try:
        return (
            Pessoa.objects.filter(condominio=condominio)
            .prefetch_related(
                Prefetch(
                    "vinculos_apartamentos",
                    queryset=(
                        VinculoPessoaApartamento.objects
                        .select_related("apartamento")
                        .order_by("-ativo", "tipo", "-data_inicio", "-id")
                    ),
                ),
                Prefetch(
                    "contratos_como_contratante",
                    queryset=(
                        Contrato.objects.select_related("apartamento")
                        .order_by("-data_inicio", "-id")
                    ),
                ),
                Prefetch(
                    "contratos_como_responsavel_financeiro",
                    queryset=(
                        Contrato.objects.select_related("apartamento")
                        .order_by("-data_inicio", "-id")
                    ),
                ),
            )
            .get(pk=pessoa_id)
        )
    except Pessoa.DoesNotExist as exc:
        raise ValueError("Pessoa não encontrada.") from exc


def listar_pessoas(
    *,
    condominio,
    busca=None,
    situacao=None,
    tipo_vinculo=None,
    incluir_sensiveis=True,
):
    pessoas = Pessoa.objects.filter(condominio=condominio)
    if busca:
        busca = busca.strip()
        filtro = Q(nome_completo__icontains=busca)
        if incluir_sensiveis:
            cpf = "".join(c for c in busca if c.isdigit())
            filtro |= (
                Q(email__icontains=busca)
                | Q(telefone__icontains=busca)
            )
            if cpf:
                filtro |= Q(cpf__icontains=cpf)
        pessoas = pessoas.filter(filtro)
    if situacao:
        pessoas = pessoas.filter(situacao=situacao)
    if tipo_vinculo:
        pessoas = pessoas.filter(
            vinculos_apartamentos__tipo=tipo_vinculo,
            vinculos_apartamentos__ativo=True,
        )
    return (
        pessoas.distinct()
        .prefetch_related(
            Prefetch(
                "vinculos_apartamentos",
                queryset=(
                    VinculoPessoaApartamento.objects
                    .filter(ativo=True)
                    .select_related("apartamento")
                    .order_by("apartamento__bloco", "apartamento__numero", "tipo")
                ),
                to_attr="vinculos_ativos",
            )
        )
        .order_by("nome_completo", "id")
    )


@transaction.atomic
def criar_vinculo(
    *,
    condominio,
    pessoa_id,
    apartamento_id,
    tipo,
    data_inicio,
    usuario=None,
):
    if usuario is not None:
        exigir_permissao(
            usuario, condominio, Permissao.GERENCIAR_VINCULOS
        )
    try:
        pessoa = Pessoa.objects.select_for_update().get(
            pk=pessoa_id, condominio=condominio
        )
        apartamento = Apartamento.objects.get(
            pk=apartamento_id,
            condominio=condominio,
            ativo=True,
            arquivado=False,
        )
    except (Pessoa.DoesNotExist, Apartamento.DoesNotExist) as exc:
        raise ValueError("Pessoa ou apartamento não encontrado.") from exc
    if pessoa.situacao != Pessoa.Situacao.ATIVA:
        raise ValueError("Não é possível vincular uma pessoa inativa.")

    vinculo = VinculoPessoaApartamento(
        pessoa=pessoa,
        apartamento=apartamento,
        tipo=tipo,
        data_inicio=data_inicio,
        ativo=True,
    )
    if VinculoPessoaApartamento.objects.filter(
        pessoa=pessoa,
        apartamento=apartamento,
        tipo=tipo,
        ativo=True,
    ).exists():
        raise ValueError("Este vínculo já está ativo.")
    if (
        tipo == VinculoPessoaApartamento.Tipo.RESPONSAVEL_FINANCEIRO
        and VinculoPessoaApartamento.objects.filter(
            apartamento=apartamento,
            tipo=tipo,
            ativo=True,
        ).exists()
    ):
        raise ValueError(
            "O apartamento já possui um responsável financeiro ativo."
        )
    _validar_modelo(vinculo)
    _salvar(vinculo, force_insert=True)
    return vinculo


@transaction.atomic
def editar_vinculo(
    vinculo_id,
    *,
    condominio,
    apartamento_id,
    tipo,
    data_inicio,
    usuario=None,
):
    if usuario is not None:
        exigir_permissao(
            usuario, condominio, Permissao.GERENCIAR_VINCULOS
        )
    try:
        vinculo = (
            VinculoPessoaApartamento.objects.select_for_update()
            .select_related("pessoa", "apartamento")
            .get(pk=vinculo_id, pessoa__condominio=condominio)
        )
        apartamento = Apartamento.objects.get(
            pk=apartamento_id,
            condominio=condominio,
            ativo=True,
            arquivado=False,
        )
    except (
        VinculoPessoaApartamento.DoesNotExist,
        Apartamento.DoesNotExist,
    ) as exc:
        raise ValueError("Vínculo ou apartamento não encontrado.") from exc

    conflitos = VinculoPessoaApartamento.objects.filter(
        apartamento=apartamento,
        tipo=tipo,
        ativo=True,
    ).exclude(pk=vinculo.pk)
    if vinculo.ativo and conflitos.filter(pessoa=vinculo.pessoa).exists():
        raise ValueError("Este vínculo já está ativo.")
    if (
        vinculo.ativo
        and tipo == VinculoPessoaApartamento.Tipo.RESPONSAVEL_FINANCEIRO
        and conflitos.exists()
    ):
        raise ValueError(
            "O apartamento já possui um responsável financeiro ativo."
        )

    vinculo.apartamento = apartamento
    vinculo.tipo = tipo
    vinculo.data_inicio = data_inicio
    _validar_modelo(vinculo)
    _salvar(
        vinculo,
        update_fields=[
            "apartamento",
            "tipo",
            "data_inicio",
            "atualizado_em",
        ],
    )
    return vinculo


@transaction.atomic
def encerrar_vinculo(
    vinculo_id,
    *,
    condominio,
    data_fim=None,
    usuario=None,
):
    if usuario is not None:
        exigir_permissao(
            usuario, condominio, Permissao.GERENCIAR_VINCULOS
        )
    try:
        vinculo = (
            VinculoPessoaApartamento.objects.select_for_update()
            .select_related("pessoa", "apartamento")
            .get(pk=vinculo_id, pessoa__condominio=condominio)
        )
    except VinculoPessoaApartamento.DoesNotExist as exc:
        raise ValueError("Vínculo não encontrado.") from exc
    if not vinculo.ativo:
        raise ValueError("Este vínculo já está encerrado.")

    data_fim = data_fim or date.today()
    if data_fim < vinculo.data_inicio:
        raise ValueError(
            "A data de fim não pode anteceder a data de início."
        )
    vinculo.ativo = False
    vinculo.data_fim = data_fim
    _validar_modelo(vinculo)
    _salvar(vinculo, update_fields=["ativo", "data_fim", "atualizado_em"])
    return vinculo


def recuperar_responsavel_financeiro(apartamento, *, em=None):
    vinculos = (
        VinculoPessoaApartamento.objects
        .select_related("pessoa")
        .filter(
            apartamento=apartamento,
            tipo=VinculoPessoaApartamento.Tipo.RESPONSAVEL_FINANCEIRO,
        )
    )
    if em is None:
        vinculos = vinculos.filter(ativo=True, data_fim__isnull=True)
    else:
        vinculos = vinculos.filter(
            data_inicio__lte=em,
        ).filter(Q(data_fim__isnull=True) | Q(data_fim__gte=em))
    vinculo = vinculos.order_by("-data_inicio", "-id").first()
    return vinculo.pessoa if vinculo else None


def listar_vinculos_apartamento(apartamento):
    return (
        VinculoPessoaApartamento.objects
        .select_related("pessoa")
        .filter(apartamento=apartamento)
        .order_by("tipo", "-ativo", "-data_inicio", "-id")
    )
