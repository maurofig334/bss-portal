"""
Sincroniza mensagens de processo: aop_case_updates → bss.processo_mensagem

Volume: 33.213 linhas. Tempo esperado: <10s.

Cada update do legado vira 1 mensagem no processo. O conteúdo pode ter HTML
(o legado armazena com tags); preservamos como veio — frontend renderiza ou
limpa conforme contexto.

Usuário (created_by): UUID legado de 'users'. Como ainda não migramos a tabela
de usuários do BSS (vamos criar do zero, conforme decisão), aqui id_usuario
fica NULL — pode ser preenchido depois quando criarmos um mapping users→bss_users.
"""

from __future__ import annotations

from ..database import get_mysql_connection, get_pg_connection
from ._base import Progresso, mysql_iter, pg_executemany, trim_or_none


SQL_LEGADO = """
    SELECT
        u.id            AS uuid,
        u.case_id       AS uuid_processo,
        u.name          AS titulo,
        u.description   AS corpo,
        u.internal      AS interno,
        u.created_by    AS uuid_user_legado,
        u.date_entered  AS criado_em
    FROM aop_case_updates u
    WHERE u.deleted = 0
"""


SQL_UPSERT = """
    INSERT INTO bss.processo_mensagem (
        id_legado_uuid, id_processo, id_usuario,
        titulo, corpo, interno, criado_em, atualizado_em
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (id_legado_uuid) DO UPDATE
        SET id_processo = EXCLUDED.id_processo,
            titulo      = EXCLUDED.titulo,
            corpo       = EXCLUDED.corpo,
            interno     = EXCLUDED.interno,
            atualizado_em = NOW()
"""


def _carregar_processo_map(pg_conn) -> dict[str, int]:
    """uuid case → id processo no BSS."""
    m: dict[str, int] = {}
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT id, id_legado_uuid FROM bss.processo_beneficio "
            "WHERE id_legado_uuid IS NOT NULL"
        )
        for r in cur:
            m[r["id_legado_uuid"]] = r["id"]
    return m


def _converter(linha: dict, proc_map: dict) -> tuple | None:
    id_processo = proc_map.get(linha.get("uuid_processo"))
    if not id_processo:
        return None  # processo não existe no BSS → pula
    corpo = linha.get("corpo") or linha.get("titulo") or ""
    if not corpo.strip():
        return None  # mensagem vazia → pula
    return (
        linha["uuid"],
        id_processo,
        None,  # id_usuario: BSS users serão criados do zero, sem mapping com legado
        trim_or_none(linha.get("titulo"), 255),
        corpo,
        bool(linha.get("interno")),
        linha.get("criado_em"),
        linha.get("criado_em"),  # atualizado_em = criado_em na migração
    )


def sync(dry_run: bool = False, limite: int | None = None) -> int:
    print(f"\n=== Sync PROCESSO_MENSAGEM ({'dry-run' if dry_run else 'gravação'}) ===")

    print("  carregando mapeamento de processo (uuid → id BSS)...")
    with get_pg_connection() as pg_conn:
        proc_map = _carregar_processo_map(pg_conn)
    print(f"  ✓ {len(proc_map)} processos em memória")

    sql = SQL_LEGADO + (f" LIMIT {int(limite)}" if limite else "")
    prog = Progresso(total=None, nome="processo_mensagem")
    pulados_proc = 0
    pulados_vazia = 0

    with get_mysql_connection() as mysql_conn:
        def converter_iter():
            nonlocal pulados_proc, pulados_vazia
            for linha in mysql_iter(mysql_conn, sql, batch_size=2000):
                if dry_run and prog.contador < 3:
                    print(f"  amostra: {linha}")
                tup = _converter(linha, proc_map)
                prog.tick()
                if tup is None:
                    if not proc_map.get(linha.get("uuid_processo")):
                        pulados_proc += 1
                    else:
                        pulados_vazia += 1
                    continue
                yield tup

        if dry_run:
            for _ in converter_iter():
                pass
        else:
            with get_pg_connection() as pg_conn:
                pg_executemany(pg_conn, SQL_UPSERT, converter_iter(), batch_size=1000)

    prog.fim()
    if pulados_proc:
        print(f"  ⚠ {pulados_proc} mensagem(ns) sem processo correspondente em bss")
    if pulados_vazia:
        print(f"  ⚠ {pulados_vazia} mensagem(ns) com corpo vazio (puladas)")
    return prog.contador
