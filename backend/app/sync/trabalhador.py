"""
Sincroniza trabalhadores: traba_trabalhadores + traba_trabalhadores_cstm → bss.trabalhador

Volume: ~300k+ linhas. Tempo estimado: 1-3 min.

Pré-requisito: bss.empresa e bss.sindicato JÁ sincronizadas — precisamos delas
pra resolver os FKs (account_id_c → bss.empresa.id; sindi_sindicatos_id_c → bss.sindicato.id).

Mapping principal:
  cstm.cpf_unformat_c (sem máscara) → cpf
  t.name                            → nome_completo
  cstm.account_id_c (UUID)          → id_empresa_atual (resolvido em memória)
  cstm.sindi_sindicatos_id_c        → id_sindicato_atual (resolvido em memória)
  cstm.titularidade_c               → titularidade (Titular/Dependente)
  cstm.situacaodotrabalhador_c      → situacao (Ativo/Inativo/Carência)
"""

from __future__ import annotations

from ..database import get_mysql_connection, get_pg_connection
from ._base import Progresso, mysql_iter, pg_executemany, so_digitos, trim_or_none


SQL_LEGADO = """
    SELECT
        t.id                                AS uuid,
        TRIM(CONCAT_WS(' ', t.first_name, t.last_name)) AS nome_completo,
        COALESCE(NULLIF(tc.cpf_unformat_c, ''), tc.cpf_c) AS cpf_raw,
        tc.data_nascimento_c                AS data_nascimento,
        tc.data_admissao_c                  AS data_admissao,
        tc.account_id_c                     AS uuid_empresa,
        tc.sindi_sindicatos_id_c            AS uuid_sindicato,
        tc.titularidade_c                   AS titularidade,
        tc.cpf_titular_c                    AS cpf_titular,
        tc.dep_relacionados_c               AS qtd_dependentes,
        tc.situacaodotrabalhador_c          AS situacao,
        tc.data_fim_carencia_c              AS data_fim_carencia,
        tc.ultimo_pagamento_c               AS ultimo_pagamento_em,
        COALESCE(NULLIF(t.phone_mobile,''), NULLIF(t.phone_work,''), NULLIF(t.phone_home,'')) AS telefone,
        t.primary_address_street            AS logradouro,
        t.primary_address_city              AS cidade,
        t.primary_address_state             AS uf,
        t.primary_address_postalcode        AS cep
    FROM traba_trabalhadores t
    LEFT JOIN traba_trabalhadores_cstm tc ON tc.id_c = t.id
    WHERE t.deleted = 0
"""


SQL_UPSERT = """
    INSERT INTO bss.trabalhador (
        id_legado_uuid, cpf, nome_completo, data_nascimento, data_admissao,
        id_empresa_atual, id_sindicato_atual,
        titularidade, cpf_titular, qtd_dependentes_ativos,
        situacao, data_fim_carencia, ultimo_pagamento_em,
        telefone, logradouro, cidade, uf, cep
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (id_legado_uuid) DO UPDATE
        SET cpf                     = EXCLUDED.cpf,
            nome_completo           = EXCLUDED.nome_completo,
            data_nascimento         = EXCLUDED.data_nascimento,
            data_admissao           = EXCLUDED.data_admissao,
            id_empresa_atual        = EXCLUDED.id_empresa_atual,
            id_sindicato_atual      = EXCLUDED.id_sindicato_atual,
            titularidade            = EXCLUDED.titularidade,
            cpf_titular             = EXCLUDED.cpf_titular,
            qtd_dependentes_ativos  = EXCLUDED.qtd_dependentes_ativos,
            situacao                = EXCLUDED.situacao,
            data_fim_carencia       = EXCLUDED.data_fim_carencia,
            ultimo_pagamento_em     = EXCLUDED.ultimo_pagamento_em,
            telefone                = EXCLUDED.telefone,
            logradouro              = EXCLUDED.logradouro,
            cidade                  = EXCLUDED.cidade,
            uf                      = EXCLUDED.uf,
            cep                     = EXCLUDED.cep,
            atualizado_em           = NOW()
"""


def _normalizar_titularidade(v) -> str:
    if not v:
        return "titular"
    s = str(v).strip().lower()
    if "depend" in s:
        return "dependente"
    return "titular"


def _normalizar_situacao(v) -> str:
    """ Ativo/Inativo/Carência → ativo/inativo/carencia """
    if not v:
        return "ativo"
    s = str(v).strip().lower()
    if "inativ" in s:
        return "inativo"
    if "caren" in s:
        return "carencia"
    if "ativ" in s:
        return "ativo"
    return s[:50]


def _carregar_mappings(pg_conn) -> tuple[dict, dict]:
    """Pré-carrega UUID legado → ID BSS para empresa e sindicato."""
    empresa_map: dict[str, int] = {}
    sindicato_map: dict[str, int] = {}
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT id, id_legado_uuid FROM bss.empresa WHERE id_legado_uuid IS NOT NULL"
        )
        for row in cur:
            empresa_map[row["id_legado_uuid"]] = row["id"]
        cur.execute(
            "SELECT id, id_legado_uuid FROM bss.sindicato WHERE id_legado_uuid IS NOT NULL"
        )
        for row in cur:
            sindicato_map[row["id_legado_uuid"]] = row["id"]
    return empresa_map, sindicato_map


def _converter(linha: dict, emp_map: dict, sind_map: dict) -> tuple:
    cpf = so_digitos(linha.get("cpf_raw"))
    cpf_titular = so_digitos(linha.get("cpf_titular"))
    cep = so_digitos(linha.get("cep"))
    return (
        linha["uuid"],
        cpf[:11] if cpf else None,
        trim_or_none(linha.get("nome_completo"), 200) or "(SEM NOME)",
        linha.get("data_nascimento"),
        linha.get("data_admissao"),
        emp_map.get(linha.get("uuid_empresa")),
        sind_map.get(linha.get("uuid_sindicato")),
        _normalizar_titularidade(linha.get("titularidade")),
        cpf_titular[:11] if cpf_titular else None,
        int(linha.get("qtd_dependentes") or 0),
        _normalizar_situacao(linha.get("situacao")),
        linha.get("data_fim_carencia"),
        linha.get("ultimo_pagamento_em"),
        trim_or_none(linha.get("telefone"), 20),
        trim_or_none(linha.get("logradouro"), 150),
        trim_or_none(linha.get("cidade"), 100),
        trim_or_none(linha.get("uf"), 2),
        cep[:8] if cep else None,
    )


def sync(dry_run: bool = False, limite: int | None = None) -> int:
    print(f"\n=== Sync TRABALHADOR ({'dry-run' if dry_run else 'gravação'}) ===")

    # Pré-carrega mappings UUID → ID das tabelas já sincronizadas (FKs do trabalhador)
    print("  carregando mapeamentos UUID→ID de empresa e sindicato...")
    with get_pg_connection() as pg_conn:
        emp_map, sind_map = _carregar_mappings(pg_conn)
    print(f"  ✓ {len(emp_map)} empresas, {len(sind_map)} sindicatos em memória")

    sql = SQL_LEGADO + (f" LIMIT {int(limite)}" if limite else "")
    prog = Progresso(total=None, nome="trabalhador")
    sem_empresa = 0
    sem_sindicato = 0

    with get_mysql_connection() as mysql_conn:
        def converter_iter():
            nonlocal sem_empresa, sem_sindicato
            for linha in mysql_iter(mysql_conn, sql, batch_size=2000):
                if dry_run and prog.contador < 3:
                    print(f"  amostra: {linha}")
                # Conta órfãos pra reportar no final
                if linha.get("uuid_empresa") and linha["uuid_empresa"] not in emp_map:
                    sem_empresa += 1
                if linha.get("uuid_sindicato") and linha["uuid_sindicato"] not in sind_map:
                    sem_sindicato += 1
                prog.tick()
                yield _converter(linha, emp_map, sind_map)

        if dry_run:
            for _ in converter_iter():
                pass
        else:
            with get_pg_connection() as pg_conn:
                pg_executemany(pg_conn, SQL_UPSERT, converter_iter(), batch_size=1000)

    prog.fim()
    if sem_empresa:
        print(f"  ⚠ {sem_empresa} trabalhador(es) com UUID de empresa não localizado em bss.empresa")
    if sem_sindicato:
        print(f"  ⚠ {sem_sindicato} trabalhador(es) com UUID de sindicato não localizado em bss.sindicato")
    return prog.contador
