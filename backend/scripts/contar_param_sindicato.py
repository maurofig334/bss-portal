"""
Cardinalidade do vínculo cbr_parametros_boleto ↔ sindi_sindicatos.

Responde:
  - quantos sindicatos têm parâmetro cadastrado?
  - quantos parâmetros distintos são referenciados?
  - existe algum parâmetro compartilhado por > 1 sindicato?
"""

from __future__ import annotations

from app.database import get_mysql_connection


def main() -> None:
    with get_mysql_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) AS total_sindicatos,
                    SUM(CASE WHEN sc.cbr_parametros_boleto_id_c IS NOT NULL
                                  AND sc.cbr_parametros_boleto_id_c != ''
                             THEN 1 ELSE 0 END)            AS com_param,
                    COUNT(DISTINCT NULLIF(sc.cbr_parametros_boleto_id_c, '')) AS params_distintos
                  FROM sindi_sindicatos s
                  LEFT JOIN sindi_sindicatos_cstm sc ON sc.id_c = s.id
                 WHERE s.deleted = 0
                """
            )
            r = cur.fetchone()
            print("=== CARDINALIDADE ===")
            print(f"  total sindicatos vivos       : {r['total_sindicatos']}")
            print(f"  com FK pra parâmetro          : {r['com_param']}")
            print(f"  parâmetros distintos referidos: {r['params_distintos']}")
            if r["com_param"] and r["params_distintos"]:
                if r["com_param"] == r["params_distintos"]:
                    print("  → Conclusão: 1:1 (cada sindicato tem seu próprio parâmetro)")
                else:
                    print("  → Conclusão: N:1 (existem parâmetros compartilhados)")

            # Top 5 parâmetros mais compartilhados
            cur.execute(
                """
                SELECT sc.cbr_parametros_boleto_id_c AS pid,
                       p.name                         AS pnome,
                       COUNT(*)                       AS qtd_sindicatos
                  FROM sindi_sindicatos s
                  JOIN sindi_sindicatos_cstm sc ON sc.id_c = s.id
                  LEFT JOIN cbr_parametros_boleto p ON p.id = sc.cbr_parametros_boleto_id_c
                 WHERE s.deleted = 0
                   AND sc.cbr_parametros_boleto_id_c IS NOT NULL
                   AND sc.cbr_parametros_boleto_id_c != ''
                 GROUP BY sc.cbr_parametros_boleto_id_c, p.name
                HAVING COUNT(*) > 1
                 ORDER BY qtd_sindicatos DESC
                 LIMIT 10
                """
            )
            shared = list(cur.fetchall())
            print("\n=== PARÂMETROS COMPARTILHADOS (>1 sindicato) ===")
            if not shared:
                print("  (nenhum — todos os parâmetros são exclusivos de um sindicato)")
            else:
                for row in shared:
                    print(f"  {row['qtd_sindicatos']:>3} sindicato(s) → '{row['pnome']}'  (id={row['pid']})")

            # Parâmetros que NUNCA são referenciados (órfãos)
            cur.execute(
                """
                SELECT p.id, p.name
                  FROM cbr_parametros_boleto p
                 WHERE p.deleted = 0
                   AND NOT EXISTS (
                       SELECT 1 FROM sindi_sindicatos_cstm sc
                        WHERE sc.cbr_parametros_boleto_id_c = p.id
                   )
                 LIMIT 10
                """
            )
            orfaos = list(cur.fetchall())
            print(f"\n=== PARÂMETROS ÓRFÃOS (sem sindicato) ===")
            print(f"  amostra (até 10): {len(orfaos)}")
            for row in orfaos:
                print(f"    {row['name']}  (id={row['id']})")


if __name__ == "__main__":
    main()
