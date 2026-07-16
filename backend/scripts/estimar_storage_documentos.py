"""
Estima o VOLUME de documentos a migrar do SuiteCRM para o storage do BSS.

Contexto (decisão do Mauro, 01/07/2026):
  - Processos ABERTOS      → migrar TODOS os documentos (todas as versões).
  - Processos ENCERRADOS   → a confirmar com a BSS; provavelmente apenas a
                             ÚLTIMA versão de cada (processo × categoria).

LIMITAÇÃO: o SuiteCRM NÃO guarda o tamanho do arquivo no banco. Os binários
ficam no filesystem do servidor da aplicação, em `upload/`, nomeados pelo
document_revision_id. Este script entrega as CONTAGENS por escopo; o tamanho
médio tem que sair do servidor (ver comando no rodapé da saída).

Estimativa final = contagem_do_escopo × tamanho_médio_por_arquivo.

READ-ONLY. Uso (do diretório backend/, com venv ativa):
    python -m scripts.estimar_storage_documentos
"""

from app.database import get_mysql_connection
from app.config import settings


def secao(titulo: str) -> None:
    print(f"\n--- {titulo} ---")


def main() -> None:
    print("=" * 84)
    print(f"Estimativa de storage: documentos de processo ({settings.MYSQL_DB})")
    print("=" * 84)

    with get_mysql_connection() as conn:
        with conn.cursor() as cur:

            # Como o legado marca aberto/encerrado?
            secao("cases.state e cases.status (valores em uso)")
            for coluna in ("state", "status"):
                try:
                    cur.execute(f"""
                        SELECT {coluna} AS v, COUNT(*) AS n
                          FROM cases WHERE deleted = 0
                         GROUP BY {coluna} ORDER BY n DESC LIMIT 15
                    """)
                    print(f"  cases.{coluna}:")
                    for r in cur.fetchall():
                        print(f"    {str(r['v'])[:40]:40s} {r['n']:>7,}")
                except Exception as e:
                    print(f"  cases.{coluna}: (erro: {e})")

            # Total de documentos vinculados a processo
            secao("Documentos vinculados a processo (documents_cases)")
            cur.execute("""
                SELECT COUNT(*) AS docs, COUNT(DISTINCT dc.case_id) AS processos
                  FROM documents_cases dc
                  JOIN documents d ON d.id = dc.document_id AND d.deleted = 0
                 WHERE dc.deleted = 0
            """)
            r = cur.fetchone()
            print(f"  {r['docs']:,} documentos em {r['processos']:,} processos")

            # Quebra por estado do processo (aberto x encerrado)
            secao("Documentos por estado do processo")
            try:
                cur.execute("""
                    SELECT c.state AS estado,
                           COUNT(*) AS docs,
                           COUNT(DISTINCT dc.case_id) AS processos
                      FROM documents_cases dc
                      JOIN documents d ON d.id = dc.document_id AND d.deleted = 0
                      JOIN cases c     ON c.id = dc.case_id AND c.deleted = 0
                     WHERE dc.deleted = 0
                     GROUP BY c.state
                     ORDER BY docs DESC
                """)
                for r in cur.fetchall():
                    print(f"    {str(r['estado']):15s} {r['docs']:>7,} documentos "
                          f"· {r['processos']:>6,} processos")
            except Exception as e:
                print(f"    (erro: {e})")

            # ENCERRADOS: todos x apenas a última versão por (processo, categoria)
            secao("ENCERRADOS: todos os documentos x apenas a última versão")
            try:
                cur.execute("""
                    SELECT COUNT(*) AS todos
                      FROM documents_cases dc
                      JOIN documents d ON d.id = dc.document_id AND d.deleted = 0
                      JOIN cases c     ON c.id = dc.case_id AND c.deleted = 0
                     WHERE dc.deleted = 0 AND c.state = 'Closed'
                """)
                todos = cur.fetchone()["todos"]

                # "Última versão" = 1 por (processo, categoria), a mais recente
                cur.execute("""
                    SELECT COUNT(*) AS ultimas FROM (
                        SELECT dc.case_id, d.category_id
                          FROM documents_cases dc
                          JOIN documents d ON d.id = dc.document_id AND d.deleted = 0
                          JOIN cases c     ON c.id = dc.case_id AND c.deleted = 0
                         WHERE dc.deleted = 0 AND c.state = 'Closed'
                         GROUP BY dc.case_id, d.category_id
                    ) x
                """)
                ultimas = cur.fetchone()["ultimas"]
                economia = todos - ultimas
                pct = (economia / todos * 100) if todos else 0
                print(f"    todos:          {todos:>7,}")
                print(f"    só a última:    {ultimas:>7,}")
                print(f"    economia:       {economia:>7,}  ({pct:.1f}% menos arquivos)")
                print("    NOTA: 'última por (processo, categoria)' junta frente/verso num só —")
                print("          confirmar com a BSS se isso é aceitável (pode perder páginas).")
            except Exception as e:
                print(f"    (erro: {e})")

            # ABERTOS: todos (decisão já tomada)
            secao("ABERTOS: todos os documentos (decisão: migrar tudo)")
            try:
                cur.execute("""
                    SELECT COUNT(*) AS docs
                      FROM documents_cases dc
                      JOIN documents d ON d.id = dc.document_id AND d.deleted = 0
                      JOIN cases c     ON c.id = dc.case_id AND c.deleted = 0
                     WHERE dc.deleted = 0 AND (c.state IS NULL OR c.state <> 'Closed')
                """)
                print(f"    {cur.fetchone()['docs']:,} documentos")
            except Exception as e:
                print(f"    (erro: {e})")

            # Quebra por extensão — ajuda a estimar peso médio
            secao("Documentos de processo por extensão (top 15)")
            try:
                cur.execute("""
                    SELECT LOWER(COALESCE(dr.file_ext, '?')) AS ext,
                           COUNT(*) AS n
                      FROM documents_cases dc
                      JOIN documents d ON d.id = dc.document_id AND d.deleted = 0
                      LEFT JOIN document_revisions dr ON dr.id = d.document_revision_id
                     WHERE dc.deleted = 0
                     GROUP BY LOWER(COALESCE(dr.file_ext, '?'))
                     ORDER BY n DESC LIMIT 15
                """)
                for r in cur.fetchall():
                    print(f"    {r['ext']:10s} {r['n']:>7,}")
            except Exception as e:
                print(f"    (erro: {e})")

            # Revisões: quantos arquivos físicos existem por documento
            secao("Revisões por documento (cada revisão = 1 arquivo no disco)")
            try:
                cur.execute("""
                    SELECT COUNT(*) AS revisoes
                      FROM document_revisions dr
                      JOIN documents d ON d.id = dr.document_id AND d.deleted = 0
                      JOIN documents_cases dc ON dc.document_id = d.id AND dc.deleted = 0
                     WHERE dr.deleted = 0
                """)
                print(f"    {cur.fetchone()['revisoes']:,} revisões de documentos de processo")
                print("    (o BSS só precisa da revisão corrente: documents.document_revision_id)")
            except Exception as e:
                print(f"    (erro: {e})")

    print("\n" + "=" * 84)
    print("FALTA O TAMANHO MÉDIO — rode no servidor do SuiteCRM (onde fica o upload/):")
    print("""
    cd <raiz_do_suitecrm>
    du -sh upload/
    find upload/ -maxdepth 1 -type f -printf '%s\\n' \\
      | awk '{s+=$1; n++} END {printf "arquivos=%d  total=%.2f GB  media=%.0f KB\\n", n, s/1073741824, (s/n)/1024}'
    """)
    print("Estimativa = contagem do escopo x tamanho médio.")
    print("=" * 84)


if __name__ == "__main__":
    main()
