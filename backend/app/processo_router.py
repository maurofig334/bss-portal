"""
/processos — benefícios.

GET  /processos                        → lista com filtros
GET  /processos/{id}/detalhe|documentos|pagamentos|mensagens
POST /processos/{id}/mensagens         → escreve no canal (empresa ↔ analista)
GET  /processos/aguardando-resposta/contagem → número do sino
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from .auth import UsuarioInfo, usuario_logado
from . import processo_repo


router = APIRouter(prefix="/processos", tags=["processos"])


@router.get("")
def listar(
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
    busca: str | None = None,
    status: str | None = None,
    status_categoria: str | None = None,
    tipo: str | None = None,
    id_empresa: int | None = None,
    id_sindicato: int | None = None,
    aguardando_resposta: bool = False,
    pagina: int = 1,
    por_pagina: int = 50,
    ordem: str = "criado_em",
    desc: bool = True,
):
    # ESCOPO ≠ FILTRO.
    #
    # O escopo é o conjunto que o usuário PODE ver (vem do JWT). O filtro é o
    # que ele ESCOLHEU ver (vem da tela). Antes o router confundia os dois:
    # sem filtro, usava `usuario.empresas[0]` como se fosse escopo — e um
    # gestor de 11 CNPJs via os benefícios de um só, escolhido pelo banco.
    #
    # O portal legado não tem "empresa atual": lista tudo que o usuário
    # administra, com a empresa como coluna. É o comportamento correto.
    ids_empresa: list[int] | None = None
    if usuario.perfil == "empresa":
        if not usuario.empresas:
            return {"linhas": [], "total": 0, "pagina": 1,
                    "por_pagina": por_pagina, "paginas": 0}
        if id_empresa is not None and id_empresa not in usuario.empresas:
            raise HTTPException(403, "Empresa fora do escopo")
        # Escopo sempre aplicado, mesmo com filtro: o filtro estreita, nunca alarga.
        ids_empresa = usuario.empresas
    elif usuario.perfil == "sindicato":
        if not usuario.sindicatos:
            return {"linhas": [], "total": 0, "pagina": 1,
                    "por_pagina": por_pagina, "paginas": 0}
        if id_sindicato is None:
            id_sindicato = usuario.sindicatos[0]
        elif id_sindicato not in usuario.sindicatos:
            raise HTTPException(403, "Sindicato fora do escopo")

    return processo_repo.listar(
        busca=busca, status=status, status_categoria=status_categoria, tipo=tipo,
        id_empresa=id_empresa, ids_empresa=ids_empresa, id_sindicato=id_sindicato,
        aguardando_resposta=aguardando_resposta,
        pagina=pagina, por_pagina=por_pagina, ordem=ordem, desc=desc,
    )


def _processo_no_escopo(id_processo: int, usuario: UsuarioInfo) -> dict:
    """Busca o processo e aplica RLS por perfil. Levanta 404/403."""
    p = processo_repo.buscar_detalhe(id_processo)
    if not p:
        raise HTTPException(404, "Processo não encontrado")
    if usuario.perfil == "empresa" and p.get("id_empresa") not in usuario.empresas:
        raise HTTPException(403, "Processo fora do escopo")
    if usuario.perfil == "sindicato" and p.get("id_sindicato") not in usuario.sindicatos:
        raise HTTPException(403, "Processo fora do escopo")
    return p


@router.get("/{id_processo}/detalhe")
def detalhe_completo(
    id_processo: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """Cabeçalho do benefício: dados, beneficiário, endereço e dados bancários."""
    return _processo_no_escopo(id_processo, usuario)


@router.get("/{id_processo}/documentos")
def documentos(
    id_processo: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """Checklist de documentos: o que o tipo exige x o que foi anexado."""
    p = _processo_no_escopo(id_processo, usuario)
    return processo_repo.listar_documentos(id_processo, p.get("id_tipo_beneficio"))


@router.get("/{id_processo}/pagamentos")
def pagamentos(
    id_processo: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """Parcelas de contas a pagar do processo."""
    _processo_no_escopo(id_processo, usuario)
    return processo_repo.listar_pagamentos(id_processo)


@router.get("/{id_processo}/mensagens")
def mensagens(
    id_processo: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """
    Canal de mensagens do processo. Só a equipe da BSS vê as mensagens
    marcadas como internas.

    A checagem é LISTA BRANCA (`in PERFIS_INTERNOS`), não `!= "empresa"`.
    Com a lista negra anterior, qualquer perfil que não fosse exatamente
    'empresa' — sindicato, contabilidade, e qualquer perfil criado no futuro —
    lia as notas internas da equipe. Perfil novo deve nascer sem acesso e
    ganhá-lo de propósito, nunca o contrário.
    """
    _processo_no_escopo(id_processo, usuario)
    incluir_internas = usuario.perfil in processo_repo.PERFIS_INTERNOS
    return processo_repo.listar_mensagens(id_processo, incluir_internas=incluir_internas)


class MensagemIn(BaseModel):
    corpo: str
    # Nota interna: conversa da equipe, invisível pro cliente. Só internos
    # podem marcar — o router ignora o que vier de externo.
    interno: bool = False
    # Mudança de status junto com a resposta (opcional, só internos).
    # Decisão da BSS: "analista escolhe ao responder".
    status_novo: str | None = None

    @field_validator("corpo")
    @classmethod
    def _valida_corpo(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("mensagem vazia")
        if len(v) > 10_000:
            raise ValueError("mensagem muito longa (máx. 10.000 caracteres)")
        return v


@router.post("/{id_processo}/mensagens", status_code=201)
def criar_mensagem(
    id_processo: int,
    dados: MensagemIn,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """
    Escreve no canal do processo. Empresa fala, analista responde.

    Regras:
      - qualquer perfil COM acesso ao processo pode escrever (o RLS de
        _processo_no_escopo já barrou quem não pode);
      - só interno marca `interno=True` — se um externo mandar, é ignorado
        silenciosamente, não dá erro. Erro aqui só ensinaria que a flag existe;
      - só interno muda status, e a mudança vai pro audit trail junto.
    """
    _processo_no_escopo(id_processo, usuario)
    eh_interno = usuario.perfil in processo_repo.PERFIS_INTERNOS

    msg = processo_repo.criar_mensagem(
        id_processo=id_processo,
        id_usuario=usuario.id,
        corpo=dados.corpo,
        interno=dados.interno and eh_interno,
        autor_eh_externo=not eh_interno,
    )

    if dados.status_novo:
        if not eh_interno:
            raise HTTPException(403, "Só a equipe interna muda o status")
        if not processo_repo.status_existe(dados.status_novo):
            raise HTTPException(400, f"Status inválido: {dados.status_novo}")
        # Comentário do andamento = a própria mensagem. Assim o histórico
        # de auditoria explica POR QUE o status mudou, em vez de registrar
        # uma transição órfã.
        processo_repo.mudar_status(
            id_processo=id_processo,
            status_novo=dados.status_novo,
            id_usuario=usuario.id,
            comentario=dados.corpo[:500],
        )

    return msg


@router.get("/status-disponiveis")
def status_disponiveis(
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """Opções do dropdown 'mudar status para…' na resposta do analista."""
    if usuario.perfil not in processo_repo.PERFIS_INTERNOS:
        raise HTTPException(403, "Acesso restrito à equipe interna")
    return processo_repo.listar_status_disponiveis()


@router.get("/aguardando-resposta/contagem")
def contar_aguardando_resposta(
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """
    Quantos processos têm a última mensagem vinda do cliente — o número do
    sino no topo do módulo de Benefícios.

    ATENÇÃO À ORDEM: esta rota precisa vir antes de qualquer `/{id_processo}`
    que aceite string, senão o FastAPI tenta converter "aguardando-resposta"
    em int. Aqui está safe porque as rotas de id são todas `/{id}/algo`.
    """
    ids_empresa = usuario.empresas if usuario.perfil == "empresa" else None
    ids_sind = usuario.sindicatos if usuario.perfil == "sindicato" else None
    return {"aguardando": processo_repo.contar_aguardando_resposta(ids_empresa, ids_sind)}


@router.get("/{id_processo}")
def detalhe(
    id_processo: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    p = processo_repo.buscar_por_id(id_processo)
    if not p:
        raise HTTPException(404, "Processo não encontrado")
    if usuario.perfil == "empresa" and p.get("id_empresa") not in usuario.empresas:
        raise HTTPException(403, "Processo fora do escopo")
    if usuario.perfil == "sindicato" and p.get("id_sindicato") not in usuario.sindicatos:
        raise HTTPException(403, "Processo fora do escopo")
    return p
