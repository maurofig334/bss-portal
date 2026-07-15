"""GET /processos — benefícios."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

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
    pagina: int = 1,
    por_pagina: int = 50,
    ordem: str = "criado_em",
    desc: bool = True,
):
    if usuario.perfil == "empresa":
        if not usuario.empresas:
            return {"linhas": [], "total": 0, "pagina": 1, "por_pagina": por_pagina, "paginas": 0}
        if id_empresa is None:
            id_empresa = usuario.empresas[0]
        elif id_empresa not in usuario.empresas:
            raise HTTPException(403, "Empresa fora do escopo")
    elif usuario.perfil == "sindicato":
        if not usuario.sindicatos:
            return {"linhas": [], "total": 0, "pagina": 1, "por_pagina": por_pagina, "paginas": 0}
        if id_sindicato is None:
            id_sindicato = usuario.sindicatos[0]
        elif id_sindicato not in usuario.sindicatos:
            raise HTTPException(403, "Sindicato fora do escopo")

    return processo_repo.listar(
        busca=busca, status=status, status_categoria=status_categoria, tipo=tipo,
        id_empresa=id_empresa, id_sindicato=id_sindicato,
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
    Canal de mensagens do processo. Perfil 'empresa' (cliente externo) não vê
    as mensagens marcadas como internas — só o staff.
    """
    _processo_no_escopo(id_processo, usuario)
    incluir_internas = usuario.perfil != "empresa"
    return processo_repo.listar_mensagens(id_processo, incluir_internas=incluir_internas)


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
