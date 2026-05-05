"""
Utilitários compartilhados pelos sincronizadores.

Funções principais:
  - mysql_iter(sql, batch_size): itera resultado do MySQL em lotes (sem carregar tudo na RAM)
  - pg_upsert_batch(conn, sql, rows): UPSERT em lote no Postgres
  - so_digitos(s): remove tudo que não é dígito (CPF/CNPJ/telefone)
  - parse_date(v): converte tipos esquisitos do MySQL pra date/None
  - log_progresso(...): print formatado com ETA
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Generator, Iterable, Sequence

import psycopg

logger = logging.getLogger("bss.sync")


# === Helpers de tipo ========================================================

_RE_DIGITOS = re.compile(r"\D+")


def so_digitos(valor: Any) -> str | None:
    """Remove tudo que não é dígito. Retorna None se vazio."""
    if valor is None:
        return None
    s = _RE_DIGITOS.sub("", str(valor))
    return s or None


def parse_data(valor: Any) -> Any:
    """Converte valor que pode vir como string vazia, '0000-00-00', etc., para None."""
    if valor is None:
        return None
    s = str(valor).strip()
    if not s or s.startswith("0000"):
        return None
    return valor


def trim_or_none(valor: Any, max_len: int | None = None) -> str | None:
    """Strip + corte de tamanho. Vazio vira None."""
    if valor is None:
        return None
    s = str(valor).strip()
    if not s:
        return None
    if max_len and len(s) > max_len:
        s = s[:max_len]
    return s


# === Helper de paginação MySQL =============================================

def mysql_iter(
    mysql_conn,
    sql: str,
    params: Sequence[Any] | None = None,
    batch_size: int = 1000,
) -> Generator[dict, None, None]:
    """
    Executa SQL no MySQL e itera resultado em lotes (server-side cursor),
    sem carregar tudo na RAM. Yields dicts.
    """
    with mysql_conn.cursor() as cur:
        cur.execute(sql, params or ())
        while True:
            lote = cur.fetchmany(batch_size)
            if not lote:
                break
            for linha in lote:
                yield linha


# === Helper de UPSERT em lote ==============================================

def pg_executemany(
    pg_conn: psycopg.Connection,
    sql: str,
    rows: Iterable[Sequence[Any]],
    batch_size: int = 500,
) -> int:
    """
    Executa SQL (com %s) em lote, fazendo commit a cada `batch_size` linhas.
    Retorna total de linhas processadas.
    """
    total = 0
    buffer: list[Sequence[Any]] = []
    with pg_conn.cursor() as cur:
        for r in rows:
            buffer.append(r)
            if len(buffer) >= batch_size:
                cur.executemany(sql, buffer)
                pg_conn.commit()
                total += len(buffer)
                buffer.clear()
        if buffer:
            cur.executemany(sql, buffer)
            pg_conn.commit()
            total += len(buffer)
    return total


# === Logger de progresso ====================================================

class Progresso:
    """Imprime progresso a cada N segundos com ETA estimado."""

    def __init__(self, total: int | None, nome: str, intervalo: float = 2.0):
        self.total = total
        self.nome = nome
        self.intervalo = intervalo
        self.contador = 0
        self.inicio = time.monotonic()
        self.ultimo_log = 0.0

    def tick(self, n: int = 1) -> None:
        self.contador += n
        agora = time.monotonic()
        if agora - self.ultimo_log < self.intervalo:
            return
        self.ultimo_log = agora
        decorrido = agora - self.inicio
        taxa = self.contador / decorrido if decorrido > 0 else 0
        if self.total:
            pct = self.contador * 100 / self.total
            restante = (self.total - self.contador) / taxa if taxa > 0 else 0
            print(
                f"  [{self.nome}] {self.contador}/{self.total} "
                f"({pct:.1f}%) — {taxa:.0f}/s — eta {restante:.0f}s",
                flush=True,
            )
        else:
            print(
                f"  [{self.nome}] {self.contador} processados — {taxa:.0f}/s",
                flush=True,
            )

    def fim(self) -> None:
        decorrido = time.monotonic() - self.inicio
        taxa = self.contador / decorrido if decorrido > 0 else 0
        print(
            f"  [{self.nome}] ✓ {self.contador} concluído em {decorrido:.1f}s "
            f"({taxa:.0f}/s)",
            flush=True,
        )
