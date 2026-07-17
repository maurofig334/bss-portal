"""
Acesso a bss.sindicato — listagem com agregados de parametros_boleto
e valor_beneficio_sindicato (Tipos de Benefício configurados).

Sem VIEW por enquanto — a query JOIN fica aqui no repo. Quando estabilizar
a gente promove pra bss.v_sindicato.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from .database import get_pg_connection


ORDER_BY_OK = {
    "razao_social", "cnpj", "categoria", "federacao",
    "qtd_trabalhadores_ativos", "qtd_trabalhadores_inativos",
    "atualizado_em",
}


# Mês corrente → coluna de vencimento correspondente em parametros_boleto.
_MES_PARA_COL = {
    1: "vencimento_jan", 2: "vencimento_fev",  3: "vencimento_mar",
    4: "vencimento_abr", 5: "vencimento_mai",  6: "vencimento_jun",
    7: "vencimento_jul", 8: "vencimento_ago",  9: "vencimento_set",
    10: "vencimento_out", 11: "vencimento_nov", 12: "vencimento_dez",
}


def _so_digitos(s: str | None) -> str:
    return re.sub(r"\D+", "", s or "")


def listar(
    busca: str | None = None,
    uf: str | None = None,
    categoria: str | None = None,
    em_atendimento: bool | None = None,
    ids: list[int] | None = None,
    pagina: int = 1,
    por_pagina: int = 50,
    ordem: str = "razao_social",
    desc: bool = False,
) -> dict[str, Any]:
    """
    Lista sindicatos paginados.

    `ids` dá escopo ao perfil 'sindicato' e PRECISA ser aplicado no SQL — o
    router filtrava o resultado depois de paginar, mesmo defeito que o
    empresa_repo tinha (ver a docstring de lá pro estrago que isso faz na
    contagem de páginas).
    """
    pagina = max(1, int(pagina))
    por_pagina = min(200, max(10, int(por_pagina)))
    if ordem not in ORDER_BY_OK:
        ordem = "razao_social"
    direcao = "DESC" if desc else "ASC"

    col_venc = _MES_PARA_COL[date.today().month]

    where = ["s.ativo = TRUE"]
    params: dict[str, Any] = {}

    if busca:
        digitos = _so_digitos(busca)
        if len(digitos) >= 6:
            where.append("s.cnpj LIKE %(cnpj)s")
            params["cnpj"] = digitos + "%"
        else:
            where.append(
                "(s.razao_social ILIKE %(s)s OR s.nome_fantasia ILIKE %(s)s)"
            )
            params["s"] = f"%{busca}%"

    if uf:
        where.append("s.uf_abrangencia = %(uf)s")
        params["uf"] = uf
    if categoria:
        where.append("s.categoria = %(cat)s")
        params["cat"] = categoria
    if em_atendimento is not None:
        where.append("s.em_atendimento = %(ea)s")
        params["ea"] = bool(em_atendimento)

    if ids is not None:
        where.append("s.id = ANY(%(ids)s)")
        params["ids"] = list(ids)

    where_sql = " AND ".join(where)

    sql_total = f"SELECT COUNT(*) AS total FROM bss.sindicato s WHERE {where_sql}"
    sql_lista = f"""
        SELECT
            s.id,
            s.razao_social,
            s.nome_fantasia,
            s.cnpj,
            s.federacao,
            s.categoria,
            s.uf_abrangencia,
            s.em_atendimento,
            s.qtd_trabalhadores_ativos,
            s.qtd_trabalhadores_inativos,
            s.atualizado_em,
            -- Tipo de sindicato: vem do legado (s.tipo_sindicato). Fallback no derivado
            -- (LIKE FEMACO na federação) pra sindicatos onde o sync ainda não populou.
            COALESCE(
                NULLIF(TRIM(s.tipo_sindicato), ''),
                CASE WHEN UPPER(TRIM(COALESCE(s.federacao, ''))) LIKE '%%FEMACO%%'
                     THEN 'FEMACO' ELSE 'NAO FEMACO' END
            ) AS tipo_sindicato,
            -- Demais campos descobertos no épico #17 (2026-05-11):
            s.telefone, s.outro_telefone, s.fax,
            s.email, s.contato_principal, s.patronal_empresa,
            s.website, s.descricao,
            s.endereco_logradouro, s.endereco_cidade, s.endereco_uf,
            s.endereco_cep, s.endereco_pais,
            -- Vencimento do mês corrente (mantido pra usos futuros — detalhe):
            pb.{col_venc} AS dia_vencimento_mes,
            pb.tipo       AS tipo_parametro,
            (pb.id IS NOT NULL) AS tem_parametro,
            pb.nome       AS parametro_nome,
            -- Tarifa do titular + tarifa dependente (núcleo da coluna "Parâmetro" da grid):
            pb.tarifa_titular,
            pb.tarifa_dependente,
            pb.aceita_dependentes,
            -- Quantos tipos de benefício o sindicato oferece e soma das indenizações:
            COALESCE(vb.qtd_tipos_beneficio, 0)   AS qtd_tipos_beneficio,
            COALESCE(vb.valor_total_indenizacoes, 0) AS valor_total_indenizacoes
        FROM bss.sindicato s
        LEFT JOIN LATERAL (
            SELECT id, {col_venc}, tipo, nome, tarifa_titular,
                   tarifa_dependente, aceita_dependentes
              FROM bss.parametros_boleto
             WHERE id_sindicato = s.id AND ativo = TRUE
             ORDER BY id DESC
             LIMIT 1
        ) pb ON TRUE
        LEFT JOIN (
            SELECT id_sindicato,
                   COUNT(*)              AS qtd_tipos_beneficio,
                   SUM(valor_total)      AS valor_total_indenizacoes
              FROM bss.valor_beneficio_sindicato
             GROUP BY id_sindicato
        ) vb ON vb.id_sindicato = s.id
        WHERE {where_sql}
        ORDER BY s.{ordem} {direcao} NULLS LAST
        LIMIT %(limit)s OFFSET %(offset)s
    """
    params["limit"] = por_pagina
    params["offset"] = (pagina - 1) * por_pagina

    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_total, params)
            total = cur.fetchone()["total"]
            cur.execute(sql_lista, params)
            linhas = cur.fetchall()

    paginas = (total + por_pagina - 1) // por_pagina if total else 0
    return {
        "linhas": linhas,
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "paginas": paginas,
    }


def buscar_por_id(id_sindicato: int) -> dict[str, object] | None:
    sql = "SELECT * FROM bss.sindicato WHERE id = %s"
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (id_sindicato,))
            return cur.fetchone()


def buscar_detalhe(id_sindicato: int) -> dict[str, Any] | None:
    """
    Detalhe completo do sindicato + JOIN com parametros_boleto + agregado
    de valor_beneficio_sindicato — pra tela de detalhe.
    """
    sql = """
        SELECT s.*,
               -- Tipo de sindicato (real do legado, fallback no derivado):
               COALESCE(
                   NULLIF(TRIM(s.tipo_sindicato), ''),
                   CASE WHEN UPPER(TRIM(COALESCE(s.federacao, ''))) LIKE '%%FEMACO%%'
                        THEN 'FEMACO' ELSE 'NAO FEMACO' END
               ) AS tipo_sindicato_resolvido,
               pb.id              AS id_parametro,
               pb.nome            AS parametro_nome,
               pb.tarifa_titular  AS parametro_tarifa_titular,
               pb.tarifa_dependente AS parametro_tarifa_dependente,
               pb.aceita_dependentes AS parametro_aceita_dependentes,
               COALESCE(vb.qtd_tipos_beneficio, 0)        AS qtd_tipos_beneficio,
               COALESCE(vb.valor_total_indenizacoes, 0)   AS valor_total_indenizacoes
          FROM bss.sindicato s
          LEFT JOIN LATERAL (
              SELECT id, nome, tarifa_titular, tarifa_dependente, aceita_dependentes
                FROM bss.parametros_boleto
               WHERE id_sindicato = s.id AND ativo = TRUE
               ORDER BY id DESC LIMIT 1
          ) pb ON TRUE
          LEFT JOIN (
              SELECT id_sindicato,
                     COUNT(*)         AS qtd_tipos_beneficio,
                     SUM(valor_total) AS valor_total_indenizacoes
                FROM bss.valor_beneficio_sindicato
               GROUP BY id_sindicato
          ) vb ON vb.id_sindicato = s.id
         WHERE s.id = %s
    """
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (id_sindicato,))
            return cur.fetchone()
