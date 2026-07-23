"""
Terceiro (e último) olhar: as parcelas são reais ou duplicação?

Uso (na OCI):
    venv/bin/python -m scripts.inspecionar_cpagar3

O cpagar2 mostrou 454 benefícios com EXATAMENTE 11 parcelas, 39 com 22, 22 com
33 — tudo múltiplo de 11. Parcelamento real seria espalhado (2, 3, 5...), não
grudado em múltiplos de 11. Isso cheira a duplicação na tabela de junção, igual
ao "case clonado" que quebrou o protocolo.

A diferença decide o sync:
  - se são pagar DISTINTOS (UUIDs diferentes, valores/datas diferentes) →
    parcelamento real, deriva parcela normalmente;
  - se é o MESMO pagar linkado N vezes → junção duplicada, tem que DISTINCT.

Também confere data_pagamento_c: se o status é sempre 'Aberto', é ela que diz
se o benefício foi pago.

SOMENTE LEITURA.
"""

from app.database import get_mysql_connection


def main() -> None:
    with get_mysql_connection() as conn, conn.cursor() as cur:

        # 1. Pega um case com 11 parcelas e olha os pagar dele de perto.
        cur.execute(
            """
            SELECT cases_pagar_contas_a_pagar_1cases_ida AS case_id, COUNT(*) AS n
              FROM cases_pagar_contas_a_pagar_1_c
             WHERE deleted = 0
             GROUP BY cases_pagar_contas_a_pagar_1cases_ida
            HAVING COUNT(*) = 11
             LIMIT 1
            """
        )
        r = cur.fetchone()
        if not r:
            print("Nenhum case com 11 parcelas — pulando teste 1.")
        else:
            case_id = r["case_id"]
            print(f"=== CASE com 11 parcelas: {case_id} ===")

            # Os pagar_id linkados são distintos ou repetidos?
            cur.execute(
                """
                SELECT cases_pagar_contas_a_pagar_1pagar_contas_a_pagar_idb AS pagar_id,
                       COUNT(*) AS vezes
                  FROM cases_pagar_contas_a_pagar_1_c
                 WHERE deleted = 0
                   AND cases_pagar_contas_a_pagar_1cases_ida = %s
                 GROUP BY pagar_id
                """,
                (case_id,),
            )
            links = cur.fetchall()
            distintos = len(links)
            repetido = any(l["vezes"] > 1 for l in links)
            print(f"  pagar_id distintos: {distintos}")
            print(f"  algum pagar_id repetido na junção? {'SIM' if repetido else 'não'}")

            # Os pagar distintos têm valores/datas diferentes? (parcelamento real
            # teria valores iguais e datas escalonadas mês a mês)
            ids = [l["pagar_id"] for l in links]
            marcadores = ",".join(["%s"] * len(ids))
            cur.execute(
                f"""
                SELECT b.name, c.valor_c, c.status_c,
                       c.data_prevista_c, c.data_vencimento_c, c.data_pagamento_c
                  FROM pagar_contas_a_pagar b
                  JOIN pagar_contas_a_pagar_cstm c ON c.id_c = b.id
                 WHERE b.id IN ({marcadores})
                 ORDER BY c.data_prevista_c
                """,
                ids,
            )
            print("  parcelas (name | valor | status | prevista | venc | pgto):")
            for p in cur.fetchall():
                print(f"    {p['name']} | {p['valor_c']} | {p['status_c']} | "
                      f"{p['data_prevista_c']} | {p['data_vencimento_c']} | {p['data_pagamento_c']}")
            print("\n  → datas escalonadas + valores parecidos = parcelamento REAL")
            print("    valores/datas idênticos = duplicação")

        # 2. data_pagamento_c: quantos têm? é ela que marca 'pago'?
        print("\n=== data_pagamento_c — preenchimento vs status ===")
        cur.execute(
            """
            SELECT status_c,
                   COUNT(*) AS total,
                   SUM(data_pagamento_c IS NOT NULL) AS com_data_pgto
              FROM pagar_contas_a_pagar_cstm
             GROUP BY status_c
             ORDER BY total DESC
            """
        )
        for r in cur.fetchall():
            print(f"  status={str(r['status_c']):<10} total={r['total']:<7} "
                  f"com data_pagamento={r['com_data_pgto']}")

        # 3. Quantos pagar no total, e quantos vínculos — pra dimensionar o sync.
        print("\n=== VOLUMES ===")
        cur.execute("SELECT COUNT(*) AS n FROM pagar_contas_a_pagar WHERE deleted = 0")
        print(f"  pagar (base, não deletados): {cur.fetchone()['n']:,}")
        cur.execute("""SELECT COUNT(DISTINCT cases_pagar_contas_a_pagar_1pagar_contas_a_pagar_idb) AS n
                         FROM cases_pagar_contas_a_pagar_1_c WHERE deleted = 0""")
        print(f"  pagar distintos com vínculo a case: {cur.fetchone()['n']:,}")

    print()


if __name__ == "__main__":
    main()
