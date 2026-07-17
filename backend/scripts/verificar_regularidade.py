"""
Testa as fórmulas de REGULARIDADE contra a resposta do legado.

Uso (do diretório backend/):
    venv/bin/python -m scripts.verificar_regularidade

POR QUE ISTO EXISTE
-------------------
A BSS definiu (17/07/2026):

    "A empresa está regular quando gerou BOLETO todos os meses, sem pular
     nenhum mês desde o início da geração dos boletos. Se gerou em mar/2023,
     depois todos os meses, mas falhou em fev/2026, é irregular — mesmo tendo
     gerado de mar/26 a jun/26."

Mas a view `bss.empresa_meses_faltantes` calcula sobre `bss.lista_mensal`
(PLANILHA entregue), não sobre `bss.boleto`. E a `motivo_bloqueio_processo()`
usa essa view pra dizer "N mês(es) sem planilha submetida".

São medidas diferentes. O boleto nasce da planilha, mas nada garante 1:1.

NÃO ADIANTA ESCOLHER A MAIS BONITA. O legado já respondeu isso pra ~5.250
empresas: a coluna `bss.empresa.regularidade` é snapshot copiado de lá. Então
dá pra testar as duas fórmulas contra a resposta conhecida e ver qual acerta.

É a lição do protocolo aplicada antes do estrago: naquele caso uma fórmula
plausível foi validada em 2 casos, e teria sobrescrito 19 mil protocolos
históricos. Aqui a validação é contra a base inteira, antes de escrever
qualquer coisa.

Este script NÃO grava nada.
"""

from app.database import get_pg_connection


# Meses faltantes por empresa, calculado sobre BOLETO (definição da BSS).
# Mesma estrutura da empresa_meses_faltantes, trocando a fonte.
SQL_POR_BOLETO = """
WITH primeiro AS (
    SELECT id_empresa, MIN(mes_referencia) AS desde
      FROM bss.boleto
     WHERE mes_referencia IS NOT NULL
       {filtro_status}
     GROUP BY id_empresa
),
esperados AS (
    SELECT p.id_empresa, gs::DATE AS mes
      FROM primeiro p
      CROSS JOIN LATERAL generate_series(
          p.desde,
          -- Até o mês ANTERIOR ao atual: o mês corrente ainda está em curso e
          -- não deveria contar como falha.
          (DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month')::DATE,
          INTERVAL '1 month'
      ) AS gs
),
gerados AS (
    SELECT DISTINCT id_empresa, mes_referencia
      FROM bss.boleto
     WHERE mes_referencia IS NOT NULL
       {filtro_status}
)
SELECT e.mes AS mes_faltante, e.id_empresa
  FROM esperados e
  LEFT JOIN gerados g
         ON g.id_empresa = e.id_empresa
        AND g.mes_referencia = e.mes
 WHERE g.mes_referencia IS NULL
"""


def _matriz(cur, sql_faltantes: str, rotulo: str) -> None:
    """Compara uma fórmula contra bss.empresa.regularidade (a do legado)."""
    cur.execute(
        f"""
        WITH faltantes AS ({sql_faltantes}),
        por_empresa AS (
            SELECT id_empresa, COUNT(*) AS qtd FROM faltantes GROUP BY id_empresa
        )
        SELECT
            e.regularidade                                   AS legado,
            CASE WHEN COALESCE(pe.qtd, 0) > 0
                 THEN 'irregular' ELSE 'regular' END         AS formula,
            COUNT(*)                                         AS qtd
          FROM bss.empresa e
          LEFT JOIN por_empresa pe ON pe.id_empresa = e.id
         WHERE e.regularidade IS NOT NULL
         GROUP BY 1, 2
         ORDER BY 1, 2
        """
    )
    linhas = cur.fetchall()
    total = sum(r["qtd"] for r in linhas)
    acertos = sum(r["qtd"] for r in linhas if r["legado"] == r["formula"])

    print(f"\n=== FÓRMULA: {rotulo} ".ljust(70, "="))
    print(f"{'legado':>12} × {'fórmula':<12} {'empresas':>10}")
    for r in linhas:
        bate = "✓" if r["legado"] == r["formula"] else "✗"
        print(f"{r['legado']:>12} × {r['formula']:<12} {r['qtd']:>10}  {bate}")
    if total:
        print(f"\n  Concordância: {acertos}/{total} = {100.0 * acertos / total:.1f}%")


def main() -> None:
    with get_pg_connection() as conn, conn.cursor() as cur:

        print("Comparando cada fórmula com bss.empresa.regularidade (valor do legado).")
        print("100% = a fórmula reproduz o legado. Menos que isso = ela inventa.")

        # (1) O que a view faz hoje: PLANILHA
        _matriz(
            cur,
            """
            SELECT id_empresa, mes_faltante FROM bss.empresa_meses_faltantes
            """,
            "planilha (bss.empresa_meses_faltantes — como está hoje)",
        )

        # (2) A definição da BSS: BOLETO, contando qualquer boleto
        _matriz(
            cur,
            SQL_POR_BOLETO.format(filtro_status=""),
            "boleto — todos, inclusive cancelados",
        )

        # (3) BOLETO ignorando cancelado. ❓ Boleto cancelado conta como "mês
        #     gerado"? A BSS não disse. Se (2) e (3) derem números diferentes,
        #     a pergunta importa e precisa de resposta.
        _matriz(
            cur,
            SQL_POR_BOLETO.format(filtro_status="AND status <> 'cancelado'"),
            "boleto — desconsiderando cancelados",
        )

        # Sanidade: as duas fontes cobrem as mesmas empresas?
        cur.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE tem_lista AND NOT tem_boleto) AS so_planilha,
                COUNT(*) FILTER (WHERE tem_boleto AND NOT tem_lista) AS so_boleto,
                COUNT(*) FILTER (WHERE tem_boleto AND tem_lista)     AS ambos,
                COUNT(*) FILTER (WHERE NOT tem_boleto AND NOT tem_lista) AS nenhum
              FROM (
                SELECT e.id,
                       EXISTS (SELECT 1 FROM bss.lista_mensal l WHERE l.id_empresa = e.id) AS tem_lista,
                       EXISTS (SELECT 1 FROM bss.boleto b WHERE b.id_empresa = e.id)       AS tem_boleto
                  FROM bss.empresa e
              ) x
            """
        )
        r = cur.fetchone()
        print("\n=== COBERTURA DAS FONTES ".ljust(70, "="))
        print(f"  só planilha, sem boleto : {r['so_planilha']}")
        print(f"  só boleto, sem planilha : {r['so_boleto']}")
        print(f"  ambos                   : {r['ambos']}")
        print(f"  nenhum dos dois         : {r['nenhum']}")
        print("\n  Se 'só planilha' ou 'só boleto' forem grandes, as duas fórmulas")
        print("  divergem por construção — e a escolha da fonte muda o resultado.")

    print()


if __name__ == "__main__":
    main()
