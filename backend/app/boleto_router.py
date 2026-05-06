"""GET /boletos — listagem com filtros."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from .auth import UsuarioInfo, usuario_logado
from . import boleto_repo


router = APIRouter(prefix="/boletos", tags=["boletos"])


@router.get("")
def listar(
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
    busca: str | None = None,
    status: str | None = None,
    mes_referencia: str | None = None,
    id_empresa: int | None = None,
    id_sindicato: int | None = None,
    pagina: int = 1,
    por_pagina: int = 50,
    ordem: str = "mes_referencia",
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

    return boleto_repo.listar(
        busca=busca, status=status, mes_referencia=mes_referencia,
        id_empresa=id_empresa, id_sindicato=id_sindicato,
        pagina=pagina, por_pagina=por_pagina, ordem=ordem, desc=desc,
    )


@router.get("/{id_boleto}")
def detalhe(
    id_boleto: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    row = boleto_repo.buscar_por_id(id_boleto)
    if not row:
        raise HTTPException(404, "Boleto não encontrado")
    if usuario.perfil == "empresa" and row.get("id_empresa") not in usuario.empresas:
        raise HTTPException(403, "Boleto fora do escopo")
    if usuario.perfil == "sindicato" and row.get("id_sindicato") not in usuario.sindicatos:
        raise HTTPException(403, "Boleto fora do escopo")
    return row
