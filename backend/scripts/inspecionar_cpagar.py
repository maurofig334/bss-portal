"""
Acha e descreve a(s) tabela(s) de CONTAS A PAGAR no SuiteCRM legado.

Uso (do diretório backend/, na OCI — só de lá há rota pro MySQL):
    venv/bin/python -m scripts.inspecionar_cpagar

POR QUE
-------
bss.pagamento existe no schema (numero_pagamento = id_cpagar_c) e a aba de
Pagamentos do processo já a lê — mas NÃO HÁ SYNC que a preencha. A tabela está
vazia. Antes de construir o módulo de contas a pagar, é preciso trazer o dado,
e pra trazer é preciso ver a estrutura no legado.

Este script NÃO adivinha o nome da tabela — procura por qualquer coisa com
'cpagar'/'pagar'/'pagamento' no nome, mostra as colunas de cada uma, o volume,
e como ela se liga aos cases (benefícios). É o mesmo cuidado do protocolo:
olhar o legado antes de assumir.

SOMENTE LEITURA.
"""

from app.database import get_mysql_connection


def main() -> None:
    with get_mysql_connection() as conn, conn.cursor() as cur:

        # 1. Quais tabelas cheiram a contas a pagar?
        cur.execute(
            """
            SELECT TABLE_NAME,
                   TABLE_ROWS
              FROM information_schema.TABLES
             WHERE TABLE_SCHEMA = DATABASE()
               AND (TABLE_NAME LIKE '%%cpagar%%'
                 OR TABLE_NAME LIKE '%%pagar%%'
                 OR TABLE_NAME LIKE '%%pagamento%%'
                 OR TABLE_NAME LIKE '%%parcela%%')
             ORDER BY TABLE_NAME
            """
        )
        tabelas = cur.fetchall()
        if not tabelas:
            print("Nenhuma tabela com cpagar/pagar/pagamento/parcela no nome.")
            print("O contas a pagar pode ter outro nome — me diga qual módulo é")
            print("no SuiteCRM (label da tela) que eu procuro pelo caminho certo.")
            return

        print("=== TABELAS CANDIDATAS ===")
        for t in tabelas:
            print(f"  {t['TABLE_NAME']:<40} ~{t['TABLE_ROWS'] or 0:>10} linhas (estimado)")

        # 2. Colunas de cada candidata (a principal costuma ser a com mais
        #    colunas ou o par base + _cstm, como cases/cases_cstm).
        for t in tabelas:
            nome = t["TABLE_NAME"]
            print(f"\n{'='*60}\nCOLUNAS de {nome}\n{'='*60}")
            cur.execute(
                """
                SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE
                  FROM information_schema.COLUMNS
                 WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
                 ORDER BY ORDINAL_POSITION
                """,
                (nome,),
            )
            for c in cur.fetchall():
                tam = f"({c['CHARACTER_MAXIMUM_LENGTH']})" if c["CHARACTER_MAXIMUM_LENGTH"] else ""
                nul = "" if c["IS_NULLABLE"] == "YES" else " NOT NULL"
                print(f"  {c['COLUMN_NAME']:<34} {c['DATA_TYPE']}{tam}{nul}")

            # Contagem real (TABLE_ROWS é estimativa do otimizador).
            try:
                cur.execute(f"SELECT COUNT(*) AS n FROM `{nome}`")
                print(f"\n  contagem REAL: {cur.fetchone()['n']:,}")
            except Exception as e:
                print(f"  (não consegui contar: {e})")

            # Como liga aos cases? Procura coluna que referencie case/processo.
            cur.execute(
                """
                SELECT COLUMN_NAME
                  FROM information_schema.COLUMNS
                 WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
                   AND (COLUMN_NAME LIKE '%%case%%'
                     OR COLUMN_NAME LIKE '%%processo%%'
                     OR COLUMN_NAME LIKE '%%beneficio%%'
                     OR COLUMN_NAME LIKE '%%parent%%')
                """,
                (nome,),
            )
            liga = [r["COLUMN_NAME"] for r in cur.fetchall()]
            if liga:
                print(f"  liga aos cases via: {', '.join(liga)}")

        # 3. Uma amostra da tabela mais promissora (a que tem 'cpagar' e mais
        #    linhas), pra ver os dados de verdade — status, valores, datas.
        principal = None
        for t in sorted(tabelas, key=lambda x: -(x["TABLE_ROWS"] or 0)):
            if "cstm" not in t["TABLE_NAME"]:   # prefere a base, não a _cstm
                principal = t["TABLE_NAME"]
                break
        principal = principal or tabelas[0]["TABLE_NAME"]

        print(f"\n{'='*60}\nAMOSTRA de {principal} (5 linhas)\n{'='*60}")
        try:
            cur.execute(f"SELECT * FROM `{principal}` "
                        f"WHERE deleted = 0 LIMIT 5")
        except Exception:
            cur.execute(f"SELECT * FROM `{principal}` LIMIT 5")
        linhas = cur.fetchall()
        for i, row in enumerate(linhas, 1):
            print(f"\n--- linha {i}")
            for k, v in row.items():
                if v not in (None, "", 0):
                    print(f"  {k:<30} {v}")

        # 4. Distribuição de status, se houver coluna de status.
        cur.execute(
            """
            SELECT COLUMN_NAME FROM information_schema.COLUMNS
             WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
               AND COLUMN_NAME LIKE '%%status%%'
            """,
            (principal,),
        )
        cols_status = [r["COLUMN_NAME"] for r in cur.fetchall()]
        for col in cols_status:
            print(f"\n=== {principal}.{col} — distribuição ===")
            try:
                cur.execute(f"SELECT `{col}` AS v, COUNT(*) AS n FROM `{principal}` "
                            f"GROUP BY `{col}` ORDER BY n DESC LIMIT 15")
                for r in cur.fetchall():
                    print(f"  {str(r['v']):<30} {r['n']:,}")
            except Exception as e:
                print(f"  (falhou: {e})")

    print()


if __name__ == "__main__":
    main()
