"""
Acesso a bss.modelo_email — os textos dos e-mails em massa.
"""

from __future__ import annotations

from typing import Any

from .database import get_pg_connection


def listar() -> list[dict[str, Any]]:
    """Todos os modelos, pra lista do editor. Ordena por categoria e nome."""
    sql = """
        SELECT id, codigo, nome, destinatario, categoria, ativo,
               (assunto <> '' OR corpo <> '') AS preenchido,
               atualizado_em
          FROM bss.modelo_email
         ORDER BY categoria NULLS LAST, nome
    """
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(sql)
        return list(cur.fetchall())


def buscar(id_modelo: int) -> dict[str, Any] | None:
    sql = """
        SELECT id, codigo, nome, destinatario, categoria,
               assunto, corpo, ativo, observacao, atualizado_em
          FROM bss.modelo_email WHERE id = %s
    """
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(sql, (id_modelo,))
        return cur.fetchone()


def salvar(id_modelo: int, assunto: str, corpo: str, ativo: bool,
           observacao: str | None, atualizado_por_id: int) -> dict[str, Any] | None:
    """
    Grava o texto. NÃO deixa mexer em codigo nem destinatario: o codigo é a
    chave que o disparo automático procura, e o destinatario define o conjunto
    de variáveis — mudar qualquer um dos dois pela edição de texto quebraria
    silenciosamente um gatilho ou tornaria variáveis órfãs de uma vez.
    """
    sql = """
        UPDATE bss.modelo_email
           SET assunto = %s, corpo = %s, ativo = %s, observacao = %s,
               atualizado_por_id = %s, atualizado_em = NOW()
         WHERE id = %s
        RETURNING id, codigo, nome, destinatario, categoria,
                  assunto, corpo, ativo, observacao, atualizado_em
    """
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(sql, (assunto, corpo, ativo, observacao,
                          atualizado_por_id, id_modelo))
        row = cur.fetchone()
        conn.commit()
        return row
