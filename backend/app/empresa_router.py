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
    # Escopo: perfil 'empresa' só enxerga as empresas vinculadas a ele
    # (bss.usuario_empresa, carregado no JWT). O filtro vai pro SQL via
    # `ids` — NÃO filtrar o resultado depois de paginar (ver docstring do
    # empresa_repo.listar: era assim, e escondia 10 das 11 empresas do
    # usuário atrás de 105 páginas).
    ids: list[int] | None = None
    if usuario.perfil == "empresa":
        if not usuario.empresas:
            # Sem vínculo não há o que mostrar. Devolve vazio coerente em vez
            # de ids=[] (que geraria SQL válido mas semanticamente confuso).
            return {"linhas": [], "total": 0, "pagina": 1,
                    "por_pagina": por_pagina, "paginas": 0}
        ids = usuario.empresas

    return empresa_repo.listar(
        busca=busca, status=status, adimplencia=adimplencia,
        regularidade=regularidade, uf=uf, ids=ids,
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
