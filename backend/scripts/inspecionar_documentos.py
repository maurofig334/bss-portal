"""
Inspeciona a estrutura de DOCUMENTOS no MySQL legado (SuiteCRM), pra modelar
o módulo de Documentos do BSS (épico #22).

Perguntas que este script responde:
  1. Como é a tabela `documents` (68k registros) e a `documents_cstm`?
  2. Onde ficam os STATUS do documento (aceito/rasurado/incompleto/rejeitado)
     e quais são os valores reais em uso?
  3. Qual o VÍNCULO entre `cases` (processo de benefício) e os documentos?
     - O mapeamento só listava `bolet_boletos_documents_1_c` (boletos).
     - Pode ser outra tabela de relacionamento, ou `notes` (anexos por parent).
  4. Existe uma CATEGORIA/TIPO de documento (certidão de óbito, CTPS, etc.)?

READ-ONLY: só faz SELECT em information_schema e amostras. A réplica é
blindada com SET SESSION TRANSACTION READ ONLY em app/database.py.

Uso (do diretório backend/, com venv ativa):
    python -m scripts.inspecionar_documentos
"""

from app.database import get_mysql_connection
from app.config import settings


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


def contar(cur, tabela: str, where: str = "1=1") -> int:
    cur.execute(f"SELECT COUNT(*) AS n FROM {tabela} WHERE {where}")
    return cur.fetchone()["n"]


def distintos(cur, tabela: str, coluna: str, limite: int = 30) -> None:
    """Mostra valores distintos de uma coluna com contagem (top N)."""
    try:
        cur.execute(
            f"""
            SELECT {coluna} AS v, COUNT(*) AS n
              FROM {tabela}
             GROUP BY {coluna}
             ORDER BY n DESC
             LIMIT {limite}
            """
        )
        for r in cur.fetchall():
            print(f"    {str(r['v'])[:45]:45s} {r['n']:>8,}")
    except Exception as e:
        print(f"    (erro: {e})")


def main() -> None:
    print("=" * 84)
    print(f"Inspeção: DOCUMENTOS no legado ({settings.MYSQL_DB})")
    print("=" * 84)

    with get_mysql_connection() as conn:
        with conn.cursor() as cur:

            # ---------------------------------------------------------------
            # 1. Estrutura de documents / documents_cstm
            # ---------------------------------------------------------------
            for tabela in ["documents", "documents_cstm", "document_revisions"]:
                print(f"\n--- Tabela: {tabela} ---")
                if not existe_tabela(cur, tabela):
                    print("  (não existe)")
                    continue
                cols = listar_colunas(cur, tabela)
                print(f"  {len(cols)} colunas · {contar(cur, tabela):,} registros")
                for c in cols:
                    print(f"    {c['COLUMN_NAME']:38s} {c['COLUMN_TYPE']:24s} "
                          f"NULL={c['IS_NULLABLE']:4s} KEY={c['COLUMN_KEY']}")

            # ---------------------------------------------------------------
            # 2. Status e categorias reais em uso
            # ---------------------------------------------------------------
            if existe_tabela(cur, "documents"):
                print("\n--- documents.status_id (valores em uso) ---")
                distintos(cur, "documents", "status_id")
                print("\n--- documents.category_id (valores em uso) ---")
                distintos(cur, "documents", "category_id")
                print("\n--- documents.subcategory_id (valores em uso) ---")
                distintos(cur, "documents", "subcategory_id")
                print("\n--- documents: ativos x deletados ---")
                print(f"    deleted=0: {contar(cur, 'documents', 'deleted=0'):,}")
                print(f"    deleted=1: {contar(cur, 'documents', 'deleted=1'):,}")

            # Campos custom podem guardar o status real:
            if existe_tabela(cur, "documents_cstm"):
                print("\n--- documents_cstm: valores por coluna custom ---")
                for c in listar_colunas(cur, "documents_cstm"):
                    nome = c["COLUMN_NAME"]
                    if nome.lower().startswith("id_c"):
                        continue
                    print(f"  · {nome}")
                    distintos(cur, "documents_cstm", nome, limite=12)

            # ---------------------------------------------------------------
            # 3. Vínculo com cases (processo de benefício)
            # ---------------------------------------------------------------
            print("\n--- Tabelas que citam 'document' no nome ---")
            cur.execute(
                """
                SELECT TABLE_NAME, TABLE_ROWS
                  FROM information_schema.TABLES
                 WHERE TABLE_SCHEMA = %s AND TABLE_NAME LIKE '%%document%%'
                 ORDER BY TABLE_NAME
                """,
                (settings.MYSQL_DB,),
            )
            for r in cur.fetchall():
                print(f"    {r['TABLE_NAME']:55s} ~{r['TABLE_ROWS'] or 0:,} linhas")

            print("\n--- Tabelas que citam 'case' no nome (procurando o vínculo) ---")
            cur.execute(
                """
                SELECT TABLE_NAME, TABLE_ROWS
                  FROM information_schema.TABLES
                 WHERE TABLE_SCHEMA = %s AND TABLE_NAME LIKE '%%case%%'
                 ORDER BY TABLE_NAME
                """,
                (settings.MYSQL_DB,),
            )
            for r in cur.fetchall():
                print(f"    {r['TABLE_NAME']:55s} ~{r['TABLE_ROWS'] or 0:,} linhas")

            # ---------------------------------------------------------------
            # 4. `notes` — no SuiteCRM anexos costumam ficar aqui, por parent
            # ---------------------------------------------------------------
            if existe_tabela(cur, "notes"):
                print("\n--- notes: total e distribuição por parent_type ---")
                print(f"    total (deleted=0): {contar(cur, 'notes', 'deleted=0'):,}")
                distintos(cur, "notes", "parent_type")
                print("\n--- notes: quantos têm arquivo anexado? ---")
                try:
                    cur.execute("""
                        SELECT parent_type,
                               COUNT(*) AS total,
                               SUM(filename IS NOT NULL AND filename <> '') AS com_arquivo
                          FROM notes
                         WHERE deleted = 0
                         GROUP BY parent_type
                         ORDER BY com_arquivo DESC
                    """)
                    for r in cur.fetchall():
                        print(f"    {str(r['parent_type']):20s} total={r['total']:>7,} "
                              f"com_arquivo={r['com_arquivo'] or 0:>7,}")
                except Exception as e:
                    print(f"    (erro: {e})")

                print("\n--- notes de Cases: amostra de 5 (nome do arquivo) ---")
                try:
                    cur.execute("""
                        SELECT id, name, filename, file_mime_type, date_entered
                          FROM notes
                         WHERE deleted = 0 AND parent_type = 'Cases'
                               AND filename IS NOT NULL AND filename <> ''
                         ORDER BY date_entered DESC
                         LIMIT 5
                    """)
                    for r in cur.fetchall():
                        print(f"    {str(r['name'])[:38]:38s} | {str(r['filename'])[:32]:32s} | {r['file_mime_type']}")
                except Exception as e:
                    print(f"    (erro: {e})")

            # ---------------------------------------------------------------
            # 5. Amostra de documents ligados a algo
            # ---------------------------------------------------------------
            if existe_tabela(cur, "documents"):
                print("\n--- documents: amostra de 5 (deleted=0) ---")
                cur.execute("""
                    SELECT id, document_name, filename, status_id,
                           category_id, date_entered
                      FROM documents
                     WHERE deleted = 0
                     ORDER BY date_entered DESC
                     LIMIT 5
                """)
                for r in cur.fetchall():
                    print(f"    {str(r['document_name'])[:34]:34s} | {str(r['filename'])[:26]:26s} "
                          f"| status={r['status_id']} cat={r['category_id']}")

    print("\n" + "=" * 84)
    print("Fim. Cole a saída no chat pra modelarmos o sync e as regras.")
    print("=" * 84)


if __name__ == "__main__":
    main()
