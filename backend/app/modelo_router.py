"""
/modelos — modelos de e-mail em massa. RESTRITO à equipe interna.

GET  /modelos                    → lista
GET  /modelos/variaveis          → catálogo (paleta do editor)
GET  /modelos/{id}               → um modelo
PUT  /modelos/{id}               → grava texto
POST /modelos/{id}/preview       → resolve contra contato/empresa real

Sem envio aqui — é fase futura, depende do conteúdo e do cronograma que a BSS
ainda vai passar. Este módulo é só criar/ajustar/pré-visualizar os textos.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .auth import UsuarioInfo, exigir_interno
from . import modelo_repo, modelo_variaveis


router = APIRouter(prefix="/modelos", tags=["modelos"])


@router.get("")
def listar(usuario: Annotated[UsuarioInfo, Depends(exigir_interno)]):
    return modelo_repo.listar()


@router.get("/variaveis")
def variaveis(
    usuario: Annotated[UsuarioInfo, Depends(exigir_interno)],
    destinatario: str | None = None,
):
    """Catálogo pra paleta. `destinatario` filtra o que faz sentido."""
    return modelo_variaveis.catalogo(destinatario)


@router.get("/{id_modelo}")
def buscar(
    id_modelo: int,
    usuario: Annotated[UsuarioInfo, Depends(exigir_interno)],
):
    m = modelo_repo.buscar(id_modelo)
    if not m:
        raise HTTPException(404, "Modelo não encontrado")
    return m


class ModeloIn(BaseModel):
    assunto: str = ""
    corpo: str = ""
    ativo: bool = False
    observacao: str | None = None


@router.put("/{id_modelo}")
def salvar(
    id_modelo: int,
    dados: ModeloIn,
    usuario: Annotated[UsuarioInfo, Depends(exigir_interno)],
):
    m = modelo_repo.buscar(id_modelo)
    if not m:
        raise HTTPException(404, "Modelo não encontrado")

    # Ativar um modelo com variável órfã é pedir pra mandar "{{xyz}}" pro
    # cliente num disparo real. Barra na hora de salvar, não só no preview.
    if dados.ativo:
        orfas = sorted(set(
            modelo_variaveis.variaveis_orfas(dados.assunto, m["destinatario"])
            + modelo_variaveis.variaveis_orfas(dados.corpo, m["destinatario"])
        ))
        if orfas:
            raise HTTPException(
                400,
                f"Não dá pra ativar: variáveis que não resolvem para "
                f"destinatário '{m['destinatario']}': {', '.join('{{'+o+'}}' for o in orfas)}",
            )

    return modelo_repo.salvar(
        id_modelo, dados.assunto, dados.corpo, dados.ativo,
        dados.observacao, usuario.id,
    )


class PreviewIn(BaseModel):
    assunto: str = ""
    corpo: str = ""
    # Contra quem resolver. O editor manda um dos dois conforme o destinatário
    # do modelo. Texto vem do editor (não do banco) pra pré-visualizar o que
    # está sendo digitado agora, antes de salvar.
    id_contato: int | None = None
    id_empresa: int | None = None


@router.post("/{id_modelo}/preview")
def preview(
    id_modelo: int,
    dados: PreviewIn,
    usuario: Annotated[UsuarioInfo, Depends(exigir_interno)],
):
    m = modelo_repo.buscar(id_modelo)
    if not m:
        raise HTTPException(404, "Modelo não encontrado")

    if m["destinatario"] == "contato" and not dados.id_contato:
        raise HTTPException(400, "Escolha um contato para pré-visualizar")
    if m["destinatario"] == "empresa" and not dados.id_empresa:
        raise HTTPException(400, "Escolha uma empresa para pré-visualizar")

    return modelo_variaveis.renderizar(
        assunto=dados.assunto, corpo=dados.corpo,
        destinatario=m["destinatario"],
        id_contato=dados.id_contato, id_empresa=dados.id_empresa,
    )
