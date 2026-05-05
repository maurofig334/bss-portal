"""
Autenticação por JWT — login + dependência usuario_logado.

Usa a tabela `bss_users` (criada por scripts/criar_tabela_usuarios.py).
"""

from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel

from .config import settings
from .database import get_pg_connection


router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# === Hash / verificação de senha ===========================================

def hash_senha(senha_plana: str) -> str:
    return bcrypt.hashpw(senha_plana.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar_senha(senha_plana: str, hash_armazenado: str) -> bool:
    try:
        return bcrypt.checkpw(senha_plana.encode("utf-8"), hash_armazenado.encode("utf-8"))
    except Exception:
        return False


# === JWT ====================================================================

def criar_token(dados: dict) -> str:
    expira = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    dados = {**dados, "exp": expira}
    return jwt.encode(dados, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decodificar_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Token inválido")


# === Schemas ================================================================

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UsuarioInfo(BaseModel):
    id: int
    email: str
    nome: str
    perfil: str                       # admin/interno/analista/empresa/sindicato/contabilidade
    # Vínculos N:N (vazios se perfil interno/admin/analista/contabilidade):
    empresas: list[int] = []          # IDs de bss.empresa que o usuário opera (perfil=empresa)
    sindicatos: list[int] = []        # IDs de bss.sindicato que o usuário vê (perfil=sindicato)


# === Helpers de vínculo =====================================================

def _carregar_vinculos(conn, user_id: int, perfil: str) -> tuple[list[int], list[int]]:
    """Carrega empresas/sindicatos do usuário conforme o perfil.
    Internos/admin/analista/contabilidade não têm filtro (listas vazias)."""
    empresas: list[int] = []
    sindicatos: list[int] = []
    with conn.cursor() as cur:
        if perfil == "empresa":
            cur.execute(
                "SELECT id_empresa FROM bss.usuario_empresa "
                "WHERE id_usuario = %s AND ativo",
                (user_id,),
            )
            empresas = [r["id_empresa"] for r in cur.fetchall()]
        elif perfil == "sindicato":
            cur.execute(
                "SELECT id_sindicato FROM bss.usuario_sindicato "
                "WHERE id_usuario = %s AND ativo",
                (user_id,),
            )
            sindicatos = [r["id_sindicato"] for r in cur.fetchall()]
    return empresas, sindicatos


# === Endpoints ==============================================================

@router.post("/login", response_model=TokenResponse)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()]):
    """Recebe form-data com 'username' (email) e 'password'."""
    sql = """
        SELECT id, email, nome, senha_hash, ativo, perfil
        FROM bss_users
        WHERE email = %s
    """
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (form.username.strip().lower(),))
            user = cur.fetchone()

        erro = HTTPException(status_code=401, detail="Email ou senha inválidos")
        if not user:
            raise erro
        if not user["ativo"]:
            raise HTTPException(status_code=401, detail="Usuário desativado")
        if not verificar_senha(form.password, user["senha_hash"]):
            raise erro

        empresas, sindicatos = _carregar_vinculos(conn, user["id"], user["perfil"])

        # Atualiza ultimo_login (não falha login se der erro)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE bss_users SET ultimo_login = NOW() WHERE id = %s",
                    (user["id"],),
                )
            conn.commit()
        except Exception:
            conn.rollback()

    token = criar_token({
        "sub":        str(user["id"]),
        "email":      user["email"],
        "nome":       user["nome"],
        "perfil":     user["perfil"],
        "empresas":   empresas,
        "sindicatos": sindicatos,
    })
    return TokenResponse(access_token=token)


def usuario_logado(token: Annotated[str, Depends(oauth2_scheme)]) -> UsuarioInfo:
    """Dependência: use Depends(usuario_logado) em endpoints protegidos."""
    p = decodificar_token(token)
    return UsuarioInfo(
        id=int(p["sub"]),
        email=p["email"],
        nome=p["nome"],
        perfil=p.get("perfil", ""),
        empresas=p.get("empresas") or [],
        sindicatos=p.get("sindicatos") or [],
    )


@router.get("/me", response_model=UsuarioInfo)
def me(usuario: Annotated[UsuarioInfo, Depends(usuario_logado)]):
    return usuario
