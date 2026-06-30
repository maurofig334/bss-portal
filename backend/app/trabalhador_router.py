"""
Endpoints de trabalhador.

GET /trabalhadores              → lista com paginação + filtros
GET /trabalhadores/{id}         → detalhe
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from .auth import UsuarioInfo, usuario_logado
from . import trabalhador_repo


router = APIRouter(prefix="/trabalhadores", tags=["trabalhadores"])


@router.get("")
def listar(
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
    busca: str | None = Query(None, description="Busca por nome ou CPF"),
    situacao: str | None = Query(None, description="ativo, inativo, carencia"),
    id_empresa: int | None = None,
    id_sindicato: int | None = None,
    uf: str | None = Query(None, max_length=2),
    pagina: int = 1,
    por_pagina: int = 50,
    ordem: str = "nome_completo",
    desc: bool = False,
):
    """
    Lista trabalhadores com filtros.
    Permissões: empresa só vê suas empresas; sindicato só vê seu sindicato.
    Admin/interno/analista veem tudo.
    """
    # RLS por perfil
    if usuario.perfil == "empresa":
        if not usuario.empresas:
            return {"linhas": [], "total": 0, "pagina": 1, "por_pagina": por_pagina, "paginas": 0}
        if id_empresa is None:
            # Sem filtro explícito → primeira empresa do usuário (na UI deve haver dropdown)
            id_empresa = usuario.empresas[0]
        elif id_empresa not in usuario.empresas:
            raise HTTPException(403, "Empresa fora do escopo do usuário")
    elif usuario.perfil == "sindicato":
        if not usuario.sindicatos:
            return {"linhas": [], "total": 0, "pagina": 1, "por_pagina": por_pagina, "paginas": 0}
        if id_sindicato is None:
            id_sindicato = usuario.sindicatos[0]
        elif id_sindicato not in usuario.sindicatos:
            raise HTTPException(403, "Sindicato fora do escopo do usuário")

    return trabalhador_repo.listar(
        busca=busca,
        situacao=situacao,
        id_empresa=id_empresa,
        id_sindicato=id_sindicato,
        uf=uf,
        pagina=pagina,
        por_pagina=por_pagina,
        ordem=ordem,
        desc=desc,
    )


@router.get("/dependentes/{cpf_titular}")
def listar_dependentes(
    cpf_titular: str,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """Retorna dependentes vinculados a um titular pelo CPF."""
    cpf = "".join(c for c in cpf_titular if c.isdigit())
    if len(cpf) != 11:
        raise HTTPException(400, "CPF inválido")
    return trabalhador_repo.buscar_dependentes(cpf)


@router.get("/{id_trabalhador}/detalhe")
def detalhe_completo(
    id_trabalhador: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """
    Detalhe completo do trabalhador (#37): dados + endereço + dependentes
    relacionados (se titular) ou titular vinculado (se dependente).
    """
    row = trabalhador_repo.buscar_detalhe(id_trabalhador)
    if not row:
        raise HTTPException(404, "Trabalhador não encontrado")

    # RLS: empresa só vê trabalhador das suas empresas; sindicato só do seu sind
    if usuario.perfil == "empresa" and row.get("id_empresa_atual") not in usuario.empresas:
        raise HTTPException(403, "Trabalhador fora do escopo do usuário")
    if usuario.perfil == "sindicato" and row.get("id_sindicato_atual") not in usuario.sindicatos:
        raise HTTPException(403, "Trabalhador fora do escopo do usuário")

    if row.get("titularidade") == "dependente":
        row["dependentes"] = []
        row["titular"] = trabalhador_repo.buscar_titular(row.get("cpf_titular"))
    else:
        row["dependentes"] = trabalhador_repo.buscar_dependentes(row.get("cpf"))
        row["titular"] = None

    return row


@router.get("/{id_trabalhador}")
def detalhe(
    id_trabalhador: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    row = trabalhador_repo.buscar_por_id(id_trabalhador)
    if not row:
        raise HTTPException(404, "Trabalhador não encontrado")

    # RLS: empresa só vê trabalhador das suas empresas; sindicato só do seu sind
    if usuario.perfil == "empresa" and row.get("id_empresa_atual") not in usuario.empresas:
        raise HTTPException(403, "Trabalhador fora do escopo do usuário")
    if usuario.perfil == "sindicato" and row.get("id_sindicato_atual") not in usuario.sindicatos:
        raise HTTPException(403, "Trabalhador fora do escopo do usuário")

    return row
