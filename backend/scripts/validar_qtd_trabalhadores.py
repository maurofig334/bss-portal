"""
Compara o cache bss.sindicato.qtd_trabalhadores_*  com a contagem real
em bss.trabalhador (filtrando por situação).

Uso (do diretório backend/, com venv ativa):
    python -m scripts.validar_qtd_trabalhadores

Saída:
  - Resumo geral: cache vs real (ativos e inativos)
  - Top 20 sindicatos com maior divergência absoluta em ATIVOS
  - Top 20 sindicatos com maior divergência absoluta em INATIVOS
  - Quantidade de sindicatos com divergência

NÃO altera nada no banco — só consulta.
"""

from __future__ import annotations

from app.database import get_pg_connection


SQL_GERAL = """
    SELECT
        SUM(s.qtd_trabalhadores_ativos)   AS cache_ativos,
        SUM(s.qtd_trabalhadores_inativos) AS cache_inativos,
        (SELECT COUNT(*) FROM bss.trabalhador
          WHERE situacao = 'ativo' AND id_sindicato_atual IS NOT NULL) AS real_ativos,
        (SELECT COUNT(*) FROM bss.trabalhador
          WHERE situacao IN ('inativo','desligado','demitido')
            AND id_sindicato_atual IS NOT NULL) AS real_inativos,
        (SELECT COUNT(*) FROM bss.trabalhador
          WHERE id_sindicato_atual IS NOT NULL) AS real_total
      FROM bss.sindicato s
     WHERE s.ativo = TRUE
"""

SQL_POR_SINDICATO = """
    WITH cont AS (
        SELECT id_sindicato_atual AS id_sindicato,
               COUNT(*) FILTER (WHERE situacao = 'ativo')                                   AS real_ativos,
               COUNT(*) FILTER (WHERE situacao IN ('inativo','desligado','demitido'))       AS real_inativos
          FROM bss.trabalhador
         WHERE id_sindicato_atual IS NOT NULL
         GROUP BY id_sindicato_atual
    )
    SELECT
        s.id, s.razao_social, s.uf_abrangencia,
        s.qtd_trabalhadores_ativos    AS cache_ativos,
        COALESCE(c.real_ativos, 0)    AS real_ativos,
        s.qtd_trabalhadores_inativos  AS cache_inativos,
        COALESCE(c.real_inativos, 0)  AS real_inativos,
        s.qtd_trabalhadores_ativos    - COALESCE(c.real_ativos, 0)   AS dif_ativos,
        s.qtd_trabalhadores_inativos  - COALESCE(c.real_inativos, 0) AS dif_inativos
      FROM bss.sindicato s
      LEFT JOIN cont c ON c.id_sindicato = s.id
     WHERE s.ativo = TRUE
"""


def main() -> None:
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_GERAL)
            g = cur.fetchone()
            print("=== RESUMO GERAL ===")
            print(f"  ATIVOS    cache: {g['cache_ativos']:>10,}   real: {g['real_ativos']:>10,}   "
                  f"diff: {g['cache_ativos'] - g['real_ativos']:>+10,}")
            print(f"  INATIVOS  cache: {g['cache_inativos']:>10,}   real: {g['real_inativos']:>10,}   "
                  f"diff: {g['cache_inativos'] - g['real_inativos']:>+10,}")
            print(f"  Total trabalhadores com sindicato preenchido: {g['real_total']:,}")

            cur.execute(SQL_POR_SINDICATO)
            rows = list(cur.fetchall())

            divergentes_at = sum(1 for r in rows if r['dif_ativos'] != 0)
            divergentes_in = sum(1 for r in rows if r['dif_inativos'] != 0)
            print(f"\n=== POR SINDICATO ===")
            print(f"  total sindicatos analisados : {len(rows)}")
            print(f"  com diff em ATIVOS          : {divergentes_at}")
            print(f"  com diff em INATIVOS        : {divergentes_in}")

            print("\n--- TOP 20 maior |dif_ativos| ---")
            top_at = sorted(rows, key=lambda r: abs(r['dif_ativos']), reverse=True)[:20]
            for r in top_at:
                print(f"  {r['dif_ativos']:>+8,}  | cache={r['cache_ativos']:>7,}  real={r['real_ativos']:>7,}  "
                      f"| {r['uf_abrangencia'] or '--':2}  {(r['razao_social'] or '')[:60]}")

            print("\n--- TOP 20 maior |dif_inativos| ---")
            top_in = sorted(rows, key=lambda r: abs(r['dif_inativos']), reverse=True)[:20]
            for r in top_in:
                print(f"  {r['dif_inativos']:>+8,}  | cache={r['cache_inativos']:>7,}  real={r['real_inativos']:>7,}  "
                      f"| {r['uf_abrangencia'] or '--':2}  {(r['razao_social'] or '')[:60]}")


if __name__ == "__main__":
    main()
