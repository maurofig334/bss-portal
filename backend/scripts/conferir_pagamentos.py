"""
Confere o sync do contas a pagar contra a realidade esperada.

Uso (na OCI):
    venv/bin/python -m scripts.conferir_pagamentos

Depois de sincronizar 10.288 pagamentos, valida o que dá pra validar sem o
legado: distribuição de status (deve ser quase tudo 'pendente', porque a baixa
raramente era dada no SuiteCRM), parcelas por benefício (deve refletir a regra
do sindicato — falecimento em 6, alguns em 11), e soma de valores por status.

SOMENTE LEITURA.
"""

from app.database import get_pg_connection


def _q(cur, titulo, sql):
    print(f"\n=== {titulo} ===")
    cur.execute(sql)
    for r in cur.fetchall():
        print("  " + "  ".join(f"{k}={v}" for k, v in r.items()))


def main() -> None:
    with get_pg_connection() as conn, conn.cursor() as cur:

        cur.execute("SELECT COUNT(*) AS n FROM bss.pagamento")
        print(f"Total em bss.pagamento: {cur.fetchone()['n']:,}")

        _q(cur, "Status (esperado: quase tudo pendente)",
           """SELECT status, COUNT(*) AS qtd,
                     TO_CHAR(SUM(valor), 'FM999G999G990D00') AS valor_total
                FROM bss.pagamento GROUP BY status ORDER BY qtd DESC""")

        _q(cur, "Forma de pagamento",
           """SELECT forma_pagamento, COUNT(*) AS qtd
                FROM bss.pagamento GROUP BY forma_pagamento ORDER BY qtd DESC""")

        _q(cur, "Parcelas por benefício (a regra do sindicato)",
           """SELECT n_parcelas, COUNT(*) AS beneficios FROM (
                   SELECT id_processo, MAX(parcela) AS n_parcelas
                     FROM bss.pagamento GROUP BY id_processo
                ) x GROUP BY n_parcelas ORDER BY n_parcelas""")

        _q(cur, "Vencendo / vencidos (pendentes)",
           """SELECT
                  COUNT(*) FILTER (WHERE data_vencimento < CURRENT_DATE) AS vencidos,
                  COUNT(*) FILTER (WHERE data_vencimento >= CURRENT_DATE) AS a_vencer,
                  COUNT(*) FILTER (WHERE data_vencimento IS NULL)         AS sem_data
                FROM bss.pagamento WHERE status = 'pendente'""")

        # Amostra de um benefício parcelado, pra olhar de perto.
        print("\n=== Amostra: um benefício com 6 parcelas ===")
        cur.execute(
            """
            SELECT id_processo FROM bss.pagamento
             GROUP BY id_processo HAVING MAX(parcela) = 6 LIMIT 1
            """
        )
        r = cur.fetchone()
        if r:
            cur.execute(
                """
                SELECT parcela, valor, status, data_prevista, data_vencimento,
                       data_pagamento, beneficiario_nome
                  FROM bss.pagamento
                 WHERE id_processo = %s ORDER BY parcela
                """,
                (r["id_processo"],),
            )
            for p in cur.fetchall():
                print(f"  parcela {p['parcela']}: R$ {p['valor']} | {p['status']} "
                      f"| prev {p['data_prevista']} | venc {p['data_vencimento']} "
                      f"| {p['beneficiario_nome']}")

    print()


if __name__ == "__main__":
    main()
