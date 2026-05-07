"""
Sincroniza parâmetros de boleto + valores de benefício por sindicato.

Fontes (legado SuiteCRM):
    cbr_parametros_boleto + cbr_parametros_boleto_cstm
    sindi_sindicatos_cstm.cbr_parametros_boleto_id_c (FK sindicato → parâmetro)

Destinos (BSS):
    bss.parametros_boleto             — 1 linha por sindicato (chave: id_sindicato)
    bss.valor_beneficio_sindicato     — N linhas por sindicato (uma por slot ativo)

Modelagem (decisão de produto):
    No legado, 1 cbr_parametros_boleto pode ser apontado por N sindicatos
    (ex: FEMACO compartilha 1 parâmetro entre 25 sindicatos). No BSS optamos
    por **manter 1:1** — cada sindicato ganha sua própria linha de parâmetros,
    com cópia dos valores. Isso permite override por sindicato (banco
    diferente, tarifa especial) sem afetar os outros.

Slots de indenização:
    cbr_parametros_boleto_cstm tem 10 slots numerados (sem sufixo, _2_c..._10_c).
    A correspondência slot → tipo de benefício vem de bss.tipo_beneficio.slot_legado
    (popular pela migration 02).

    Slot 1  AC  acionamento_funeral
    Slot 2  AU  auxilio_creche
    Slot 3  NA  natalidade
    Slot 4  AD  acidente
    Slot 5  IN  incapacitacao
    Slot 6  FA  falecimento
    Slot 7  RE  reembolso_rescisao
    Slot 8  CM  consulta_medica
    Slot 9  EX  exame
    Slot 10 BS  brinde_sindicato

    O legado deixa "lixo" em slots desativados (valores antigos persistidos).
    Filtramos pelo multiselect beneficios_ativos_c (ex: '^IN^,^FA^,^RE^') —
    só viram linha em valor_beneficio_sindicato os tipos ativos.

Pré-requisitos:
    - bss.sindicato sincronizado (precisamos do mapping uuid → id)
    - bss.tipo_beneficio com codigo_legado/slot_legado preenchidos (migration 02)
    - bss.parametros_boleto com UNIQUE(id_sindicato) (migration 03)
"""

from __future__ import annotations

import re
from typing import Any

from ..database import get_mysql_connection, get_pg_connection
from ._base import Progresso, mysql_iter, trim_or_none


# Pull do legado: já junta sindicato + parâmetro + cstm em uma só passada.
# Aliases pra ficar legível no Python.
SQL_LEGADO = """
    SELECT
        s.id                              AS sind_uuid,
        p.id                              AS param_uuid,
        p.name                            AS param_nome,
        pc.tarifa_c                       AS tarifa_titular,
        pc.aceita_dependentes_c           AS aceita_dependentes,
        pc.tarifa_dependente_c            AS tarifa_dependente,
        pc.carencia_dependente_c          AS carencia_dependente_dias,
        pc.banco_geracao_boleto_c         AS banco_geracao_boleto,
        pc.banco_boleto_dependente_c      AS banco_boleto_dependente,
        pc.tipo_c                         AS tipo,
        pc.beneficios_ativos_c            AS beneficios_ativos,
        pc.vencimento_jan_c               AS venc_jan,
        pc.vencimento_fev_c               AS venc_fev,
        pc.vencimento_mar_c               AS venc_mar,
        pc.vencimento_abr_c               AS venc_abr,
        pc.vencimento_maio_c              AS venc_mai,
        pc.vencimento_jun_c               AS venc_jun,
        pc.vencimento_jul_c               AS venc_jul,
        pc.vencimento_ago_c               AS venc_ago,
        pc.vencimento_set_c               AS venc_set,
        pc.vencimento_out_c               AS venc_out,
        pc.vencimento_nov_c               AS venc_nov,
        pc.vencimento_dez_c               AS venc_dez,
        -- 10 slots × 4 campos (primeiro_pagamento, qtd_parcelas, valor_parcela, prazo)
        pc.primeiro_pagamento_c   AS slot1_primeiro,  pc.qtd_parcelas_c   AS slot1_qtd,
        pc.valor_parcela_c        AS slot1_valor,     pc.prazo_c          AS slot1_prazo,
        pc.primeiro_pagamento2_c  AS slot2_primeiro,  pc.qtd_parcelas2_c  AS slot2_qtd,
        pc.valor_parcela2_c       AS slot2_valor,     pc.prazo2_c         AS slot2_prazo,
        pc.primeiro_pagamento3_c  AS slot3_primeiro,  pc.qtd_parcelas3_c  AS slot3_qtd,
        pc.valor_parcela3_c       AS slot3_valor,     pc.prazo3_c         AS slot3_prazo,
        pc.primeiro_pagamento4_c  AS slot4_primeiro,  pc.qtd_parcelas4_c  AS slot4_qtd,
        pc.valor_parcela4_c       AS slot4_valor,     pc.prazo4_c         AS slot4_prazo,
        pc.primeiro_pagamento5_c  AS slot5_primeiro,  pc.qtd_parcelas5_c  AS slot5_qtd,
        pc.valor_parcela5_c       AS slot5_valor,     pc.prazo5_c         AS slot5_prazo,
        pc.primeiro_pagamento6_c  AS slot6_primeiro,  pc.qtd_parcelas6_c  AS slot6_qtd,
        pc.valor_parcela6_c       AS slot6_valor,     pc.prazo6_c         AS slot6_prazo,
        pc.primeiro_pagamento7_c  AS slot7_primeiro,  pc.qtd_parcelas7_c  AS slot7_qtd,
        pc.valor_parcela7_c       AS slot7_valor,     pc.prazo7_c         AS slot7_prazo,
        pc.primeiro_pagamento8_c  AS slot8_primeiro,  pc.qtd_parcelas8_c  AS slot8_qtd,
        pc.valor_parcela8_c       AS slot8_valor,     pc.prazo8_c         AS slot8_prazo,
        pc.primeiro_pagamento9_c  AS slot9_primeiro,  pc.qtd_parcelas9_c  AS slot9_qtd,
        pc.valor_parcela9_c       AS slot9_valor,     pc.prazo9_c         AS slot9_prazo,
        pc.primeiro_pagamento10_c AS slot10_primeiro, pc.qtd_parcelas10_c AS slot10_qtd,
        pc.valor_parcela10_c      AS slot10_valor,    pc.prazo10_c        AS slot10_prazo
    FROM sindi_sindicatos s
    JOIN sindi_sindicatos_cstm sc ON sc.id_c = s.id
    JOIN cbr_parametros_boleto p  ON p.id   = sc.cbr_parametros_boleto_id_c
    LEFT JOIN cbr_parametros_boleto_cstm pc ON pc.id_c = p.id
    WHERE s.deleted = 0
      AND p.deleted = 0
      AND sc.cbr_parametros_boleto_id_c IS NOT NULL
      AND sc.cbr_parametros_boleto_id_c != ''
"""


SQL_UPSERT_PARAM = """
    INSERT INTO bss.parametros_boleto (
        id_legado_uuid, id_sindicato,
        tarifa_titular, aceita_dependentes, tarifa_dependente, carencia_dependente_dias,
        vencimento_jan, vencimento_fev, vencimento_mar, vencimento_abr,
        vencimento_mai, vencimento_jun, vencimento_jul, vencimento_ago,
        vencimento_set, vencimento_out, vencimento_nov, vencimento_dez,
        banco_geracao_boleto, banco_boleto_dependente, tipo, ativo
    )
    VALUES (%s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, TRUE)
    ON CONFLICT (id_sindicato) DO UPDATE
        SET id_legado_uuid           = EXCLUDED.id_legado_uuid,
            tarifa_titular           = EXCLUDED.tarifa_titular,
            aceita_dependentes       = EXCLUDED.aceita_dependentes,
            tarifa_dependente        = EXCLUDED.tarifa_dependente,
            carencia_dependente_dias = EXCLUDED.carencia_dependente_dias,
            vencimento_jan = EXCLUDED.vencimento_jan, vencimento_fev = EXCLUDED.vencimento_fev,
            vencimento_mar = EXCLUDED.vencimento_mar, vencimento_abr = EXCLUDED.vencimento_abr,
            vencimento_mai = EXCLUDED.vencimento_mai, vencimento_jun = EXCLUDED.vencimento_jun,
            vencimento_jul = EXCLUDED.vencimento_jul, vencimento_ago = EXCLUDED.vencimento_ago,
            vencimento_set = EXCLUDED.vencimento_set, vencimento_out = EXCLUDED.vencimento_out,
            vencimento_nov = EXCLUDED.vencimento_nov, vencimento_dez = EXCLUDED.vencimento_dez,
            banco_geracao_boleto    = EXCLUDED.banco_geracao_boleto,
            banco_boleto_dependente = EXCLUDED.banco_boleto_dependente,
            tipo                    = EXCLUDED.tipo,
            atualizado_em           = NOW()
"""


SQL_UPSERT_VALOR = """
    INSERT INTO bss.valor_beneficio_sindicato (
        id_sindicato, id_tipo_beneficio,
        primeiro_pagamento, qtd_parcelas, valor_parcela, prazo_dias, ativo
    )
    VALUES (%s, %s, %s, %s, %s, %s, TRUE)
    ON CONFLICT (id_sindicato, id_tipo_beneficio) DO UPDATE
        SET primeiro_pagamento = EXCLUDED.primeiro_pagamento,
            qtd_parcelas       = EXCLUDED.qtd_parcelas,
            valor_parcela      = EXCLUDED.valor_parcela,
            prazo_dias         = EXCLUDED.prazo_dias,
            ativo              = TRUE,
            atualizado_em      = NOW()
"""


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────
_RE_BENEF = re.compile(r"\^([A-Z]{2})\^")


def _parse_aceita_dep(v: Any) -> bool:
    """Legado armazena '1' = Sim, '2' = Não. Qualquer outra coisa → False."""
    if v in (1, "1", True):
        return True
    return False


def _parse_beneficios_ativos(s: str | None) -> set[str]:
    """'^IN^,^FA^,^RE^' → {'IN', 'FA', 'RE'}. Vazio/None → set()."""
    if not s:
        return set()
    return set(_RE_BENEF.findall(s))


def _to_int(v: Any) -> int | None:
    """Aceita int, float, str numérica, '' / None / 'abc' → None."""
    if v is None or v == "":
        return None
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return None


def _to_dec(v: Any) -> Any:
    """Mantém Decimal/float; None ou string vazia → 0."""
    if v is None or v == "":
        return 0
    return v


# ──────────────────────────────────────────────────────────────────────────
# Loaders
# ──────────────────────────────────────────────────────────────────────────
def _carregar_sind_map(pg_conn) -> dict[str, int]:
    m: dict[str, int] = {}
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT id, id_legado_uuid FROM bss.sindicato "
            "WHERE id_legado_uuid IS NOT NULL"
        )
        for r in cur:
            m[r["id_legado_uuid"]] = r["id"]
    return m


def _carregar_tipo_legado_map(pg_conn) -> dict[str, tuple[int, int]]:
    """{codigo_legado → (id_tipo_beneficio, slot_legado)}"""
    m: dict[str, tuple[int, int]] = {}
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT id, codigo_legado, slot_legado FROM bss.tipo_beneficio "
            "WHERE codigo_legado IS NOT NULL AND slot_legado IS NOT NULL AND ativo"
        )
        for r in cur:
            m[r["codigo_legado"]] = (r["id"], r["slot_legado"])
    return m


# ──────────────────────────────────────────────────────────────────────────
# Conversões linha-a-linha
# ──────────────────────────────────────────────────────────────────────────
def _row_to_param_tuple(row: dict, id_sindicato: int) -> tuple:
    return (
        row["param_uuid"],
        id_sindicato,
        row.get("tarifa_titular"),
        _parse_aceita_dep(row.get("aceita_dependentes")),
        row.get("tarifa_dependente"),
        _to_int(row.get("carencia_dependente_dias")),
        _to_int(row.get("venc_jan")), _to_int(row.get("venc_fev")),
        _to_int(row.get("venc_mar")), _to_int(row.get("venc_abr")),
        _to_int(row.get("venc_mai")), _to_int(row.get("venc_jun")),
        _to_int(row.get("venc_jul")), _to_int(row.get("venc_ago")),
        _to_int(row.get("venc_set")), _to_int(row.get("venc_out")),
        _to_int(row.get("venc_nov")), _to_int(row.get("venc_dez")),
        trim_or_none(row.get("banco_geracao_boleto"), 100),
        trim_or_none(row.get("banco_boleto_dependente"), 100),
        trim_or_none(row.get("tipo"), 50),
    )


def _row_to_valor_tuples(
    row: dict,
    id_sindicato: int,
    tipo_legado_map: dict[str, tuple[int, int]],
) -> list[tuple]:
    """Explode os 10 slots do legado em N linhas, filtrando por beneficios_ativos."""
    ativos = _parse_beneficios_ativos(row.get("beneficios_ativos"))
    out: list[tuple] = []
    for codigo in ativos:
        if codigo not in tipo_legado_map:
            # Código no multiselect do legado que não tá em bss.tipo_beneficio
            # (não esperado, mas defensivo). Loga e segue.
            print(f"    ⚠ código de benefício desconhecido em multiselect: {codigo}")
            continue
        id_tipo, slot = tipo_legado_map[codigo]
        primeiro = _to_dec(row.get(f"slot{slot}_primeiro"))
        qtd      = _to_int(row.get(f"slot{slot}_qtd")) or 0
        valor    = _to_dec(row.get(f"slot{slot}_valor"))
        prazo    = _to_int(row.get(f"slot{slot}_prazo"))
        out.append((id_sindicato, id_tipo, primeiro, qtd, valor, prazo))
    return out


# ──────────────────────────────────────────────────────────────────────────
# Sync
# ──────────────────────────────────────────────────────────────────────────
def sync(dry_run: bool = False, limite: int | None = None) -> tuple[int, int]:
    """Retorna (n_parametros_upsert, n_valores_upsert)."""
    print(f"\n=== Sync PARAMETROS_BOLETO ({'dry-run' if dry_run else 'gravação'}) ===")

    print("  carregando lookups do BSS...")
    with get_pg_connection() as pg:
        sind_map = _carregar_sind_map(pg)
        tipo_legado_map = _carregar_tipo_legado_map(pg)
    print(f"  ✓ {len(sind_map)} sindicatos, {len(tipo_legado_map)} tipos benefício")

    if not tipo_legado_map:
        raise RuntimeError(
            "bss.tipo_beneficio sem codigo_legado/slot_legado preenchidos. "
            "Rode antes a migration 02_legado_dropdown.sql."
        )

    sql = SQL_LEGADO + (f" LIMIT {int(limite)}" if limite else "")
    n_param = 0
    n_valor = 0
    n_skip_sind = 0

    with get_mysql_connection() as my:
        rows = list(mysql_iter(my, sql, batch_size=200))
    print(f"  legado retornou {len(rows)} pares sindicato↔parâmetro")

    prog = Progresso(total=len(rows), nome="param")

    if dry_run:
        for row in rows:
            id_sindicato = sind_map.get(row["sind_uuid"])
            if not id_sindicato:
                n_skip_sind += 1
                prog.tick()
                continue
            n_param += 1
            n_valor += len(_row_to_valor_tuples(row, id_sindicato, tipo_legado_map))
            prog.tick()
    else:
        with get_pg_connection() as pg:
            with pg.cursor() as cur:
                for row in rows:
                    id_sindicato = sind_map.get(row["sind_uuid"])
                    if not id_sindicato:
                        n_skip_sind += 1
                        prog.tick()
                        continue
                    cur.execute(SQL_UPSERT_PARAM, _row_to_param_tuple(row, id_sindicato))
                    n_param += 1
                    for tpl in _row_to_valor_tuples(row, id_sindicato, tipo_legado_map):
                        cur.execute(SQL_UPSERT_VALOR, tpl)
                        n_valor += 1
                    prog.tick()
            pg.commit()

    prog.fim()
    print(f"\n  ✓ parametros_boleto: {n_param} upsert(s)")
    print(f"  ✓ valor_beneficio_sindicato: {n_valor} upsert(s)")
    if n_skip_sind:
        print(f"  ⚠ {n_skip_sind} sindicato(s) ignorados (UUID não bateu com BSS)")
    return n_param, n_valor


if __name__ == "__main__":
    import sys
    dry = "--dry" in sys.argv
    sync(dry_run=dry)
