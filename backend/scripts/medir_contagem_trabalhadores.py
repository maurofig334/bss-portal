"""
Mede se dá pra CONTAR trabalhadores ativos na hora, em vez de guardar cache.

Uso (do diretório backend/):
    venv/bin/python -m scripts.medir_contagem_trabalhadores

POR QUE
-------
`bss.empresa.qtd_trabalhadores_ativos` é campo derivado, gravado, "atualizado
por job" (comentário do schema). Campo derivado gravado descola da fonte — foi
o que aconteceu no legado, onde o portal mostra 22 trabalhadores pra uma
empresa que tem 0 no SuiteCRM. Nossa sync copiou o número errado; depois algum
job recalculou por cima, e agora bate. Ninguém sabe qual job, nem quando roda.

A alternativa é a v_empresa contar na hora. O índice pra isso já existe:

    CREATE INDEX idx_trab_emp_sind ON bss.trabalhador (id_empresa_atual, ...)
      WHERE situacao = 'ativo';

Índice parcial, feito exatamente pra esta pergunta.

MAS: o cache existe por algum motivo, e "deve ser rápido" não é medição. Este
script cronometra a listagem de Empresas (50 por página, que é o uso real) das
duas formas. Se a diferença for irrelevante, o cache não se justifica — e um
número sempre verdadeiro vale mais que milissegundos.

NÃO GRAVA NADA.
"""

import time

from app.database import get_pg_connection


# Como é hoje: lê o campo gravado.
SQL_CACHE = """
SELECT e.id, e.razao_social, e.qtd_trabalhadores_ativos AS ativos
  FROM bss.empresa e
 ORDER BY e.razao_social
 LIMIT 50 OFFSET %(off)s
"""

# Proposta: conta na hora, usando o índice parcial.
SQL_CONTADO = """
SELECT e.id, e.razao_social,
       (SELECT count(*) FROM bss.trabalhador t
         WHERE t.id_empresa_atual = e.id AND t.situacao = 'ativo') AS ativos
  FROM bss.empresa e
 ORDER BY e.razao_social
 LIMIT 50 OFFSET %(off)s
"""


def _cronometrar(cur, sql: str, rodadas: int = 5) -> float:
    """Mediana de N execuções, variando a página (evita cache de plano/página)."""
    tempos = []
    for i in range(rodadas):
        off = i * 50
        t0 = time.perf_counter()
        cur.execute(sql, {"off": off})
        cur.fetchall()
        tempos.append((time.perf_counter() - t0) * 1000)
    tempos.sort()
    return tempos[len(tempos) // 2]


def main() -> None:
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM bss.empresa")
        n_emp = cur.fetchone()["n"]
        cur.execute("SELECT count(*) AS n FROM bss.trabalhador")
        n_trab = cur.fetchone()["n"]
        print(f"\nBase: {n_emp:,} empresas · {n_trab:,} trabalhadores")

        # Aquecimento: a primeira execução paga o custo de plano e de I/O frio,
        # e compararia maçã com laranja.
        _cronometrar(cur, SQL_CACHE, 2)
        _cronometrar(cur, SQL_CONTADO, 2)

        t_cache = _cronometrar(cur, SQL_CACHE)
        t_contado = _cronometrar(cur, SQL_CONTADO)

        print("\n=== Listagem de Empresas (50 por página) ".ljust(60, "="))
        print(f"  lendo o cache gravado ... {t_cache:7.1f} ms")
        print(f"  contando na hora ........ {t_contado:7.1f} ms")
        delta = t_contado - t_cache
        print(f"  diferença ............... {delta:+7.1f} ms")

        if t_contado < 100:
            print("\n  ✓ Contar na hora custa menos de 100ms numa página.")
            print("    O cache não se justifica: um número sempre verdadeiro vale")
            print("    mais do que essa diferença.")
        else:
            print("\n  ⚠ Contar na hora passou de 100ms. Aí o cache tem razão de")
            print("    existir — mas precisa de um job confiável, não de um que")
            print("    ninguém sabe qual é.")

        print("\n=== Plano da contagem ".ljust(60, "="))
        cur.execute("EXPLAIN (ANALYZE, BUFFERS) " + SQL_CONTADO, {"off": 0})
        for r in cur.fetchall():
            linha = list(r.values())[0]
            print("  " + linha)
        print("\n  Procure por 'idx_trab_emp_sind' — se ele aparecer, o índice")
        print("  parcial está sendo usado e a contagem é barata. Se aparecer")
        print("  'Seq Scan on trabalhador', o índice NÃO serve e o cache fica.")

    print()


if __name__ == "__main__":
    main()
