"""
Mostra amostras de dados de uma tabela do MySQL legado.

Uso:
    python -m scripts.amostra_legado "SELECT status, COUNT(*) FROM cases GROUP BY status"
    python -m scripts.amostra_legado "SELECT * FROM traba_trabalhadores_cases_1_c LIMIT 3"
"""

import sys

from app.database import get_mysql_connection


def main() -> None:
    if len(sys.argv) < 2:
        print('Uso: python -m scripts.amostra_legado "<SQL aqui>"')
        sys.exit(1)
    sql = sys.argv[1]
    with get_mysql_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    if not rows:
        print("(sem resultado)")
        return
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
