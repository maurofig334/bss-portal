"""GET /empresas — listagem com filtros."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from .auth import UsuarioInfo, usuario_logado
from . import empresa_repo


router = APIRouter(prefix="/empresas", tags=["empresas"])


@router.get("")
def listar(
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
    busca: str | None = None,
    status: str | None = None,
    adimplencia: str | None = None,
    regularidade: str | None = None,
    uf: str | None = Query(None, max_length=2),
    pagina: int = 1,
    por_pagina: int = 50,
    ordem: str = "razao_social",
    desc: bool = False,
):
    # Empresa só vê suas próprias; sindicato vê todas das empresas relacionadas (futuro)
    if usuario.perfil == "empresa":
        # Para empresa, vamos retornar só a(s) dela(s)
        if not usuario.empresas:
            return {"linhas": [], "total": 0, "pagina": 1, "por_pagina": por_pagina, "paginas": 0}
        # TODO: filtrar por id IN (empresas) — por enquanto pega 1ª como atalho
        # (pra simplificar; numa fase posterior adicionar filtro IN)
        result = empresa_repo.listar(
            busca=busca, status=status, adimplencia=adimplencia,
            regularidade=regularidade, uf=uf,
            pagina=pagina, por_pagina=por_pagina, ordem=ordem, desc=desc,
        )
        result["linhas"] = [r for r in result["linhas"] if r["id"] in usuario.empresas]
        result["total"] = len(result["linhas"])
        return result

    return empresa_repo.listar(
        busca=busca, status=status, adimplencia=adimplencia,
        regularidade=regularidade, uf=uf,
        pagina=pagina, por_pagina=por_pagina, ordem=ordem, desc=desc,
    )


@router.get("/{id_empresa}/detalhe")
def detalhe_completo(
    id_empresa: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """Detalhe completo da empresa (endereço + caches + datas)."""
    if usuario.perfil == "empresa" and id_empresa not in usuario.empresas:
        raise HTTPException(403, "Empresa fora do escopo")
    row = empresa_repo.buscar_detalhe(id_empresa)
    if not row:
        raise HTTPException(404, "Empresa não encontrada")
    return row


@router.get("/{id_empresa}/usuarios")
def usuarios(
    id_empresa: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """Usuários com acesso à empresa (aba de relacionamento)."""
    if usuario.perfil == "empresa" and id_empresa not in usuario.empresas:
        raise HTTPException(403, "Empresa fora do escopo")
    return empresa_repo.listar_usuarios(id_empresa)


@router.get("/{id_empresa}")
def detalhe(
    id_empresa: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    row = empresa_repo.buscar_por_id(id_empresa)
    if not row:
        raise HTTPException(404, "Empresa não encontrada")
    if usuario.perfil == "empresa" and id_empresa not in usuario.empresas:
        raise HTTPException(403, "Empresa fora do escopo")
    return row
