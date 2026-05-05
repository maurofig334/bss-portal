"""
Sincroniza empresas: accounts + accounts_cstm → bss.empresa

Volume estimado: 7.744 linhas. Roda em <30s.

Mapping principal:
  accounts.name                    → razao_social
  cstm.cnpj_unformat_c (só dígitos) → cnpj
  accounts.billing_address_*       → endereço (logradouro/cidade/uf/cep)
  accounts.phone_office            → telefone
  cstm.statusempresa_c             → status
  cstm.regularidade_c              → regularidade
  cstm.trabalhadores_ativos_c      → qtd_trabalhadores_ativos (cache)
  cstm.recebeemailfinanceiro_c     → recebe_email_financeiro (Sim/Não → bool)
"""

from __future__ import annotations

from ..database import get_mysql_connection, get_pg_connection
from ._base import Progresso, mysql_iter, pg_executemany, so_digitos, trim_or_none


SQL_LEGADO = """
    SELECT
        a.id                                AS uuid,
        a.name                              AS razao_social,
        COALESCE(
            NULLIF(ac.cnpj_unformat_c, ''),
            ac.cnpj_c
        )                                   AS cnpj_raw,
        a.billing_address_street            AS logradouro,
        a.billing_address_city              AS cidade,
        a.billing_address_state             AS uf,
        a.billing_address_postalcode        AS cep,
        a.phone_office                      AS telefone,
        ac.statusempresa_c                  AS status,
        ac.ativa_c                          AS ativa,
        ac.regularidade_c                   AS regularidade,
        ac.recebeemailfinanceiro_c          AS recebe_email,
        ac.trabalhadores_ativos_c           AS qtd_trab_ativos,
        ac.trabalhadores_inativos_c         AS qtd_trab_inativos,
        ac.dependentes_ativos_c             AS qtd_dep_ativos,
        ac.ultimo_boleto_c                  AS ultimo_boleto_em,
        ac.ultima_notificacao_c             AS ultima_notificacao_em
    FROM accounts a
    LEFT JOIN accounts_cstm ac ON ac.id_c = a.id
    WHERE a.deleted = 0
"""


SQL_UPSERT = """
    INSERT INTO bss.empresa (
        id_legado_uuid, razao_social, cnpj,
        logradouro, cidade, uf, cep,
        telefone,
        status, regularidade, recebe_email_financeiro,
        qtd_trabalhadores_ativos, qtd_trabalhadores_inativos, qtd_dependentes_ativos,
        ultimo_boleto_em, ultima_notificacao_em
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (id_legado_uuid) DO UPDATE
        SET razao_social    = EXCLUDED.razao_social,
            cnpj            = EXCLUDED.cnpj,
            logradouro      = EXCLUDED.logradouro,
            cidade          = EXCLUDED.cidade,
            uf              = EXCLUDED.uf,
            cep             = EXCLUDED.cep,
            telefone        = EXCLUDED.telefone,
            status          = EXCLUDED.status,
            regularidade    = EXCLUDED.regularidade,
            recebe_email_financeiro     = EXCLUDED.recebe_email_financeiro,
            qtd_trabalhadores_ativos    = EXCLUDED.qtd_trabalhadores_ativos,
            qtd_trabalhadores_inativos  = EXCLUDED.qtd_trabalhadores_inativos,
            qtd_dependentes_ativos      = EXCLUDED.qtd_dependentes_ativos,
            ultimo_boleto_em            = EXCLUDED.ultimo_boleto_em,
            ultima_notificacao_em       = EXCLUDED.ultima_notificacao_em,
            atualizado_em               = NOW()
"""


def _converter_bool(v) -> bool:
    """Converte 'Sim'/'Não'/None → bool. Default True (recebe email)."""
    if v is None:
        return True
    s = str(v).strip().lower()
    return s in ("sim", "s", "yes", "y", "1", "true", "verdadeiro")


def _normalizar_status(v) -> str:
    """Normaliza statusempresa_c em valores padronizados."""
    if not v:
        return "ativa"
    s = str(v).strip().lower()
    if "cancel" in s:
        return "cancelada"
    if "suspen" in s:
        return "suspensa"
    return "ativa"


def _converter(linha: dict) -> tuple:
    cnpj = so_digitos(linha.get("cnpj_raw"))
    return (
        linha["uuid"],
        trim_or_none(linha["razao_social"], 255) or "(SEM NOME)",
        cnpj[:14] if cnpj else None,
        trim_or_none(linha.get("logradouro"), 150),
        trim_or_none(linha.get("cidade"), 100),
        trim_or_none(linha.get("uf"), 2),
        so_digitos(linha.get("cep"))[:8] if so_digitos(linha.get("cep")) else None,
        trim_or_none(linha.get("telefone"), 20),
        _normalizar_status(linha.get("status")),
        trim_or_none(linha.get("regularidade"), 50),
        _converter_bool(linha.get("recebe_email")),
        int(linha.get("qtd_trab_ativos") or 0),
        int(linha.get("qtd_trab_inativos") or 0),
        int(linha.get("qtd_dep_ativos") or 0),
        linha.get("ultimo_boleto_em"),
        linha.get("ultima_notificacao_em"),
    )


def sync(dry_run: bool = False, limite: int | None = None) -> int:
    """Sincroniza empresas do legado pro BSS."""
    print(f"\n=== Sync EMPRESA ({'dry-run' if dry_run else 'gravação'}) ===")

    sql = SQL_LEGADO + (f" LIMIT {int(limite)}" if limite else "")
    prog = Progresso(total=None, nome="empresa")

    with get_mysql_connection() as mysql_conn:
        def converter_iter():
            for linha in mysql_iter(mysql_conn, sql, batch_size=500):
                if dry_run and prog.contador < 3:
                    print(f"  amostra: {linha}")
                prog.tick()
                yield _converter(linha)

        if dry_run:
            for _ in converter_iter():
                pass
        else:
            with get_pg_connection() as pg_conn:
                pg_executemany(pg_conn, SQL_UPSERT, converter_iter(), batch_size=500)

    prog.fim()
    return prog.contador
