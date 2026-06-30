"""GET /sindicatos — listagem com filtros."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from .auth import UsuarioInfo, usuario_logado
from . import sindicato_repo


router = APIRouter(prefix="/sindicatos", tags=["sindicatos"])


@router.get("")
def listar(
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
    busca: str | None = None,
    uf: str | None = Query(None, max_length=2),
    categoria: str | None = None,
    em_atendimento: bool | None = None,
    pagina: int = 1,
    por_pagina: int = 50,
    ordem: str = "razao_social",
    desc: bool = False,
):
    # Sindicato logado vê só ele mesmo; demais perfis veem todos.
    if usuario.perfil == "sindicato":
        if not usuario.sindicatos:
            return {"linhas": [], "total": 0, "pagina": 1, "por_pagina": por_pagina, "paginas": 0}
        result = sindicato_repo.listar(
            busca=busca, uf=uf, categoria=categoria,
            em_atendimento=em_atendimento,
            pagina=pagina, por_pagina=por_pagina, ordem=ordem, desc=desc,
        )
        result["linhas"] = [r for r in result["linhas"] if r["id"] in usuario.sindicatos]
        result["total"] = len(result["linhas"])
        return result

    return sindicato_repo.listar(
        busca=busca, uf=uf, categoria=categoria,
        em_atendimento=em_atendimento,
        pagina=pagina, por_pagina=por_pagina, ordem=ordem, desc=desc,
    )


@router.get("/{id_sindicato}")
def detalhe(
    id_sindicato: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    row = sindicato_repo.buscar_por_id(id_sindicato)
    if not row:
        raise HTTPException(404, "Sindicato não encontrado")
    if usuario.perfil == "sindicato" and id_sindicato not in usuario.sindicatos:
        raise HTTPException(403, "Sindicato fora do escopo")
    return row


@router.get("/{id_sindicato}/detalhe")
def detalhe_completo(
    id_sindicato: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """Detalhe completo do sindicato (com parametros_boleto resolvido + agregados)."""
    row = sindicato_repo.buscar_detalhe(id_sindicato)
    if not row:
        raise HTTPException(404, "Sindicato não encontrado")
    if usuario.perfil == "sindicato" and id_sindicato not in usuario.sindicatos:
        raise HTTPException(403, "Sindicato fora do escopo")
    return row
