"""
Mapeia o universo de tabelas cbr_parametros* no legado SuiteCRM.

Pra cada tabela encontrada, mostra:
  1) Lista de colunas (nome + tipo + nullable)
  2) Contagem total de linhas (descontando deleted=1 quando a coluna existe)
  3) Amostra das primeiras 3 linhas (chaves selecionadas)

Uso (do diretório backend/, com venv ativa):
    python -m scripts.inspecionar_cbr_parametros

Saída direcionada pra `docs/MAPEAMENTO_LEGADO.md` depois.
"""

from __future__ import annotations

from app.config import settings
from app.database import get_mysql_connection


def listar_tabelas(cur) -> list[str]:
    cur.execute(
        """
        SELECT TABLE_NAME
          FROM information_schema.TABLES
         WHERE TABLE_SCHEMA = %s
           AND TABLE_NAME LIKE 'cbr_parametros%%'
         ORDER BY TABLE_NAME
        """,
        (settings.MYSQL_DB,),
    )
    return [r["TABLE_NAME"] for r in cur.fetchall()]


def colunas(cur, tabela: str) -> list[dict]:
    cur.execute(
        """
        SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT
          FROM information_schema.COLUMNS
         WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
         ORDER BY ORDINAL_POSITION
        """,
        (settings.MYSQL_DB, tabela),
    )
    return list(cur.fetchall())


def contar(cur, tabela: str, col_names: set[str]) -> tuple[int, int]:
    """Retorna (total, ativos). Ativos só faz sentido se tiver 'deleted'."""
    cur.execute(f"SELECT COUNT(*) AS n FROM `{tabela}`")
    total = cur.fetchone()["n"]
    if "deleted" in col_names:
        cur.execute(f"SELECT COUNT(*) AS n FROM `{tabela}` WHERE deleted = 0")
        ativos = cur.fetchone()["n"]
    else:
        ativos = total
    return total, ativos


def amostra(cur, tabela: str, limite: int = 3) -> list[dict]:
    cur.execute(f"SELECT * FROM `{tabela}` LIMIT {limite}")
    return list(cur.fetchall())


def main() -> None:
    with get_mysql_connection() as conn:
        with conn.cursor() as cur:
            tabelas = listar_tabelas(cur)
            if not tabelas:
                print("Nenhuma tabela cbr_parametros* encontrada.")
                return

            print(f"\n=== {len(tabelas)} TABELA(S) cbr_parametros* ===\n")
            for nome in tabelas:
                cols = colunas(cur, nome)
                col_names = {c["COLUMN_NAME"] for c in cols}
                total, ativos = contar(cur, nome, col_names)

                print("-" * 78)
                print(f"TABELA: {nome}")
                print(f"  total={total}  ativos(deleted=0)={ativos}  colunas={len(cols)}")
                print(f"  COLUNAS:")
                for c in cols:
                    nullable = "NULL" if c["IS_NULLABLE"] == "YES" else "NOT NULL"
                    print(f"    - {c['COLUMN_NAME']:<35} {c['COLUMN_TYPE']:<25} {nullable}")

                if ativos:
                    print(f"  AMOSTRA (primeiras 3 linhas):")
                    rows = amostra(cur, nome, 3)
                    for i, r in enumerate(rows, 1):
                        print(f"    [{i}]")
                        for k, v in r.items():
                            s = repr(v)
                            if len(s) > 80:
                                s = s[:77] + "..."
                            print(f"        {k}: {s}")
                print()


if __name__ == "__main__":
    main()
