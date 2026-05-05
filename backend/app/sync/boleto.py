"""
Sincroniza boletos: bolet_boletos + bolet_boletos_cstm → bss.boleto

Volume estimado: ~170k linhas. Tempo esperado: 30-60s.

Pré-requisito: bss.empresa JÁ sincronizada.

Mapping:
  cstm.id_boleto_c       → numero_boleto (sequencial)
  cstm.parent_id (UUID)  → id_empresa (resolvido em memória se parent_type='Accounts')
  cstm.ano_c + cstm.mes_c → mes_referencia (DATE dia 1)
  cstm.valor_c           → valor_total
  cstm.vencimento_c      → data_vencimento
  cstm.emissao_c         → data_emissao
  cstm.data_pagamento_c  → data_pagamento
  cstm.status_c          → status
  cstm.tipo_c            → tipo
  cstm.banco_c           → banco
  cstm.num_boleto_c      → nosso_numero (string)
  cstm.link_pdf_boleto_c → link_pdf

Observação:
  id_sindicato NÃO é preenchido aqui — fica NULL e é populado depois,
  via UPDATE pós-sync, a partir do boleto_item (que sabe via trabalhador).
"""

from __future__ import annotations

from datetime import date

from ..database import get_mysql_connection, get_pg_connection
from ._base import Progresso, mysql_iter, pg_executemany, trim_or_none


SQL_LEGADO = """
    SELECT
        b.id                              AS uuid,
        bc.id_boleto_c                    AS numero_boleto,
        bc.parent_type                    AS parent_type,
        bc.parent_id                      AS parent_id,
        bc.ano_c                          AS ano,
        bc.mes_c                          AS mes,
        bc.valor_c                        AS valor_total,
        bc.vencimento_c                   AS data_vencimento,
        bc.emissao_c                      AS data_emissao,
        bc.data_pagamento_c               AS data_pagamento,
        bc.num_boleto_c                   AS nosso_numero,
        bc.status_c                       AS status_legado,
        bc.tipo_c                         AS tipo,
        bc.banco_c                        AS banco,
        bc.link_pdf_boleto_c              AS link_pdf,
        bc.trabalhadores_ativos_c         AS qtd_trabalhadores
    FROM bolet_boletos b
    LEFT JOIN bolet_boletos_cstm bc ON bc.id_c = b.id
    WHERE b.deleted = 0
"""


SQL_UPSERT = """
    INSERT INTO bss.boleto (
        id_legado_uuid, numero_boleto, id_empresa, mes_referencia,
        qtd_trabalhadores, valor_total,
        banco, nosso_numero, link_pdf,
        status, tipo, data_emissao, data_vencimento, data_pagamento
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (id_legado_uuid) DO UPDATE
        SET numero_boleto    = EXCLUDED.numero_boleto,
            id_empresa       = EXCLUDED.id_empresa,
            mes_referencia   = EXCLUDED.mes_referencia,
            qtd_trabalhadores= EXCLUDED.qtd_trabalhadores,
            valor_total      = EXCLUDED.valor_total,
            banco            = EXCLUDED.banco,
            nosso_numero     = EXCLUDED.nosso_numero,
            link_pdf         = EXCLUDED.link_pdf,
            status           = EXCLUDED.status,
            tipo             = EXCLUDED.tipo,
            data_emissao     = EXCLUDED.data_emissao,
            data_vencimento  = EXCLUDED.data_vencimento,
            data_pagamento   = EXCLUDED.data_pagamento,
            atualizado_em    = NOW()
"""


def _normalizar_status(v) -> str:
    """status_c (varchar 100) → enum BSS."""
    if not v:
        return "gerado"
    s = str(v).strip().lower()
    if "pago" in s or "pagam" in s:
        return "pago"
    if "vencid" in s or "atras" in s:
        return "vencido"
    if "cancel" in s:
        return "cancelado"
    if "envia" in s:
        return "enviado"
    return "gerado"


def _carregar_empresa_map(pg_conn) -> dict[str, int]:
    """UUID legado → id BSS pra empresa."""
    m: dict[str, int] = {}
    with pg_conn.cursor() as cur:
        cur.execute("SELECT id, id_legado_uuid FROM bss.empresa WHERE id_legado_uuid IS NOT NULL")
        for row in cur:
            m[row["id_legado_uuid"]] = row["id"]
    return m


def _converter(linha: dict, emp_map: dict) -> tuple | None:
    """Converte 1 linha. Retorna None se boleto inválido (sem ano/mes)."""
    ano = linha.get("ano")
    mes = linha.get("mes")
    if not ano or not mes or int(mes) < 1 or int(mes) > 12:
        return None
    try:
        mes_ref = date(int(ano), int(mes), 1)
    except (ValueError, TypeError):
        return None

    # parent_id aponta pra empresa quando parent_type == 'Accounts'
    parent_type = (linha.get("parent_type") or "").strip()
    parent_id = linha.get("parent_id") if parent_type == "Accounts" else None
    id_empresa = emp_map.get(parent_id) if parent_id else None

    return (
        linha["uuid"],
        int(linha["numero_boleto"]) if linha.get("numero_boleto") is not None else None,
        id_empresa,
        mes_ref,
        int(linha.get("qtd_trabalhadores") or 0),
        float(linha.get("valor_total") or 0),
        trim_or_none(linha.get("banco"), 100),
        trim_or_none(linha.get("nosso_numero"), 50),
        trim_or_none(linha.get("link_pdf"), 500),
        _normalizar_status(linha.get("status_legado")),
        trim_or_none(linha.get("tipo"), 50),
        linha.get("data_emissao"),
        linha.get("data_vencimento"),
        linha.get("data_pagamento"),
    )


def sync(dry_run: bool = False, limite: int | None = None) -> int:
    print(f"\n=== Sync BOLETO ({'dry-run' if dry_run else 'gravação'}) ===")

    print("  carregando mapeamento UUID→ID de empresa...")
    with get_pg_connection() as pg_conn:
        emp_map = _carregar_empresa_map(pg_conn)
    print(f"  ✓ {len(emp_map)} empresas em memória")

    sql = SQL_LEGADO + (f" LIMIT {int(limite)}" if limite else "")
    prog = Progresso(total=None, nome="boleto")
    pulados = 0

    with get_mysql_connection() as mysql_conn:
        def converter_iter():
            nonlocal pulados
            for linha in mysql_iter(mysql_conn, sql, batch_size=1000):
                if dry_run and prog.contador < 3:
                    print(f"  amostra: {linha}")
                tup = _converter(linha, emp_map)
                prog.tick()
                if tup is None:
                    pulados += 1
                    continue
                yield tup

        if dry_run:
            for _ in converter_iter():
                pass
        else:
            with get_pg_connection() as pg_conn:
                pg_executemany(pg_conn, SQL_UPSERT, converter_iter(), batch_size=1000)

    prog.fim()
    if pulados:
        print(f"  ⚠ {pulados} boleto(s) pulado(s) (sem ano/mes válidos)")
    print("  ℹ id_sindicato será preenchido na pós-fase (depois de boleto_item)")
    return prog.contador
