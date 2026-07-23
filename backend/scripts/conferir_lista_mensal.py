"""
Fotografa os números de um mês de lista_mensal — pra comparar ANTES/DEPOIS de
reimportar a mesma planilha e provar que a importação em lote dá o mesmo
resultado da versão antiga (linha-a-linha).

Uso (na OCI):
    venv/bin/python -m scripts.conferir_lista_mensal 2026-07-01
    venv/bin/python -m scripts.conferir_lista_mensal 2026-07-01 --cnpj 20707884000126

Rodar ANTES de reimportar, anotar; reimportar pela tela; rodar DEPOIS e comparar.
Como a importação é idempotente (ON CONFLICT DO UPDATE), os números devem BATER
— não duplicar. Se baterem, a lógica em lote está correta.

SOMENTE LEITURA.
"""

import sys

from app.database import get_pg_connection


def main() -> None:
    if len(sys.argv) < 2:
        print("uso: python -m scripts.conferir_lista_mensal AAAA-MM-01 [--cnpj DIGITOS]")
        return
    mes = sys.argv[1]
    cnpj = None
    if "--cnpj" in sys.argv:
        cnpj = "".join(c for c in sys.argv[sys.argv.index("--cnpj") + 1] if c.isdigit())

    filtro_emp = ""
    params = [mes]
    if cnpj:
        filtro_emp = " AND e.cnpj = %s"
        params.append(cnpj)

    with get_pg_connection() as conn, conn.cursor() as cur:
        print(f"\n=== lista_mensal_item — mês {mes}"
              + (f" · CNPJ {cnpj}" if cnpj else " · todos") + " ===")
        cur.execute(
            f"""
            SELECT
                COUNT(*)                                                    AS itens,
                COUNT(*) FILTER (WHERE lmi.situacao_no_upload = 'ativo')    AS ativos,
                COUNT(*) FILTER (WHERE lmi.situacao_no_upload = 'inativo')  AS inativos,
                COUNT(DISTINCT lmi.id_trabalhador)                          AS trabalhadores,
                COUNT(DISTINCT lmi.id_empresa)                             AS empresas
              FROM bss.lista_mensal_item lmi
              JOIN bss.empresa e ON e.id = lmi.id_empresa
             WHERE lmi.mes_referencia = %s {filtro_emp}
            """,
            params,
        )
        for k, v in cur.fetchone().items():
            print(f"  {k:<16} {v:,}")

        # Sanidade: nenhum trabalhador deve ter 2 itens ATIVOS na MESMA empresa
        # no mesmo mês (o UNIQUE + dedup garante). Se aparecer > 0, tem bug.
        cur.execute(
            f"""
            SELECT COUNT(*) AS duplicados FROM (
                SELECT lmi.id_trabalhador, lmi.id_empresa
                  FROM bss.lista_mensal_item lmi
                  JOIN bss.empresa e ON e.id = lmi.id_empresa
                 WHERE lmi.mes_referencia = %s {filtro_emp}
                   AND lmi.situacao_no_upload = 'ativo'
                 GROUP BY lmi.id_trabalhador, lmi.id_empresa
                HAVING COUNT(*) > 1
            ) x
            """,
            params,
        )
        dup = cur.fetchone()["duplicados"]
        print(f"\n  duplicados (trab+empresa com 2 itens ativos): {dup}"
              + ("  ⚠ BUG" if dup else "  ✓"))

        # Quantas listas_mensal existem pra esse mês/cnpj (reimportar cria nova
        # lista, mas os itens são upsertados na mesma chave — normal ter várias
        # listas apontando; o que não pode é item duplicado, checado acima).
        cur.execute(
            f"""
            SELECT COUNT(*) AS listas
              FROM bss.lista_mensal lm
              JOIN bss.empresa e ON e.id = lm.id_empresa
             WHERE lm.mes_referencia = %s {filtro_emp}
            """,
            params,
        )
        print(f"  listas_mensal no mês: {cur.fetchone()['listas']:,}")

    print()


if __name__ == "__main__":
    main()
