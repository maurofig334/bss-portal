"""
Inspeciona a estrutura da tabela de boletos no MySQL legado SuiteCRM,
focando em colunas que contenham CNPJ — pra descobrir o vínculo correto
entre bolet_boletos e accounts (empresas).

A migração inicial puxou só id_sindicato. id_empresa ficou NULL em todos
os 162k boletos. Precisamos descobrir qual coluna do legado tem CNPJ,
fazer match com bss.empresa.cnpj, e atualizar bss.boleto.id_empresa.

Uso (do diretório backend/, com venv ativa):
    python -m scripts.inspecionar_legado_boleto
"""

from app.database import get_mysql_connection
from app.config import settings


TABELAS = ["bolet_boletos", "bolet_boletos_cstm"]


def listar_colunas(cur, tabela: str) -> list[dict]:
    cur.execute(
        """
        SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_KEY
          FROM information_schema.COLUMNS
         WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
         ORDER BY ORDINAL_POSITION
        """,
        (settings.MYSQL_DB, tabela),
    )
    return cur.fetchall()


def existe_tabela(cur, tabela: str) -> bool:
    cur.execute(
        """
        SELECT 1 FROM information_schema.TABLES
         WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
        """,
        (settings.MYSQL_DB, tabela),
    )
    return cur.fetchone() is not None


def main() -> None:
    print("=" * 80)
    print(f"Inspeção: tabelas de boletos no MySQL legado ({settings.MYSQL_DB})")
    print("=" * 80)

    with get_mysql_connection() as conn:
        with conn.cursor() as cur:
            for tabela in TABELAS:
                print(f"\n--- Tabela: {tabela} ---")
                if not existe_tabela(cur, tabela):
                    print("  (não existe)")
                    continue
                cols = listar_colunas(cur, tabela)
                print(f"  Total: {len(cols)} colunas")
                # Filtra colunas potencialmente úteis pra descobrir empresa:
                relevantes = [
                    c for c in cols
                    if any(t in c["COLUMN_NAME"].lower()
                           for t in ["cnpj", "cpf", "doc", "empresa",
                                     "account", "razao", "patronal", "id_c"])
                ]
                if relevantes:
                    print(f"  Colunas com cnpj/empresa/account/id_c:")
                    for c in relevantes:
                        print(f"    {c['COLUMN_NAME']:40s} {c['COLUMN_TYPE']:20s} "
                              f"NULL={c['IS_NULLABLE']:4s} KEY={c['COLUMN_KEY']}")

            # Amostra de 3 registros (campos resumidos):
            print("\n--- Amostra de 3 boletos do legado ---")
            cur.execute("""
                SELECT b.id, b.name, b.assigned_user_id,
                       b.date_entered, b.deleted
                  FROM bolet_boletos b
                 WHERE b.deleted = 0
                 ORDER BY b.date_entered DESC
                 LIMIT 3
            """)
            for r in cur.fetchall():
                print(f"  id={r['id'][:13]}... name={r['name']!r}")

            # Procurar campo CNPJ em qualquer tabela do legado:
            print("\n--- Tabelas que têm coluna 'cnpj' ou similar ---")
            cur.execute("""
                SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE
                  FROM information_schema.COLUMNS
                 WHERE TABLE_SCHEMA = %s
                   AND (COLUMN_NAME LIKE '%%cnpj%%' OR COLUMN_NAME LIKE '%%CNPJ%%')
                 ORDER BY TABLE_NAME, COLUMN_NAME
            """, (settings.MYSQL_DB,))
            for r in cur.fetchall():
                print(f"  {r['TABLE_NAME']:50s} {r['COLUMN_NAME']:30s} {r['COLUMN_TYPE']}")

            # Tabelas de relacionamento bolet_boletos × accounts:
            print("\n--- Tabelas de relacionamento bolet × accounts ---")
            cur.execute("""
                SELECT TABLE_NAME
                  FROM information_schema.TABLES
                 WHERE TABLE_SCHEMA = %s
                   AND TABLE_NAME LIKE '%%bolet%%account%%'
            """, (settings.MYSQL_DB,))
            for r in cur.fetchall():
                print(f"  {r['TABLE_NAME']}")

            # Idem com 'traba_trabalhadores':
            cur.execute("""
                SELECT TABLE_NAME
                  FROM information_schema.TABLES
                 WHERE TABLE_SCHEMA = %s
                   AND TABLE_NAME LIKE '%%bolet%%traba%%'
            """, (settings.MYSQL_DB,))
            print("\n--- Tabelas de relacionamento bolet × trabalhadores ---")
            for r in cur.fetchall():
                print(f"  {r['TABLE_NAME']}")


if __name__ == "__main__":
    main()
