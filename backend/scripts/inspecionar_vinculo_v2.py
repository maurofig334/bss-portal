"""Hipóteses 1, 2 e 3 do vínculo parâmetro↔sindicato.

Uso (do diretório backend/, com venv ativa):
    python -m scripts.inspecionar_vinculo_v2

Investiga:
  HIP 1 — sindi_sindicatos_cstm tem coluna FK pro parâmetro?
  HIP 2 — existe tabela N-N (terminada em _c) ligando os dois?
  HIP 3 — vínculo é por nome (cbr_parametros_boleto.name == sindi_sindicatos.name)?
"""

from __future__ import annotations

from app.config import settings
from app.database import get_mysql_connection


def main() -> None:
    with get_mysql_connection() as conn:
        with conn.cursor() as cur:
            # ── HIP 1: ligação inversa em sindi_sindicatos_cstm ────────────
            print("=== HIP 1: sindi_sindicatos_cstm — todas as colunas ===")
            cur.execute(
                """
                SELECT COLUMN_NAME, COLUMN_TYPE
                  FROM information_schema.COLUMNS
                 WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'sindi_sindicatos_cstm'
                 ORDER BY ORDINAL_POSITION
                """,
                (settings.MYSQL_DB,),
            )
            for c in cur.fetchall():
                print(f"  {c['COLUMN_NAME']:<40} {c['COLUMN_TYPE']}")

            # ── HIP 2: tabelas N-N (terminam em _c) que mencionem qualquer dos dois
            print("\n=== HIP 2: tabelas N-N (terminam em _c) ===")
            cur.execute(
                """
                SELECT TABLE_NAME
                  FROM information_schema.TABLES
                 WHERE TABLE_SCHEMA = %s
                   AND TABLE_NAME LIKE '%_c'
                   AND (TABLE_NAME LIKE '%parametros%'
                        OR TABLE_NAME LIKE '%sindi%'
                        OR TABLE_NAME LIKE '%sindicato%')
                 ORDER BY TABLE_NAME
                """,
                (settings.MYSQL_DB,),
            )
            rels = [r["TABLE_NAME"] for r in cur.fetchall()]
            for t in rels:
                print(f"  - {t}")

            for t in rels:
                print(f"\n  --- {t} ---")
                cur.execute(
                    """
                    SELECT COLUMN_NAME, COLUMN_TYPE
                      FROM information_schema.COLUMNS
                     WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                     ORDER BY ORDINAL_POSITION
                    """,
                    (settings.MYSQL_DB, t),
                )
                for c in cur.fetchall():
                    print(f"    {c['COLUMN_NAME']:<35} {c['COLUMN_TYPE']}")
                cur.execute(f"SELECT COUNT(*) AS n FROM `{t}`")
                print(f"    linhas: {cur.fetchone()['n']}")
                cur.execute(f"SELECT * FROM `{t}` LIMIT 2")
                for i, r in enumerate(cur.fetchall(), 1):
                    print(f"    [{i}] {dict(r)}")

            # ── HIP 3: match por NAME ─────────────────────────────────────
            print("\n=== HIP 3: match por NAME ===")
            cur.execute(
                """
                SELECT COUNT(DISTINCT p.id) AS n
                  FROM cbr_parametros_boleto p
                  JOIN sindi_sindicatos s
                    ON UPPER(TRIM(s.name)) = UPPER(TRIM(p.name))
                 WHERE p.deleted = 0 AND s.deleted = 0
                """
            )
            n_exato = cur.fetchone()["n"]
            print(f"  parâmetros com match exato: {n_exato}/87")

            cur.execute(
                """
                SELECT p.name AS pn, s.name AS sn
                  FROM cbr_parametros_boleto p
                  JOIN sindi_sindicatos s
                    ON (UPPER(p.name) LIKE CONCAT('%', UPPER(s.name), '%')
                        OR UPPER(s.name) LIKE CONCAT('%', UPPER(p.name), '%'))
                 WHERE p.deleted = 0 AND s.deleted = 0
                 LIMIT 10
                """
            )
            print(f"\n  matches parciais (LIKE), até 10 amostras:")
            for r in cur.fetchall():
                print(f"    [{r['pn']}]  ↔  [{r['sn']}]")


if __name__ == "__main__":
    main()
