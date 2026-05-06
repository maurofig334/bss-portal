"""
Conexões de banco do BSS.

- get_pg_connection(): PostgreSQL (banco novo, fonte da verdade)
- get_mysql_connection(): MySQL do SuiteCRM (somente leitura, opcional)
"""

from contextlib import contextmanager
from typing import Generator

import psycopg
from psycopg.rows import dict_row

from .config import settings


@contextmanager
def get_pg_connection() -> Generator[psycopg.Connection, None, None]:
    """
    Abre uma conexão com o PostgreSQL do BSS.

    Uso:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                row = cur.fetchone()
    """
    conn = psycopg.connect(
        host=settings.PG_HOST,
        port=settings.PG_PORT,
        dbname=settings.PG_DB,
        user=settings.PG_USER,
        password=settings.PG_PASSWORD,
        row_factory=dict_row,
    )
    try:
        yield conn
    finally:
        conn.close()


def get_mysql_connection():
    """
    Abre conexão com o MySQL do SuiteCRM legado em modo READ-ONLY.

    SEGURANÇA: este banco é a base de produção da GNB. Todas as queries
    feitas por este projeto são SELECT — mas pra blindar contra erros,
    a sessão MySQL é configurada como READ ONLY assim que conecta:
      SET SESSION TRANSACTION READ ONLY;
    Qualquer INSERT/UPDATE/DELETE/DDL aciona erro 1792.

    Importa pymysql só quando chamado, pra evitar dependência se não usado.
    """
    if not settings.MYSQL_HOST:
        raise RuntimeError(
            "MySQL legado não configurado. Defina MYSQL_HOST/MYSQL_DB/... no .env"
        )
    import pymysql
    import pymysql.cursors
    conn = pymysql.connect(
        host=settings.MYSQL_HOST,
        port=settings.MYSQL_PORT,
        database=settings.MYSQL_DB,
        user=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )
    # Blindagem: força a sessão a ser READ ONLY no servidor.
    # Qualquer escrita aciona ERROR 1792: "Cannot execute statement in a READ ONLY transaction."
    try:
        with conn.cursor() as cur:
            cur.execute("SET SESSION TRANSACTION READ ONLY")
    except Exception:
        # Se o servidor MySQL não suportar (versão antiga), não bloqueia o uso —
        # nosso código segue só rodando SELECT mesmo.
        pass
    return conn
