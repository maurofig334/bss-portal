"""
Audita o cache `empresa.qtd_trabalhadores_ativos` contra a contagem real.

Uso (do diretório backend/):
    venv/bin/python -m scripts.auditar_cache_trabalhadores

O QUE ESTÁ EM JOGO
------------------
Descoberta de 17/07/2026, verificada por Mauro direto no SuiteCRM:

    RCOND GESTAO E TECNOLOGIA LTDA
      portal legado ............ 22 trabalhadores ativos
      SuiteCRM (a verdade) ..... 0
      BSS, contando de verdade . 0

Ou seja: **o campo de cache do legado está errado**, e o portal legado o exibe.
Nossa sync copiou o campo fielmente — então o BSS herdou o número errado na
coluna de cache, ao mesmo tempo em que conta certo quando conta.

Consequência prática: a tela de Empresas do BSS mostra `qtd_trabalhadores_ativos`
(o cache herdado), enquanto a tela de Trabalhadores filtra por `id_empresa_atual`
(a realidade). Os dois números vêm de fontes diferentes e discordam.

Este script mede o tamanho do problema em TODA a base, não em um exemplo.
Anedota não é diagnóstico — foi assim que eu estimei "~636 processos sem
vínculo" quando a realidade era 59.

NÃO GRAVA NADA. Só mede.
"""

from app.database import get_pg_connection


def main() -> None:
    with get_pg_connection() as conn, conn.cursor() as cur:

        cur.execute(
            """
            WITH real AS (
                SELECT e.id,
                       e.razao_social,
                       e.qtd_trabalhadores_ativos AS cache,
                       (SELECT count(*) FROM bss.trabalhador t
                         WHERE t.id_empresa_atual = e.id
                           AND t.situacao = 'ativo')  AS contado
                  FROM bss.empresa e
            )
            SELECT
                count(*)                                          AS empresas,
                count(*) FILTER (WHERE cache = contado)           AS batem,
                count(*) FILTER (WHERE cache > contado)           AS cache_maior,
                count(*) FILTER (WHERE cache < contado)           AS cache_menor,
                count(*) FILTER (WHERE cache > 0 AND contado = 0) AS fantasma,
                COALESCE(sum(cache), 0)                           AS soma_cache,
                COALESCE(sum(contado), 0)                         AS soma_real
              FROM real
            """
        )
        r = cur.fetchone()

        print("\n=== CACHE vs REALIDADE — base inteira ".ljust(66, "="))
        print(f"  empresas ................................. {r['empresas']:>8}")
        print(f"  cache == contagem real ................... {r['batem']:>8}")
        print(f"  cache MAIOR que a realidade .............. {r['cache_maior']:>8}")
        print(f"  cache MENOR que a realidade .............. {r['cache_menor']:>8}")
        print(f"  cache > 0 mas ZERO trabalhadores de fato . {r['fantasma']:>8}  ← o caso RCOND")
        print()
        print(f"  soma do cache ............................ {r['soma_cache']:>8}")
        print(f"  soma da contagem real .................... {r['soma_real']:>8}")
        dif = r["soma_cache"] - r["soma_real"]
        print(f"  diferença ................................ {dif:>8}")

        if r["empresas"]:
            pct = 100.0 * r["batem"] / r["empresas"]
            print(f"\n  Concordância: {pct:.1f}%")
            if pct < 90:
                print("  ⚠ O cache NÃO é confiável. A tela de Empresas está exibindo")
                print("    números que o resto do sistema não enxerga.")

        # Os piores casos: onde o cache mais mente.
        cur.execute(
            """
            SELECT e.id, e.razao_social, e.status,
                   e.qtd_trabalhadores_ativos AS cache,
                   (SELECT count(*) FROM bss.trabalhador t
                     WHERE t.id_empresa_atual = e.id
                       AND t.situacao = 'ativo') AS contado,
                   (SELECT count(*) FROM bss.trabalhador t
                     WHERE t.id_empresa_atual = e.id) AS trab_qualquer
              FROM bss.empresa e
             WHERE e.qtd_trabalhadores_ativos > 0
             ORDER BY (e.qtd_trabalhadores_ativos -
                       (SELECT count(*) FROM bss.trabalhador t
                         WHERE t.id_empresa_atual = e.id
                           AND t.situacao = 'ativo')) DESC
             LIMIT 15
            """
        )
        print("\n=== 15 MAIORES DIVERGÊNCIAS ".ljust(66, "="))
        print(f"{'id':>6} {'cache':>7} {'real':>6} {'qualquer':>9}  razão social")
        for x in cur.fetchall():
            print(f"{x['id']:>6} {x['cache']:>7} {x['contado']:>6} "
                  f"{x['trab_qualquer']:>9}  {x['razao_social'][:38]}")
        print("\n  'qualquer' = trabalhadores vinculados à empresa em qualquer situação.")
        print("  Se 'qualquer' também for 0, os trabalhadores NÃO existem ou não")
        print("  estão ligados a esta empresa. Se for alto e 'real' for 0, eles")
        print("  existem mas nenhum está com situacao='ativo'.")

        # Distinguir as duas causas possíveis da divergência.
        cur.execute(
            """
            SELECT
                count(*) FILTER (WHERE id_empresa_atual IS NULL)  AS sem_empresa,
                count(*)                                          AS total,
                count(*) FILTER (WHERE situacao = 'ativo')        AS ativos,
                count(*) FILTER (WHERE situacao <> 'ativo')       AS nao_ativos
              FROM bss.trabalhador
            """
        )
        t = cur.fetchone()
        print("\n=== bss.trabalhador — panorama ".ljust(66, "="))
        print(f"  total ........................ {t['total']:>8}")
        print(f"  ativos ....................... {t['ativos']:>8}")
        print(f"  não-ativos ................... {t['nao_ativos']:>8}")
        print(f"  SEM empresa (id_empresa_atual NULL) {t['sem_empresa']:>8}")
        print("\n  'sem empresa' alto explicaria cache>0 com contagem 0: os")
        print("  trabalhadores existiriam, mas soltos. Isso seria bug NOSSO.")
        print("  'sem empresa' baixo aponta pro cache do legado como culpado.")

    print()


if __name__ == "__main__":
    main()
