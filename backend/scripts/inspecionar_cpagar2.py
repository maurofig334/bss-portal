"""
Segundo olhar no contas a pagar do legado — os detalhes que decidem o sync.

Uso (na OCI):
    venv/bin/python -m scripts.inspecionar_cpagar2

O primeiro script achou as tabelas e colunas. Faltam 4 respostas antes de
escrever o sync, e todas são do tipo "não adivinhar":

  1. Quais valores status_c assume? → mapear pra 'pendente'/'pago'/'cancelado'
  2. Quais valores forma_pagto_c assume?
  3. PARCELA: um case pode ter vários pagar? (falecimento é parcelado) — se
     sim, a parcela precisa ser derivada, porque não há coluna de parcela.
  4. Os pagar linkam a cases que EXISTEM no bss? (senão viram órfãos)

SOMENTE LEITURA.
"""

from app.database import get_mysql_connection


def _dist(cur, titulo, sql):
    print(f"\n=== {titulo} ===")
    cur.execute(sql)
    for r in cur.fetchall():
        vals = list(r.values())
        print("  " + "  ".join(str(v) for v in vals))


def main() -> None:
    with get_mysql_connection() as conn, conn.cursor() as cur:

        _dist(cur, "status_c — distribuição",
              """SELECT status_c AS status, COUNT(*) AS n
                   FROM pagar_contas_a_pagar_cstm
                  GROUP BY status_c ORDER BY n DESC""")

        _dist(cur, "forma_pagto_c — distribuição",
              """SELECT forma_pagto_c AS forma, COUNT(*) AS n
                   FROM pagar_contas_a_pagar_cstm
                  GROUP BY forma_pagto_c ORDER BY n DESC LIMIT 20""")

        _dist(cur, "tipo_conta_c / detalhe_conta_c",
              """SELECT tipo_conta_c, detalhe_conta_c, COUNT(*) AS n
                   FROM pagar_contas_a_pagar_cstm
                  GROUP BY tipo_conta_c, detalhe_conta_c ORDER BY n DESC LIMIT 20""")

        # 3. PARCELAS: quantos pagar cada case tem?
        print("\n=== PARCELAS: pagar por case ===")
        cur.execute(
            """
            SELECT qtd_pagar, COUNT(*) AS qtd_cases
              FROM (
                SELECT cases_pagar_contas_a_pagar_1cases_ida AS case_id,
                       COUNT(*) AS qtd_pagar
                  FROM cases_pagar_contas_a_pagar_1_c
                 WHERE deleted = 0
                 GROUP BY cases_pagar_contas_a_pagar_1cases_ida
              ) x
             GROUP BY qtd_pagar
             ORDER BY qtd_pagar
            """
        )
        for r in cur.fetchall():
            print(f"  {r['qtd_pagar']} parcela(s): {r['qtd_cases']:,} benefícios")

        # 4. Amostra REAL do _cstm com o name da base (protocolo+tipo).
        print("\n=== AMOSTRA (cstm + name da base) ===")
        cur.execute(
            """
            SELECT b.name,
                   c.id_cpagar_c, c.valor_c, c.status_c,
                   c.data_prevista_c, c.data_vencimento_c, c.data_pagamento_c,
                   c.forma_pagto_c, c.beneficiario_c, c.cpf_c,
                   c.documemto_c
              FROM pagar_contas_a_pagar b
              JOIN pagar_contas_a_pagar_cstm c ON c.id_c = b.id
             WHERE b.deleted = 0
             ORDER BY c.id_cpagar_c DESC
             LIMIT 8
            """
        )
        for r in cur.fetchall():
            print(f"\n  name={r['name']}  cpagar={r['id_cpagar_c']}")
            for k in ("valor_c", "status_c", "data_prevista_c", "data_vencimento_c",
                      "data_pagamento_c", "forma_pagto_c", "beneficiario_c", "cpf_c",
                      "documemto_c"):
                if r[k] not in (None, "", 0):
                    print(f"      {k:<20} {r[k]}")

        # 5. Os pagar apontam pra cases que existem no BSS? (via id_legado_uuid)
        print("\n=== LIGAÇÃO com bss.processo_beneficio ===")
        cur.execute(
            """
            SELECT COUNT(*) AS total_links,
                   COUNT(DISTINCT cases_pagar_contas_a_pagar_1cases_ida) AS cases_distintos
              FROM cases_pagar_contas_a_pagar_1_c
             WHERE deleted = 0
            """
        )
        r = cur.fetchone()
        print(f"  vínculos case↔pagar: {r['total_links']:,}")
        print(f"  cases distintos com pagar: {r['cases_distintos']:,}")
        print("  (comparar com quantos desses id existem em bss.processo_beneficio.")
        print("   id_legado_uuid — faço isso no sync; aqui só confirmo o volume)")

        # 6. id_cpagar_c é único e não-nulo? (vai virar numero_pagamento)
        _dist(cur, "id_cpagar_c — nulos e duplicados",
              """SELECT
                   SUM(id_cpagar_c IS NULL) AS nulos,
                   COUNT(*) - COUNT(DISTINCT id_cpagar_c) AS duplicados,
                   MIN(id_cpagar_c) AS menor, MAX(id_cpagar_c) AS maior
                 FROM pagar_contas_a_pagar_cstm""")

    print()


if __name__ == "__main__":
    main()
