from dataclasses import dataclass

from django.db.models import Prefetch

from contratos.models import Contrato
from contratos.selectors import contratos_para_apartamentos
from pessoas.models import VinculoPessoaApartamento

from .models import Apartamento


@dataclass
class PessoaVinculadaResumo:
    pessoa: object
    vinculos: list
    tipos_ativos: list
    tipos_historicos: list
    data_inicio: object
    ativo: bool
    responsavel_financeiro: bool
    contratante: bool

    @property
    def cpf_mascarado(self):
        cpf = self.pessoa.cpf
        if len(cpf) != 11:
            return "CPF não informado"
        return f"***.{cpf[3:6]}.{cpf[6:9]}-**"

    @property
    def contato_principal(self):
        return self.pessoa.telefone or self.pessoa.email


@dataclass
class PainelApartamento:
    pessoas: list
    pessoa_principal: object
    responsavel_financeiro: object
    contrato_atual: object
    contrato_futuro: object
    ultimo_contrato: object
    indicadores_ocupacao: list
    ocupado: bool
    total_vinculos_ativos: int

    @property
    def possui_contrato(self):
        return self.contrato_atual is not None


def _queryset_vinculos():
    return (
        VinculoPessoaApartamento.objects.select_related("pessoa")
        .order_by("-ativo", "pessoa__nome_completo", "tipo", "-data_inicio")
    )


def listar_apartamentos_operacionais(
    condominio, *, numero=None, bloco=None
):
    apartamentos = Apartamento.objects.filter(
        condominio=condominio, ativo=True, arquivado=False
    )
    if numero:
        apartamentos = apartamentos.filter(numero__icontains=numero.strip())
    if bloco:
        apartamentos = apartamentos.filter(bloco__iexact=bloco.strip())
    return apartamentos.prefetch_related(
        Prefetch(
            "vinculos_pessoas",
            queryset=_queryset_vinculos(),
            to_attr="vinculos_operacionais",
        ),
        Prefetch(
            "contratos",
            queryset=contratos_para_apartamentos(condominio),
            to_attr="contratos_operacionais",
        ),
    ).order_by("bloco", "numero", "id")


def _selecionar_pessoa_principal(vinculos, contrato_atual):
    ativos = [item for item in vinculos if item.ativo]
    prioridades = []
    if contrato_atual:
        prioridades.append(
            (
                VinculoPessoaApartamento.Tipo.INQUILINO,
                contrato_atual.pessoa_contratante_id,
            )
        )
    prioridades.extend(
        [
            (VinculoPessoaApartamento.Tipo.MORADOR, None),
            (VinculoPessoaApartamento.Tipo.PROPRIETARIO, None),
        ]
    )
    for tipo, pessoa_id in prioridades:
        for vinculo in ativos:
            if vinculo.tipo == tipo and (
                pessoa_id is None or vinculo.pessoa_id == pessoa_id
            ):
                return vinculo.pessoa
    return None


def montar_painel_apartamento(apartamento):
    vinculos_prefetch = getattr(
        apartamento, "vinculos_operacionais", None
    )
    gerenciador_vinculos = getattr(
        apartamento, "vinculos_pessoas", None
    )
    vinculos = list(
        vinculos_prefetch
        if vinculos_prefetch is not None
        else (
            gerenciador_vinculos.select_related("pessoa").all()
            if gerenciador_vinculos is not None
            else []
        )
    )
    contratos_prefetch = getattr(
        apartamento, "contratos_operacionais", None
    )
    gerenciador_contratos = getattr(apartamento, "contratos", None)
    contratos = list(
        contratos_prefetch
        if contratos_prefetch is not None
        else (
            gerenciador_contratos.select_related(
                "pessoa_contratante", "responsavel_financeiro"
            ).all()
            if gerenciador_contratos is not None
            else []
        )
    )
    for contrato in contratos:
        contrato.situacao = contrato.calcular_situacao()
    contrato_atual = next(
        (item for item in contratos if item.situacao == Contrato.Situacao.ATIVO),
        None,
    )
    contrato_futuro = next(
        (item for item in contratos if item.situacao == Contrato.Situacao.FUTURO),
        None,
    )
    ativos = [item for item in vinculos if item.ativo]
    responsavel = next(
        (
            item.pessoa
            for item in ativos
            if item.tipo
            == VinculoPessoaApartamento.Tipo.RESPONSAVEL_FINANCEIRO
        ),
        None,
    )
    pessoa_principal = _selecionar_pessoa_principal(
        vinculos, contrato_atual
    )
    ocupado = bool(
        contrato_atual
        or any(
            item.tipo
            in {
                VinculoPessoaApartamento.Tipo.MORADOR,
                VinculoPessoaApartamento.Tipo.INQUILINO,
            }
            for item in ativos
        )
    )
    indicadores = [("success" if ocupado else "secondary", "Ocupado" if ocupado else "Desocupado")]
    if not contrato_atual and contrato_futuro:
        indicadores.append(("info", "Contrato futuro"))
    if contrato_atual and contrato_atual.proximo_vencimento:
        indicadores.append(("warning", "Contrato próximo do vencimento"))
    if responsavel is None:
        indicadores.append(("danger", "Sem responsável financeiro"))

    pessoas_por_id = {}
    contratantes = {
        item.pessoa_contratante_id for item in contratos
    }
    for vinculo in vinculos:
        grupo = pessoas_por_id.setdefault(
            vinculo.pessoa_id,
            {"pessoa": vinculo.pessoa, "vinculos": []},
        )
        grupo["vinculos"].append(vinculo)
    pessoas = []
    for pessoa_id, grupo in pessoas_por_id.items():
        vinculos_pessoa = grupo["vinculos"]
        ativos_pessoa = [item for item in vinculos_pessoa if item.ativo]
        pessoas.append(
            PessoaVinculadaResumo(
                pessoa=grupo["pessoa"],
                vinculos=vinculos_pessoa,
                tipos_ativos=[
                    item.get_tipo_display() for item in ativos_pessoa
                ],
                tipos_historicos=[
                    item.get_tipo_display()
                    for item in vinculos_pessoa
                    if not item.ativo
                ],
                data_inicio=min(
                    item.data_inicio for item in vinculos_pessoa
                ),
                ativo=bool(ativos_pessoa),
                responsavel_financeiro=any(
                    item.tipo
                    == VinculoPessoaApartamento.Tipo.RESPONSAVEL_FINANCEIRO
                    for item in ativos_pessoa
                ),
                contratante=pessoa_id in contratantes,
            )
        )
    pessoas.sort(key=lambda item: (not item.ativo, item.pessoa.nome_completo))
    return PainelApartamento(
        pessoas=pessoas,
        pessoa_principal=pessoa_principal,
        responsavel_financeiro=responsavel,
        contrato_atual=contrato_atual,
        contrato_futuro=contrato_futuro,
        ultimo_contrato=contratos[0] if contratos else None,
        indicadores_ocupacao=indicadores,
        ocupado=ocupado,
        total_vinculos_ativos=len(ativos),
    )


def enriquecer_apartamentos(apartamentos):
    for apartamento in apartamentos:
        apartamento.painel = montar_painel_apartamento(apartamento)
    return apartamentos
