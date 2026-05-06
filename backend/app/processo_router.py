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
