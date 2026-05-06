"""
Aplicação FastAPI — ponto de entrada do BSS.

Endpoints públicos:
    GET  /          → redireciona pra interface (/app)
    GET  /app/...   → arquivos estáticos do frontend
    GET  /health    → checa conexão com Postgres
    GET  /version   → versão atual
    GET  /docs      → Swagger
    POST /auth/login

Endpoints protegidos (requerem JWT):
    GET  /auth/me
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .version import VERSION
from .auth import router as auth_router
from .trabalhador_router import router as trabalhador_router
from .empresa_router import router as empresa_router
from .processo_router import router as processo_router
from .boleto_router import router as boleto_router
from .dashboard_router import router as dashboard_router
from .database import get_pg_connection


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(
    title="BSS — Benefício Social Sindical",
    description="API do portal BSS da GNB",
    version=VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(trabalhador_router)
app.include_router(empresa_router)
app.include_router(processo_router)
app.include_router(boleto_router)
app.include_router(dashboard_router)

# Arquivos estáticos do frontend em /app/
app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/app/")


@app.get("/version", include_in_schema=False)
def version():
    return {"version": VERSION}


@app.get("/health")
def health():
    """Confirma que a API está de pé E que o Postgres responde."""
    try:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT current_database() AS db, current_user AS db_user, "
                    "inet_server_addr() AS host, inet_server_port() AS port"
                )
                info = cur.fetchone()
        return {"api": "ok", "database": "ok", "version": VERSION, "conexao": info}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao conectar no banco: {e}")
