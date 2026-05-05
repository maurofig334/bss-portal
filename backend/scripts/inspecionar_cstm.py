"""
Lista as colunas de uma tabela do legado SuiteCRM (útil pra mapear *_cstm).

Uso (do diretório backend/, com venv ativa):
    python -m scripts.inspecionar_cstm sindi_sindicatos_cstm
    python -m scripts.inspecionar_cstm accounts_cstm
    python -m scripts.inspecionar_cstm traba_trabalhadores_cstm
"""

import sys

from app.config import settings
from app.database import get_mysql_connection


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python -m scripts.inspecionar_cstm <nome_da_tabela>")
        sys.exit(1)

    tabela = sys.argv[1]

    with get_mysql_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT
                  FROM information_schema.COLUMNS
                 WHERE TABLE_SCHEMA = %s
                   AND TABLE_NAME   = %s
                 ORDER BY ORDINAL_POSITION
                """,
                (settings.MYSQL_DB, tabela),
            )
            rows = cur.fetchall()

    if not rows:
        print(f"Tabela '{tabela}' não encontrada no banco '{settings.MYSQL_DB}'")
        sys.exit(1)

    print(f"\nColunas de {settings.MYSQL_DB}.{tabela}:")
    print("-" * 80)
    for r in rows:
        nullable = "NULL" if r["IS_NULLABLE"] == "YES" else "NOT NULL"
        print(f"  {r['COLUMN_NAME']:<40} {r['COLUMN_TYPE']:<30} {nullable}")
    print(f"\nTotal: {len(rows)} colunas\n")


if __name__ == "__main__":
    main()
