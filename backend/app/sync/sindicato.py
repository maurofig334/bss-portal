"""
Sincroniza sindicatos: sindi_sindicatos + sindi_sindicatos_cstm → bss.sindicato

Volume estimado: 147 linhas. Roda em segundos.

ATENÇÃO: os nomes das colunas custom (com sufixo _c) são EXEMPLOS baseados em
padrões típicos do SuiteCRM. Antes de rodar em produção, valide os nomes reais
rodando: SELECT * FROM information_schema.COLUMNS WHERE TABLE_NAME='sindi_sindicatos_cstm';
"""

from __future__ import annotations

from ..database import get_mysql_connection, get_pg_connection
from ._base import Progresso, mysql_iter, pg_executemany, so_digitos, trim_or_none


# Query do legado: junta tabela base + custom.
# Nomes das colunas custom obtidos via inspecionar_cstm (2026-05-05).
SQL_LEGADO = """
    SELECT
        s.id                            AS uuid,
        s.name                          AS razao_social,
        sc.razsocial_c                  AS nome_fantasia,
        sc.cnpj_c                       AS cnpj,
        sc.federacao_c                  AS federacao,
        sc.categoria_c                  AS categoria,
        sc.presidente_c                 AS presidente,
        sc.vicepresidente_c             AS vice_presidente,
        sc.ufabangencia_c               AS uf_abrangencia,
        sc.contrato_bss_c               AS contrato_bss,
        sc.ematendimento_c              AS em_atendimento,
        sc.trabalhadores_ativos_c       AS qtd_trabalhadores_ativos,
        sc.trabalhadores_inativos_c     AS qtd_trabalhadores_inativos
    FROM sindi_sindicatos s
    LEFT JOIN sindi_sindicatos_cstm sc ON sc.id_c = s.id
    WHERE s.deleted = 0
"""


# UPSERT no Postgres (idempotente — chave: id_legado_uuid)
SQL_UPSERT = """
    INSERT INTO bss.sindicato (
        id_legado_uuid, razao_social, nome_fantasia, cnpj,
        federacao, categoria, presidente, vice_presidente,
        uf_abrangencia, contrato_bss, em_atendimento,
        qtd_trabalhadores_ativos, qtd_trabalhadores_inativos, ativo
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
    ON CONFLICT (id_legado_uuid) DO UPDATE
        SET razao_social    = EXCLUDED.razao_social,
            nome_fantasia   = EXCLUDED.nome_fantasia,
            cnpj            = EXCLUDED.cnpj,
            federacao       = EXCLUDED.federacao,
            categoria       = EXCLUDED.categoria,
            presidente      = EXCLUDED.presidente,
            vice_presidente = EXCLUDED.vice_presidente,
            uf_abrangencia  = EXCLUDED.uf_abrangencia,
            contrato_bss    = EXCLUDED.contrato_bss,
            em_atendimento  = EXCLUDED.em_atendimento,
            qtd_trabalhadores_ativos    = EXCLUDED.qtd_trabalhadores_ativos,
            qtd_trabalhadores_inativos  = EXCLUDED.qtd_trabalhadores_inativos,
            atualizado_em   = NOW()
"""


def _converter(linha: dict) -> tuple:
    """Transforma linha do MySQL no formato esperado pelo INSERT."""
    em_atend = linha.get("em_atendimento")
    em_atend_bool = (
        True if em_atend in (1, "1", True, "Sim", "S") else False
        if em_atend in (0, "0", False, "Não", "N") else True  # default ativo
    )
    cnpj = so_digitos(linha.get("cnpj"))
    return (
        linha["uuid"],
        trim_or_none(linha["razao_social"], 255) or "(SEM NOME)",
        trim_or_none(linha.get("nome_fantasia"), 255),
        cnpj[:14] if cnpj else None,
        trim_or_none(linha.get("federacao"), 255),
        trim_or_none(linha.get("categoria"), 100),
        trim_or_none(linha.get("presidente"), 255),
        trim_or_none(linha.get("vice_presidente"), 255),
        trim_or_none(linha.get("uf_abrangencia"), 2),
        trim_or_none(linha.get("contrato_bss"), 255),
        em_atend_bool,
        int(linha.get("qtd_trabalhadores_ativos") or 0),
        int(linha.get("qtd_trabalhadores_inativos") or 0),
    )


def sync(dry_run: bool = False, limite: int | None = None) -> int:
    """
    Sincroniza sindicatos do legado pro BSS.

    Args:
        dry_run: se True, só lê do MySQL e imprime amostra (não escreve).
        limite: se setado, processa só as N primeiras linhas (útil pra teste).

    Returns:
        Quantidade de sindicatos processados.
    """
    print(f"\n=== Sync SINDICATO ({'dry-run' if dry_run else 'gravação'}) ===")

    sql = SQL_LEGADO + (f" LIMIT {int(limite)}" if limite else "")
    prog = Progresso(total=None, nome="sindicato")

    with get_mysql_connection() as mysql_conn:
        def converter_iter():
            for linha in mysql_iter(mysql_conn, sql, batch_size=200):
                if dry_run and prog.contador < 3:
                    print(f"  amostra: {linha}")
                prog.tick()
                yield _converter(linha)

        if dry_run:
            # Dry-run NÃO conecta no Postgres — só lê do MySQL e imprime amostras.
            for _ in converter_iter():
                pass
        else:
            # Sync de verdade: abre Postgres só agora e UPSERT em lote.
            with get_pg_connection() as pg_conn:
                pg_executemany(pg_conn, SQL_UPSERT, converter_iter(), batch_size=200)

    prog.fim()
    return prog.contador
