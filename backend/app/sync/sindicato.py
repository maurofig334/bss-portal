"""
Sincroniza sindicatos: sindi_sindicatos + sindi_sindicatos_cstm → bss.sindicato

Volume estimado: ~147 linhas. Roda em segundos.

Mapping (atualizado em 2026-05-11 — épico/task #17):
  s.name                      → razao_social   (nome curto exibido na tela)
  sc.razsocial_c              → nome_fantasia  (nome longo da razao social juridica)
  sc.cnpj_c                   → cnpj
  sc.federacao_c              → federacao
  sc.categoria_c              → categoria
  sc.presidente_c             → presidente
  sc.vicepresidente_c         → vice_presidente
  sc.ufabangencia_c           → uf_abrangencia
  sc.contrato_bss_c           → contrato_bss
  sc.ematendimento_c          → em_atendimento
  sc.trabalhadores_ativos_c   → qtd_trabalhadores_ativos
  sc.trabalhadores_inativos_c → qtd_trabalhadores_inativos
  sc.patronaleempresa_c       → patronal_empresa
  s.sindi_sindicatos_type     → tipo_sindicato (ex: 'FEMACO')
  s.phone_office              → telefone
  s.phone_alternate           → outro_telefone
  s.phone_fax                 → fax
  s.website                   → website
  s.description               → descricao
  s.shipping_address_*        → endereco_* (5 campos)
  email_addr_bean_rel + email_addresses → email (LEFT JOIN, primary_address=1)
  sc.contact_id_c → contato_principal (via contacts.first_name + last_name)
"""

from __future__ import annotations

from ..database import get_mysql_connection, get_pg_connection
from ._base import Progresso, mysql_iter, pg_executemany, so_digitos, trim_or_none


SQL_LEGADO = """
    SELECT
        s.id                            AS uuid,
        s.name                          AS razao_social,
        s.sindi_sindicatos_type         AS tipo_sindicato,
        s.phone_office                  AS telefone,
        s.phone_alternate               AS outro_telefone,
        s.phone_fax                     AS fax,
        s.website                       AS website,
        s.description                   AS descricao,
        s.shipping_address_street       AS endereco_logradouro,
        s.shipping_address_city         AS endereco_cidade,
        s.shipping_address_state        AS endereco_uf,
        s.shipping_address_postalcode   AS endereco_cep,
        s.shipping_address_country      AS endereco_pais,
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
        sc.trabalhadores_inativos_c     AS qtd_trabalhadores_inativos,
        sc.patronaleempresa_c           AS patronal_empresa,
        -- Email principal via relacionamento padrão SuiteCRM:
        (SELECT ea.email_address
           FROM email_addr_bean_rel eabr
           JOIN email_addresses ea ON ea.id = eabr.email_address_id
          WHERE eabr.bean_module = 'sindi_sindicatos'
            AND eabr.bean_id = s.id
            AND eabr.primary_address = 1
            AND eabr.deleted = 0
            AND ea.deleted = 0
          LIMIT 1)                      AS email,
        -- Contato principal: full name a partir de contacts:
        (SELECT TRIM(CONCAT(COALESCE(c.first_name,''), ' ', COALESCE(c.last_name,'')))
           FROM contacts c
          WHERE c.id = sc.contact_id_c
            AND c.deleted = 0
          LIMIT 1)                      AS contato_principal
    FROM sindi_sindicatos s
    LEFT JOIN sindi_sindicatos_cstm sc ON sc.id_c = s.id
    WHERE s.deleted = 0
"""


SQL_UPSERT = """
    INSERT INTO bss.sindicato (
        id_legado_uuid, razao_social, nome_fantasia, cnpj,
        federacao, categoria, presidente, vice_presidente,
        uf_abrangencia, contrato_bss, em_atendimento,
        qtd_trabalhadores_ativos, qtd_trabalhadores_inativos, ativo,
        tipo_sindicato, telefone, outro_telefone, fax,
        email, contato_principal, patronal_empresa, website, descricao,
        endereco_logradouro, endereco_cidade, endereco_uf, endereco_cep, endereco_pais
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE,
            %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s)
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
            tipo_sindicato  = EXCLUDED.tipo_sindicato,
            telefone        = EXCLUDED.telefone,
            outro_telefone  = EXCLUDED.outro_telefone,
            fax             = EXCLUDED.fax,
            email           = EXCLUDED.email,
            contato_principal = EXCLUDED.contato_principal,
            patronal_empresa  = EXCLUDED.patronal_empresa,
            website         = EXCLUDED.website,
            descricao       = EXCLUDED.descricao,
            endereco_logradouro = EXCLUDED.endereco_logradouro,
            endereco_cidade = EXCLUDED.endereco_cidade,
            endereco_uf     = EXCLUDED.endereco_uf,
            endereco_cep    = EXCLUDED.endereco_cep,
            endereco_pais   = EXCLUDED.endereco_pais,
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
        # Bloco 1 — campos já existentes
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
        # Bloco 2 — campos NOVOS
        trim_or_none(linha.get("tipo_sindicato"), 50),
        trim_or_none(linha.get("telefone"), 100),
        trim_or_none(linha.get("outro_telefone"), 100),
        trim_or_none(linha.get("fax"), 100),
        trim_or_none(linha.get("email"), 255),
        trim_or_none(linha.get("contato_principal"), 255) or None,
        trim_or_none(linha.get("patronal_empresa"), 255),
        trim_or_none(linha.get("website"), 255),
        linha.get("descricao"),  # TEXT, sem trim
        trim_or_none(linha.get("endereco_logradouro"), 255),
        trim_or_none(linha.get("endereco_cidade"), 100),
        trim_or_none(linha.get("endereco_uf"), 2),
        trim_or_none(linha.get("endereco_cep"), 10),
        trim_or_none(linha.get("endereco_pais"), 50),
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
            for _ in converter_iter():
                pass
        else:
            with get_pg_connection() as pg_conn:
                pg_executemany(pg_conn, SQL_UPSERT, converter_iter(), batch_size=200)

    prog.fim()
    return prog.contador
