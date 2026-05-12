"""GET /boletos — listagem + emissão (épico #21)."""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from .auth import UsuarioInfo, usuario_logado
from . import boleto_repo, boleto_emissao, boleto_pdf


router = APIRouter(prefix="/boletos", tags=["boletos"])


# =============================================================================
# Listagem (já existia)
# =============================================================================

@router.get("")
def listar(
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
    busca: str | None = None,
    status: str | None = None,
    mes_referencia: str | None = None,
    id_empresa: int | None = None,
    id_sindicato: int | None = None,
    incluir_cancelados: bool = False,
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
        # Empresa NUNCA vê cancelados (regra do épico #21):
        incluir_cancelados = False
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
        incluir_cancelados=incluir_cancelados,
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


@router.get("/{id_boleto}/detalhe")
def detalhe_completo(
    id_boleto: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """Detalhe completo do boleto + trabalhadores (boleto_item) pra tela de detalhe."""
    row = boleto_repo.buscar_detalhe(id_boleto)
    if not row:
        raise HTTPException(404, "Boleto não encontrado")
    # Empresa nunca vê cancelado:
    if usuario.perfil == "empresa":
        if row.get("status") == "cancelado":
            raise HTTPException(404, "Boleto não disponível")
        if row.get("id_empresa") not in usuario.empresas:
            raise HTTPException(403, "Boleto fora do escopo")
    elif usuario.perfil == "sindicato":
        if row.get("id_sindicato") not in usuario.sindicatos:
            raise HTTPException(403, "Boleto fora do escopo")
    return row


# =============================================================================
# Emissão (épico #21)
# =============================================================================

def _mes_corrente_inicio() -> date:
    h = date.today()
    return h.replace(day=1)


@router.get("/emissao/preview")
def preview_emissao(
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
    id_empresa: int | None = None,
):
    """
    Preview da emissão pra mês de amparo CORRENTE (regra: mês fixo).

    Por perfil:
      - empresa: lista TODAS as empresas vinculadas ao usuário
      - admin/interno: REQUER id_empresa na query string
                       (sem isso, retorna vazio com aviso)
    """
    return boleto_emissao.preview_emissao(usuario, _mes_corrente_inicio(), id_empresa)


class EmitirRequest(BaseModel):
    ids_empresa: list[int] | None = None  # opcional — subset; default = todas do escopo


@router.post("/emissao/emitir")
def emitir(
    payload: Annotated[EmitirRequest | None, Body()],
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    """
    Gera boletos pro mês de amparo CORRENTE.
    Idempotente: pares (empresa × sindicato × mês) que já têm boleto vivo
    são pulados (volta no campo 'pulados').
    """
    ids = payload.ids_empresa if payload else None
    return boleto_emissao.emitir_boletos(usuario, _mes_corrente_inicio(), ids)


class CancelarRequest(BaseModel):
    motivo: str


@router.post("/{id_boleto}/cancelar")
def cancelar(
    id_boleto: int,
    payload: Annotated[CancelarRequest, Body()],
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    res = boleto_emissao.cancelar_boleto(usuario, id_boleto, payload.motivo)
    if not res.get("ok"):
        raise HTTPException(400, res.get("erro", "Erro ao cancelar"))
    return res


@router.post("/{id_boleto}/reemitir")
def reemitir(
    id_boleto: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    res = boleto_emissao.reemitir_boleto(usuario, id_boleto)
    if not res.get("ok"):
        raise HTTPException(400, res.get("erro", "Erro ao reemitir"))
    return res


# =============================================================================
# Downloads PDF (boleto + lista de trabalhadores)
# =============================================================================

def _check_acesso_boleto(usuario: UsuarioInfo, row: dict[str, Any]) -> None:
    """Confere se o usuário tem permissão de ver o boleto."""
    if not row:
        raise HTTPException(404, "Boleto não encontrado")
    if usuario.perfil == "empresa":
        if row.get("status") == "cancelado":
            # Empresa NUNCA vê cancelado:
            raise HTTPException(404, "Boleto não disponível")
        if row.get("id_empresa") not in usuario.empresas:
            raise HTTPException(403, "Boleto fora do escopo")
    elif usuario.perfil == "sindicato":
        if row.get("id_sindicato") not in usuario.sindicatos:
            raise HTTPException(403, "Boleto fora do escopo")


@router.get("/{id_boleto}/pdf")
def download_pdf_boleto(
    id_boleto: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    row = boleto_repo.buscar_por_id(id_boleto)
    _check_acesso_boleto(usuario, row)
    pdf = boleto_pdf.gerar_pdf_boleto(id_boleto)
    if not pdf:
        raise HTTPException(404, "Boleto não encontrado")
    nome = f"boleto_{row.get('nosso_numero') or id_boleto}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nome}"'},
    )


@router.get("/{id_boleto}/lista-pdf")
def download_pdf_lista(
    id_boleto: int,
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
):
    row = boleto_repo.buscar_por_id(id_boleto)
    _check_acesso_boleto(usuario, row)
    pdf = boleto_pdf.gerar_pdf_lista(id_boleto)
    if not pdf:
        raise HTTPException(404, "Boleto não encontrado")
    nome = f"lista_trabalhadores_{row.get('nosso_numero') or id_boleto}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nome}"'},
    )
