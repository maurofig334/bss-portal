"""
Sincroniza itens de boleto: bolet_boletos_traba_trabalhadores_1_c → bss.boleto_item

Volume: 4.882.174 linhas (a "killer table" do legado).
Tempo esperado: 4-10 min.

Pré-requisito: bss.boleto E bss.trabalhador JÁ sincronizadas.

Cada linha da N-N do legado vira 1 linha em bss.boleto_item, resolvendo:
  uuid_boleto      → id_boleto      (lookup em memória)
  uuid_trabalhador → id_trabalhador (lookup em memória)
  + id_sindicato (do trabalhador)
  + mes_referencia (do boleto)
  + eh_dependente (titularidade do trabalhador)

Após este sync, rodar UPDATE pós-processamento que preenche
bss.boleto.id_sindicato a partir do primeiro item de cada boleto.
"""

from __future__ import annotations

from ..database import get_mysql_connection, get_pg_connection
from ._base import Progresso, mysql_iter, pg_executemany


SQL_LEGADO = """
    SELECT
        bbn.bolet_boletos_traba_trabalhadores_1bolet_boletos_ida AS uuid_boleto,
        bbn.bolet_boletos_traba_trabalhadores_1traba_trabalhadores_idb AS uuid_trabalhador
    FROM bolet_boletos_traba_trabalhadores_1_c bbn
    WHERE bbn.deleted = 0
"""


# UPSERT idempotente. UNIQUE (id_boleto, id_trabalhador) adicionado em 09_boleto_item_dedup.sql.
# Permite rodar o sync diário sem duplicar — descoberto em 2026-05-11
# que a versão antiga (INSERT puro) triplicava as 4.9M linhas a cada execução.
SQL_INSERT = """
    INSERT INTO bss.boleto_item (
        id_boleto, id_trabalhador, id_sindicato, mes_referencia,
        taxa_aplicada, eh_dependente
    )
    VALUES (%s, %s, %s, %s, %s, %s)
    ON CONFLICT (id_boleto, id_trabalhador) DO NOTHING
"""


def _carregar_boleto_map(pg_conn) -> dict[str, tuple]:
    """uuid → (id, mes_referencia)."""
    m: dict[str, tuple] = {}
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT id, id_legado_uuid, mes_referencia "
            "FROM bss.boleto WHERE id_legado_uuid IS NOT NULL"
        )
        for row in cur:
            m[row["id_legado_uuid"]] = (row["id"], row["mes_referencia"])
    return m


def _carregar_trabalhador_map(pg_conn) -> dict[str, tuple]:
    """uuid → (id, id_sindicato_atual, eh_dependente)."""
    m: dict[str, tuple] = {}
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT id, id_legado_uuid, id_sindicato_atual, titularidade "
            "FROM bss.trabalhador WHERE id_legado_uuid IS NOT NULL"
        )
        for row in cur:
            m[row["id_legado_uuid"]] = (
                row["id"],
                row["id_sindicato_atual"],
                row["titularidade"] == "dependente",
            )
    return m


def sync(dry_run: bool = False, limite: int | None = None) -> int:
    print(f"\n=== Sync BOLETO_ITEM ({'dry-run' if dry_run else 'gravação'}) ===")

    print("  carregando mapeamentos UUID→ID...")
    with get_pg_connection() as pg_conn:
        boleto_map = _carregar_boleto_map(pg_conn)
        trab_map = _carregar_trabalhador_map(pg_conn)
    print(f"  ✓ {len(boleto_map)} boletos, {len(trab_map)} trabalhadores em memória")

    sql = SQL_LEGADO + (f" LIMIT {int(limite)}" if limite else "")
    prog = Progresso(total=None, nome="boleto_item")
    pulados_boleto = 0
    pulados_trab = 0

    with get_mysql_connection() as mysql_conn:
        def converter_iter():
            nonlocal pulados_boleto, pulados_trab
            for linha in mysql_iter(mysql_conn, sql, batch_size=5000):
                if dry_run and prog.contador < 3:
                    print(f"  amostra: {linha}")

                bol = boleto_map.get(linha["uuid_boleto"])
                if not bol:
                    pulados_boleto += 1
                    prog.tick()
                    continue
                trab = trab_map.get(linha["uuid_trabalhador"])
                if not trab:
                    pulados_trab += 1
                    prog.tick()
                    continue

                boleto_id, mes_ref = bol
                trab_id, trab_sind, eh_dep = trab

                prog.tick()
                yield (
                    boleto_id,
                    trab_id,
                    trab_sind,    # pode ser NULL — fica NULL no item
                    mes_ref,
                    0,            # taxa_aplicada (default no schema também)
                    eh_dep,
                )

        if dry_run:
            for _ in converter_iter():
                pass
        else:
            with get_pg_connection() as pg_conn:
                pg_executemany(pg_conn, SQL_INSERT, converter_iter(), batch_size=2000)

    prog.fim()
    if pulados_boleto:
        print(f"  ⚠ {pulados_boleto} item(ns) sem boleto correspondente em bss.boleto")
    if pulados_trab:
        print(f"  ⚠ {pulados_trab} item(ns) sem trabalhador correspondente em bss.trabalhador")
    return prog.contador
