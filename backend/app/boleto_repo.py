"""
Acesso a bss.boleto (via VIEW v_boleto).
"""

from __future__ import annotations

from typing import Any

from .database import get_pg_connection


ORDER_BY_OK = {
    "mes_referencia", "data_vencimento", "data_emissao", "data_pagamento",
    "valor_total", "empresa", "sindicato", "status", "numero_boleto",
}


def listar(
    busca: str | None = None,
    status: str | None = None,
    mes_referencia: str | None = None,   # YYYY-MM
    id_empresa: int | None = None,
    ids_empresa: list[int] | None = None,
    id_sindicato: int | None = None,
    incluir_cancelados: bool = False,
    pagina: int = 1,
    por_pagina: int = 50,
    ordem: str = "mes_referencia",
    desc: bool = True,
) -> dict[str, Any]:
    """
    `id_empresa`  → filtro de UMA empresa (escolha na tela).
    `ids_empresa` → ESCOPO: o conjunto que o usuário pode ver (vem do JWT).

    Os dois convivem: o filtro estreita dentro do escopo, nunca o alarga.
    Antes o router preenchia id_empresa com `usuario.empresas[0]` quando a tela
    não mandava nada — e um gestor de 11 CNPJs via os boletos de um só.
    """
    pagina = max(1, int(pagina))
    por_pagina = min(200, max(10, int(por_pagina)))
    if ordem not in ORDER_BY_OK:
        ordem = "mes_referencia"
    direcao = "DESC" if desc else "ASC"

    where = ["1=1"]
    params: dict[str, Any] = {}

    # Esconde os 162k boletos legados que ficaram com id_empresa=NULL na migração
    # (campo nunca foi populado). Sem empresa não dá pra fazer NADA com o boleto
    # — não dá pra emitir lista de trabalhadores, vincular dependentes, gerar PDF
    # com cabeçalho correto. Mantemos no banco pro caso de reconciliação futura.
    where.append("v.id_empresa IS NOT NULL")

    if busca:
        where.append("(v.empresa ILIKE %(s)s OR v.empresa_cnpj LIKE %(cnpj)s OR v.nosso_numero LIKE %(s)s)")
        params["s"] = f"%{busca}%"
        params["cnpj"] = busca + "%"

    if status:
        where.append("v.status = %(status)s")
        params["status"] = status
    elif not incluir_cancelados:
        # Default: esconde cancelados da listagem geral.
        # Quando o user passa status='cancelado' explicitamente, mostra (filtro acima).
        where.append("v.status <> 'cancelado'")
    if mes_referencia:
        # YYYY-MM → primeiro dia do mês
        where.append("v.mes_referencia = (%(mes)s || '-01')::date")
        params["mes"] = mes_referencia
    if id_empresa:
        where.append("v.id_empresa = %(id_empresa)s")
        params["id_empresa"] = id_empresa
    if ids_empresa is not None:
        where.append("v.id_empresa = ANY(%(ids_empresa)s)")
        params["ids_empresa"] = list(ids_empresa)
    if id_sindicato:
        where.append("v.id_sindicato = %(id_sindicato)s")
        params["id_sindicato"] = id_sindicato

    where_sql = " AND ".join(where)
    sql_total = f"SELECT COUNT(*) AS total FROM bss.v_boleto v WHERE {where_sql}"
    sql_lista = f"""
        SELECT
            v.id, v.numero_boleto, v.empresa, v.empresa_cnpj, v.sindicato,
            v.mes_referencia, v.qtd_trabalhadores, v.valor_total,
            v.banco, v.nosso_numero, v.status, v.tipo,
            v.data_vencimento, v.data_pagamento
        FROM bss.v_boleto v
        WHERE {where_sql}
        ORDER BY v.{ordem} {direcao} NULLS LAST
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
    return {"linhas": linhas, "total": total, "pagina": pagina, "por_pagina": por_pagina, "paginas": paginas}


def buscar_por_id(id_boleto: int) -> dict[str, Any] | None:
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM bss.v_boleto WHERE id = %s", (id_boleto,))
            return cur.fetchone()


def buscar_detalhe(id_boleto: int) -> dict[str, Any] | None:
    """
    Retorna boleto + parametros_boleto.nome + lista de trabalhadores
    (boleto_item × bss.trabalhador) — pra tela de detalhe espelhar o legado.
    """
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    b.id, b.numero_boleto, b.nosso_numero, b.id_legado_uuid,
                    b.id_empresa, b.id_sindicato, b.id_lista_mensal,
                    b.mes_referencia, b.qtd_trabalhadores, b.qtd_dependentes,
                    b.valor_total, b.banco, b.linha_digitavel, b.codigo_barras,
                    b.link_pdf, b.status, b.tipo, b.data_emissao, b.data_vencimento,
                    b.data_pagamento, b.criado_em, b.atualizado_em,
                    b.id_boleto_substituido, b.motivo_cancelamento,
                    e.razao_social    AS empresa,
                    e.cnpj            AS empresa_cnpj,
                    s.razao_social    AS sindicato,
                    p.nome            AS parametro_nome,
                    p.tarifa_titular, p.tarifa_dependente,
                    -- Boleto substituto (se este foi reemitido):
                    (SELECT b2.nosso_numero
                       FROM bss.boleto b2
                      WHERE b2.id_boleto_substituido = b.id
                      ORDER BY b2.id DESC LIMIT 1) AS nosso_numero_substituto,
                    (SELECT b2.id
                       FROM bss.boleto b2
                      WHERE b2.id_boleto_substituido = b.id
                      ORDER BY b2.id DESC LIMIT 1) AS id_substituto,
                    -- Boleto de origem (se este é uma reemissão):
                    (SELECT b3.nosso_numero FROM bss.boleto b3
                      WHERE b3.id = b.id_boleto_substituido) AS nosso_numero_origem,
                    (SELECT b3.mes_referencia FROM bss.boleto b3
                      WHERE b3.id = b.id_boleto_substituido) AS mes_origem
                  FROM bss.boleto b
                  LEFT JOIN bss.empresa  e ON e.id = b.id_empresa
                  LEFT JOIN bss.sindicato s ON s.id = b.id_sindicato
                  LEFT JOIN bss.parametros_boleto p
                         ON p.id_sindicato = s.id AND p.ativo
                 WHERE b.id = %s
                """,
                (id_boleto,),
            )
            boleto = cur.fetchone()
            if not boleto:
                return None

            # Agrega por trabalhador — alguns boletos do legado tem múltiplas
            # linhas em boleto_item pra mesmo trabalhador (provável bug da
            # migração legada). qtd_lancamentos > 1 sinaliza a duplicação.
            cur.execute(
                """
                SELECT
                    t.id             AS id_trabalhador,
                    t.cpf,
                    t.nome_completo,
                    t.titularidade,
                    t.situacao,
                    t.data_admissao,
                    bool_or(bi.eh_dependente)      AS eh_dependente,
                    SUM(bi.taxa_aplicada)          AS taxa_aplicada,
                    COUNT(*)                       AS qtd_lancamentos
                  FROM bss.boleto_item bi
                  JOIN bss.trabalhador t ON t.id = bi.id_trabalhador
                 WHERE bi.id_boleto = %s
                 GROUP BY t.id, t.cpf, t.nome_completo, t.titularidade,
                          t.situacao, t.data_admissao
                 ORDER BY bool_or(bi.eh_dependente), t.nome_completo
                """,
                (id_boleto,),
            )
            boleto["itens"] = cur.fetchall()
            return boleto
