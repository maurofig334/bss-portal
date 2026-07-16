"""
Endpoints de contato — os usuários externos que administram empresas.

GET /contatos                    → listagem com filtros
GET /contatos/pendentes/contagem → o sininho (fila de aprovação)
GET /contatos/pendentes          → a fila que o analista aprova
GET /contatos/{id}/detalhe       → cabeçalho do contato
GET /contatos/{id}/empresas      → os CNPJs que ele administra (o N:N)
GET /contatos/{id}/solicitacoes  → histórico de pedidos de acesso

Ver docs/AUTOCADASTRO.md.

PERMISSÃO: só staff interno. Contato é dado de gestão de acesso — cliente não
vê a lista de quem administra o quê.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from .auth import UsuarioInfo, usuario_logado
from . import contato_repo


router = APIRouter(prefix="/contatos", tags=["contatos"])

PERFIS_INTERNOS = {"admin", "interno", "analista"}


def _exigir_interno(usuario: UsuarioInfo) -> None:
    if usuario.perfil not in PERFIS_INTERNOS:
        raise HTTPException(403, "Acesso restrito à equipe interna")


@router.get("")
def listar(
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
    busca: str | None = Query(None, description="Nome, e-mail ou CNPJ administrado"),
    ativo: bool | None = None,
    tipo_cadastro: str | None = Query(None, description="auto | interno"),
    id_empresa: int | None = None,
    pagina: int = 1,
    por_pagina: int = 50,
    ordem: str = "nome",
    desc: bool = False,
):
    _exigir_interno(usuario)
    return contato_repo.listar(
        busca=busca, ativo=ativo, tipo_cadastro=tipo_cadastro,
        id_empresa=id_empresa, pagina=pagina, por_pagina=por_pagina,
        ordem=ordem, desc=desc,
    )


@router.get("/pendentes/contagem")
def contagem_pendentes(usuario: Annotated[UsuarioInfo, Depends(usuario_logado)]):
    """O sininho. Chamado a cada carga de página — por isso é só um COUNT."""
    _exigir_interno(usuario)
    return {"pendentes": contato_repo.contar_pendentes()}


@router.get("/pendentes")
def pendentes(usuario: Annotated[UsuarioInfo, Depends(usuario_logado)]):
    """
    A fila de aprovação. A view já traz o contexto pro analista decidir:
    quantos gestores o CNPJ já tem, e há quantos dias o pedido espera.
    """
    _exigir_interno(usuario)
    return contato_repo.listar_pendentes()


@router.get("/{id_contato}/detalhe")
def detalhe(
    id_contato: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    _exigir_interno(usuario)
    row = contato_repo.buscar_detalhe(id_contato)
    if not row:
        raise HTTPException(404, "Contato não encontrado")
    return row


@router.get("/{id_contato}/empresas")
def empresas(
    id_contato: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """Os CNPJs que o contato administra — o N:N que o legado não mostra."""
    _exigir_interno(usuario)
    return contato_repo.listar_empresas(id_contato)


@router.get("/{id_contato}/solicitacoes")
def solicitacoes(
    id_contato: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    _exigir_interno(usuario)
    return contato_repo.listar_solicitacoes(id_contato)
