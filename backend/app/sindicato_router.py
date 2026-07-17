"""
GET /sindicatos — listagem com filtros.

ESCOPO POR PERFIL
-----------------
- interno/admin/analista : veem todos
- sindicato              : vê só os seus (bss.usuario_sindicato)
- empresa/contabilidade  : BLOQUEADO (403)

O bloqueio do perfil 'empresa' não é capricho: `/{id}/detalhe` devolve o
`parametros_boleto` resolvido — tarifas, banco, vencimentos. É dado comercial
da BSS com o sindicato, e nenhuma empresa cliente tem o que fazer com ele.
Até 17/07/2026 as checagens aqui só tratavam `perfil == "sindicato"`, então
'empresa' caía no `else` e recebia a base inteira.

PENDÊNCIA: o portal legado TEM um item "Sindicatos" no menu da empresa. Falta
descobrir o que aquela tela mostra (provavelmente os sindicatos dos próprios
trabalhadores, sem os parâmetros comerciais). Quando soubermos, dá pra abrir
uma visão reduzida em vez do 403. Bloquear agora é a opção segura: some do
menu e não vaza nada.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from .auth import UsuarioInfo, usuario_logado
from . import sindicato_repo


router = APIRouter(prefix="/sindicatos", tags=["sindicatos"])

# Quem não pode ver sindicato nenhum enquanto a tela reduzida não existir.
PERFIS_SEM_ACESSO = {"empresa", "contabilidade"}


def _bloquear_externos(usuario: UsuarioInfo) -> None:
    if usuario.perfil in PERFIS_SEM_ACESSO:
        raise HTTPException(403, "Acesso restrito")


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
    _bloquear_externos(usuario)

    # Sindicato logado vê só ele mesmo; internos veem todos.
    ids: list[int] | None = None
    if usuario.perfil == "sindicato":
        if not usuario.sindicatos:
            return {"linhas": [], "total": 0, "pagina": 1,
                    "por_pagina": por_pagina, "paginas": 0}
        ids = usuario.sindicatos

    return sindicato_repo.listar(
        busca=busca, uf=uf, categoria=categoria,
        em_atendimento=em_atendimento, ids=ids,
        pagina=pagina, por_pagina=por_pagina, ordem=ordem, desc=desc,
    )


@router.get("/{id_sindicato}")
def detalhe(
    id_sindicato: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    _bloquear_externos(usuario)
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
    _bloquear_externos(usuario)   # parametros_boleto = tarifas e condições comerciais
    row = sindicato_repo.buscar_detalhe(id_sindicato)
    if not row:
        raise HTTPException(404, "Sindicato não encontrado")
    if usuario.perfil == "sindicato" and id_sindicato not in usuario.sindicatos:
        raise HTTPException(403, "Sindicato fora do escopo")
    return row
