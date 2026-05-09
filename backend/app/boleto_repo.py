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
    id_sindicato: int | None = None,
    incluir_cancelados: bool = False,
    pagina: int = 1,
    por_pagina: int = 50,
    ordem: str = "mes_referencia",
    desc: bool = True,
) -> dict[str, Any]:
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
