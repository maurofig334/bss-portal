"""
Marca boletos abertos como vencidos quando passou da data_vencimento + 2 dias.

Regra confirmada com cliente em 2026-05-09:
  - status 'gerado' (UI: "Aberto") com data_vencimento + 2 dias <= HOJE → 'vencido'
  - 'pendente' (legado de 2 anos) também transita pra 'vencido' nas mesmas
    condições (já estão vencidos, só não rodaram esse fluxo).
  - Status 'pago' e 'cancelado' são finais — não muda.

Idempotente: rodar várias vezes não faz nada além da primeira passada do dia.

Uso manual:
    cd backend && source venv/bin/activate
    python -m scripts.marcar_boletos_vencidos

Uso automático (cron na OCI, todo dia 04:00 UTC):
    0 4 * * * cd /home/opc/bss-portal/backend && \
        ./venv/bin/python -m scripts.marcar_boletos_vencidos \
        >> /home/opc/bss-portal/logs/cron-vencidos.log 2>&1
"""

from datetime import date

from app.database import get_pg_connection


# Regra: D+2 (= 2 dias de tolerância depois do vencimento antes de marcar vencido).
# Se quiser mais agressivo (D+1), trocar pra 1.
DIAS_TOLERANCIA = 2


def main() -> None:
    hoje = date.today()
    print(f"[{hoje.isoformat()}] Marcando boletos vencidos (tolerância D+{DIAS_TOLERANCIA})…")

    sql = """
        UPDATE bss.boleto
           SET status        = 'vencido',
               atualizado_em = NOW()
         WHERE status IN ('gerado', 'pendente')
           AND data_vencimento IS NOT NULL
           AND data_vencimento + INTERVAL '%s days' <= CURRENT_DATE
        RETURNING id
    """ % DIAS_TOLERANCIA   # interval com %s direto não dá em psycopg, então hard-code

    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
        conn.commit()

    print(f"  {len(rows):,} boleto(s) marcado(s) como vencidos.")

    # Stats finais:
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT status, COUNT(*) AS qtd
                  FROM bss.boleto
                 GROUP BY status
                 ORDER BY qtd DESC
            """)
            for r in cur.fetchall():
                print(f"  {r['status']:12s} {r['qtd']:>10,}")


if __name__ == "__main__":
    main()
