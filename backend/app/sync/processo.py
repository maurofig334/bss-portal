"""
Sincroniza processos de benefício: cases + cases_cstm → bss.processo_beneficio

Volume: ~18k registros. Tempo esperado: <30s.

Pré-requisitos: bss.empresa, bss.sindicato, bss.trabalhador, bss.tipo_beneficio
JÁ sincronizadas (precisamos das FKs).

Mapping principal:
  c.case_number              → numero_processo (sequencial legado, NÃO exibido)
  c.account_id (UUID)        → id_empresa (lookup)
  cc.contact_id_c (UUID)     → id_trabalhador (lookup via traba_trabalhadores.id)
  cc.sindi_sindicatos_id1_c  → id_sindicato (lookup)
  cc.tipodebeneficio_c       → id_tipo_beneficio (lookup catálogo por nome)
  cc.liberalidade_c          → liberalidade
  cc.causa_mortis_c          → causa_mortis
  cc.datadeevento_c          → data_evento
  cc.datadefinalizacao_c     → data_finalizacao
  cc.datavencimentocartao_c  → vencimento_cartao_em
  cc.rastreio_c              → codigo_rastreio_cartao
  cc.qtidadebebes_c          → qtd_bebes
  cc.dataobito_c             → data_obito
  cc.forma_pagamento_c       → forma_pagamento
  cc.situacaoacionamento_c   → situacao_acionamento
  cc.dados_revisados_c       → dados_revisados
  cc.chat_description_c      → chat_descricao
  c.status                   → status (mapeado pra catálogo bss.status_processo)
  + endereço/dados do beneficiário (de várias colunas cstm)
"""

from __future__ import annotations

import unicodedata

from ..database import get_mysql_connection, get_pg_connection
from ._base import Progresso, mysql_iter, pg_executemany, so_digitos, trim_or_none


SQL_LEGADO = """
    SELECT
        c.id                                AS uuid,
        c.case_number                       AS numero_processo,
        c.account_id                        AS uuid_empresa,
        c.status                            AS status_legado,
        c.date_entered                      AS criado_em_legado,
        cc.contact_id_c                     AS uuid_trabalhador,
        cc.sindi_sindicatos_id1_c           AS uuid_sindicato,
        cc.base_base_territorial_id_c       AS uuid_base_territorial,
        cc.tipodebeneficio_c                AS tipo_beneficio_nome,
        cc.liberalidade_c                   AS liberalidade,
        cc.rastreio_c                       AS codigo_rastreio_cartao,
        cc.causa_mortis_c                   AS causa_mortis,
        cc.chat_description_c               AS chat_descricao,
        cc.datadeevento_c                   AS data_evento,
        cc.datadefinalizacao_c              AS data_finalizacao,
        cc.datavencimentocartao_c           AS vencimento_cartao_em,
        cc.nomebeneficiario_c               AS beneficiario_nome,
        cc.cpfbeneficiario_c                AS beneficiario_cpf,
        cc.telbeneficiario_c                AS beneficiario_telefone,
        cc.nascimentobeneficiario_c         AS beneficiario_data_nasc,
        cc.grau_de_parentesco_c             AS beneficiario_grau_parentesco,
        cc.enderecodobenef_c                AS benef_logradouro,
        cc.enderecon_c                      AS benef_numero,
        cc.complemento_c                    AS benef_complemento,
        cc.bairro_c                         AS benef_bairro,
        cc.enderecodobenef_city_c           AS benef_cidade,
        cc.enderecodobenef_state_c          AS benef_uf,
        cc.enderecodobenef_postalcode_c     AS benef_cep,
        cc.qtidadebebes_c                   AS qtd_bebes,
        cc.dataobito_c                      AS data_obito,
        cc.situacaoacionamento_c            AS situacao_acionamento,
        cc.forma_pagamento_c                AS forma_pagamento,
        cc.dados_revisados_c                AS dados_revisados
    FROM cases c
    LEFT JOIN cases_cstm cc ON cc.id_c = c.id
    WHERE c.deleted = 0
"""


SQL_UPSERT = """
    INSERT INTO bss.processo_beneficio (
        id_legado_uuid, numero_processo,
        id_empresa, id_sindicato, id_trabalhador, id_tipo_beneficio,
        status, situacao_acionamento, causa_mortis, liberalidade,
        beneficiario_nome, beneficiario_cpf, beneficiario_telefone,
        beneficiario_data_nasc, beneficiario_grau_parentesco,
        beneficiario_endereco_logradouro, beneficiario_endereco_numero,
        beneficiario_endereco_complemento, beneficiario_endereco_bairro,
        beneficiario_endereco_cidade, beneficiario_endereco_uf,
        beneficiario_endereco_cep,
        qtd_bebes, data_obito, data_evento, data_finalizacao,
        forma_pagamento, codigo_rastreio_cartao, vencimento_cartao_em,
        chat_descricao, dados_revisados
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (id_legado_uuid) DO UPDATE
        SET numero_processo  = EXCLUDED.numero_processo,
            id_empresa       = EXCLUDED.id_empresa,
            id_sindicato     = EXCLUDED.id_sindicato,
            id_trabalhador   = EXCLUDED.id_trabalhador,
            id_tipo_beneficio= EXCLUDED.id_tipo_beneficio,
            status           = EXCLUDED.status,
            situacao_acionamento = EXCLUDED.situacao_acionamento,
            causa_mortis     = EXCLUDED.causa_mortis,
            liberalidade     = EXCLUDED.liberalidade,
            beneficiario_nome= EXCLUDED.beneficiario_nome,
            beneficiario_cpf = EXCLUDED.beneficiario_cpf,
            data_evento      = EXCLUDED.data_evento,
            data_finalizacao = EXCLUDED.data_finalizacao,
            atualizado_em    = NOW()
"""


def _slug(texto: str | None) -> str:
    """Normaliza string pra slug ASCII lowercase: 'Por Inadimplência' → 'por_inadimplencia'."""
    if not texto:
        return ""
    s = str(texto).strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.replace(" ", "_").replace("-", "_")


# Mapa: status do legado (lower-stripped) → codigo no catálogo bss.status_processo
STATUS_MAP = {
    "em analise":             "em_analise",      # mantém pelos 8 registros antigos
    "em aprovacao":           "em_aprovacao",
    "documentacao conforme":  "documentacao_conforme",
    "documentacao pendente":  "documentacao_pendente",
    "confirmacao de dados":   "confirmacao_dados",
    "irregularidade de dados":"irregularidade_dados",
    "contribuicao pendente":  "contribuicao_pendente",
    "aguardando informacao":  "aguardando_informacao",
    "autorizado financeiro":  "autorizado_financeiro",
    "cartao solicitado":      "cartao_solicitado",
    "cartao em transporte":   "cartao_em_transporte",
    "em andamento":           "em_andamento",
    "beneficio finalizado":   "beneficio_finalizado",
    "solicitacao cancelada":  "solicitacao_cancelada",
}


def _normalizar_status(v: str | None) -> str:
    """status legado → codigo do catálogo bss.status_processo. Default 'andamento_inicial'."""
    chave = _slug(v).replace("_", " ")
    return STATUS_MAP.get(chave, "andamento_inicial")


def _normalizar_liberalidade(v: str | None) -> str | None:
    """Regular / Por Inadimplência / Por Prazo → regular / por_inadimplencia / por_prazo."""
    if not v:
        return None
    s = _slug(v)
    if "regular" in s:
        return "regular"
    if "inadim" in s:
        return "por_inadimplencia"
    if "prazo" in s:
        return "por_prazo"
    return s[:20]


def _carregar_mappings(pg_conn, mysql_conn) -> tuple[dict, dict, dict, dict, dict]:
    """Pré-carrega UUID → ID pra empresa, sindicato, trabalhador, tipo_beneficio + base_territorial."""
    emp_map: dict[str, int] = {}
    sind_map: dict[str, int] = {}
    trab_map: dict[str, int] = {}
    bt_map: dict[str, int] = {}
    tipo_map: dict[str, int] = {}

    with pg_conn.cursor() as cur:
        cur.execute("SELECT id, id_legado_uuid FROM bss.empresa WHERE id_legado_uuid IS NOT NULL")
        for r in cur:
            emp_map[r["id_legado_uuid"]] = r["id"]
        cur.execute("SELECT id, id_legado_uuid FROM bss.sindicato WHERE id_legado_uuid IS NOT NULL")
        for r in cur:
            sind_map[r["id_legado_uuid"]] = r["id"]
        cur.execute("SELECT id, id_legado_uuid FROM bss.trabalhador WHERE id_legado_uuid IS NOT NULL")
        for r in cur:
            trab_map[r["id_legado_uuid"]] = r["id"]
        cur.execute("SELECT id, id_legado_uuid FROM bss.base_territorial WHERE id_legado_uuid IS NOT NULL")
        for r in cur:
            bt_map[r["id_legado_uuid"]] = r["id"]
        cur.execute("SELECT id, codigo FROM bss.tipo_beneficio")
        for r in cur:
            tipo_map[r["codigo"]] = r["id"]

    return emp_map, sind_map, trab_map, bt_map, tipo_map


def _converter(linha: dict, emp_map, sind_map, trab_map, bt_map, tipo_map) -> tuple:
    cep = so_digitos(linha.get("benef_cep"))
    cpf_benef = so_digitos(linha.get("beneficiario_cpf"))
    tipo_codigo = _slug(linha.get("tipo_beneficio_nome"))
    return (
        linha["uuid"],
        int(linha["numero_processo"]) if linha.get("numero_processo") is not None else None,
        emp_map.get(linha.get("uuid_empresa")),
        sind_map.get(linha.get("uuid_sindicato")),
        trab_map.get(linha.get("uuid_trabalhador")),
        tipo_map.get(tipo_codigo),
        _normalizar_status(linha.get("status_legado")),
        trim_or_none(linha.get("situacao_acionamento"), 50),
        trim_or_none(linha.get("causa_mortis"), 100),
        _normalizar_liberalidade(linha.get("liberalidade")),
        trim_or_none(linha.get("beneficiario_nome"), 255),
        cpf_benef[:11] if cpf_benef else None,
        trim_or_none(linha.get("beneficiario_telefone"), 20),
        linha.get("beneficiario_data_nasc"),
        trim_or_none(linha.get("beneficiario_grau_parentesco"), 50),
        trim_or_none(linha.get("benef_logradouro"), 150),
        str(linha.get("benef_numero"))[:20] if linha.get("benef_numero") is not None else None,
        trim_or_none(linha.get("benef_complemento"), 100),
        trim_or_none(linha.get("benef_bairro"), 100),
        trim_or_none(linha.get("benef_cidade"), 100),
        trim_or_none(linha.get("benef_uf"), 2),
        cep[:8] if cep else None,
        int(linha.get("qtd_bebes") or 0) if linha.get("qtd_bebes") is not None else None,
        linha.get("data_obito"),
        linha.get("data_evento"),
        linha.get("data_finalizacao"),
        trim_or_none(linha.get("forma_pagamento"), 30),
        trim_or_none(linha.get("codigo_rastreio_cartao"), 50),
        linha.get("vencimento_cartao_em"),
        linha.get("chat_descricao"),
        bool(linha.get("dados_revisados")) if linha.get("dados_revisados") else False,
    )


def sync(dry_run: bool = False, limite: int | None = None) -> int:
    print(f"\n=== Sync PROCESSO ({'dry-run' if dry_run else 'gravação'}) ===")

    print("  carregando mapeamentos UUID→ID...")
    with get_mysql_connection() as mysql_conn, get_pg_connection() as pg_conn:
        emp_map, sind_map, trab_map, bt_map, tipo_map = _carregar_mappings(pg_conn, mysql_conn)
    print(
        f"  ✓ {len(emp_map)} empresas, {len(sind_map)} sindicatos, "
        f"{len(trab_map)} trabalhadores, {len(tipo_map)} tipos de benefício"
    )

    sql = SQL_LEGADO + (f" LIMIT {int(limite)}" if limite else "")
    prog = Progresso(total=None, nome="processo")

    with get_mysql_connection() as mysql_conn:
        def converter_iter():
            for linha in mysql_iter(mysql_conn, sql, batch_size=500):
                if dry_run and prog.contador < 3:
                    print(f"  amostra: {linha}")
                prog.tick()
                yield _converter(linha, emp_map, sind_map, trab_map, bt_map, tipo_map)

        if dry_run:
            for _ in converter_iter():
                pass
        else:
            with get_pg_connection() as pg_conn:
                pg_executemany(pg_conn, SQL_UPSERT, converter_iter(), batch_size=500)

    prog.fim()
    return prog.contador
