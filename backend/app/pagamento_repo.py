"""
Acesso ao contas a pagar (bss.pagamento via v_pagamento).

Só a equipe interna usa — o escopo por empresa NÃO se aplica aqui (é operação
financeira da BSS, não do cliente). O router garante o perfil.
"""

from __future__ import annotations

import re
from typing import Any

from .database import get_pg_connection


ORDER_BY_OK = {
    "data_prevista", "valor", "status", "empresa", "protocolo",
    "tipo_beneficio", "beneficiario_nome",
}


def _so_digitos(s: str | None) -> str:
    return re.sub(r"\D+", "", s or "")


# Colunas compartilhadas entre listagem e export — uma fonte só (mesma lição
# do export de trabalhadores: filtro/colunas duplicados divergem).
COLUNAS = """
    v.id, v.protocolo, v.parcela, v.valor, v.status, v.forma_pagamento,
    v.data_referencia, v.data_pagamento,
    v.empresa, v.empresa_cnpj, v.sindicato, v.tipo_beneficio,
    v.trabalhador, v.beneficiario_nome, v.beneficiario_cpf, v.id_processo
"""


def _montar_where(busca, status, forma, empresa_cnpj,
                  data_de, data_ate) -> tuple[str, dict]:
    where = ["1=1"]
    params: dict[str, Any] = {}

    if busca:
        digitos = _so_digitos(busca)
        if len(digitos) == 14:
            where.append("v.empresa_cnpj = %(cnpj)s")
            params["cnpj"] = digitos
        elif len(digitos) == 11:
            where.append("(v.trabalhador_cpf = %(cpf)s OR v.beneficiario_cpf = %(cpf)s)")
            params["cpf"] = digitos
        else:
            where.append("(v.empresa ILIKE %(s)s OR v.trabalhador ILIKE %(s)s "
                         "OR v.beneficiario_nome ILIKE %(s)s OR v.protocolo = %(raw)s)")
            params["s"] = f"%{busca}%"
            params["raw"] = busca

    if status:
        where.append("v.status = %(status)s")
        params["status"] = status
    if forma:
        where.append("v.forma_pagamento = %(forma)s")
        params["forma"] = forma
    if empresa_cnpj:
        where.append("v.empresa_cnpj = %(ecnpj)s")
        params["ecnpj"] = _so_digitos(empresa_cnpj)
    if data_de:
        where.append("v.data_referencia >= %(data_de)s")
        params["data_de"] = data_de
    if data_ate:
        where.append("v.data_referencia <= %(data_ate)s")
        params["data_ate"] = data_ate

    return " AND ".join(where), params


def listar(busca=None, status=None, forma=None, empresa_cnpj=None,
           data_de=None, data_ate=None, pagina=1, por_pagina=50,
           ordem="data_prevista", desc=True) -> dict[str, Any]:
    pagina = max(1, int(pagina))
    por_pagina = min(200, max(10, int(por_pagina)))
    if ordem not in ORDER_BY_OK:
        ordem = "data_prevista"
    # data_prevista é a coluna real; na view chama data_referencia também.
    col = "data_referencia" if ordem == "data_prevista" else ordem
    direcao = "DESC" if desc else "ASC"

    where_sql, params = _montar_where(busca, status, forma, empresa_cnpj,
                                      data_de, data_ate)

    # Total + soma dos valores no mesmo filtro — o financeiro quer saber
    # "quanto tem pendente aqui", não só quantas linhas.
    sql_agg = f"""
        SELECT COUNT(*) AS total,
               COALESCE(SUM(v.valor), 0) AS soma_valor
          FROM bss.v_pagamento v WHERE {where_sql}
    """
    sql_lista = f"""
        SELECT {COLUNAS}
          FROM bss.v_pagamento v
         WHERE {where_sql}
         ORDER BY v.{col} {direcao} NULLS LAST, v.protocolo, v.parcela
         LIMIT %(limit)s OFFSET %(offset)s
    """
    params["limit"] = por_pagina
    params["offset"] = (pagina - 1) * por_pagina

    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(sql_agg, params)
        agg = cur.fetchone()
        cur.execute(sql_lista, params)
        linhas = cur.fetchall()

    total = agg["total"]
    paginas = (total + por_pagina - 1) // por_pagina if total else 0
    return {
        "linhas": linhas, "total": total, "soma_valor": float(agg["soma_valor"]),
        "pagina": pagina, "por_pagina": por_pagina, "paginas": paginas,
    }


def listar_tudo(busca=None, status=None, forma=None, empresa_cnpj=None,
                data_de=None, data_ate=None, ordem="data_prevista",
                desc=True) -> list[dict[str, Any]]:
    """Sem paginação, pro export. Mesmo _montar_where da listagem."""
    if ordem not in ORDER_BY_OK:
        ordem = "data_prevista"
    col = "data_referencia" if ordem == "data_prevista" else ordem
    direcao = "DESC" if desc else "ASC"
    where_sql, params = _montar_where(busca, status, forma, empresa_cnpj,
                                      data_de, data_ate)
    sql = f"""
        SELECT {COLUNAS}
          FROM bss.v_pagamento v
         WHERE {where_sql}
         ORDER BY v.{col} {direcao} NULLS LAST, v.protocolo, v.parcela
         LIMIT 100000
    """
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def liquidar(ids: list[int], data_pagamento, id_usuario: int) -> int:
    """
    Marca parcelas como pagas. Só muda quem está 'pendente' — não "despaga"
    nem mexe em cancelado. Retorna quantas foram efetivamente liquidadas.

    Escreve data_pagamento (o sinal real de pagamento — status_c do legado era
    inútil). Como o SuiteCRM nunca deu baixa confiável, o BSS passa a ser a
    fonte da verdade disso; não há conflito com a sync (o sync só preenche
    data_pagamento se o legado tiver, o que quase nunca tem).
    """
    if not ids:
        return 0
    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE bss.pagamento
               SET status = 'pago', data_pagamento = %s, atualizado_em = NOW()
             WHERE id = ANY(%s) AND status = 'pendente'
            """,
            (data_pagamento, ids),
        )
        n = cur.rowcount
        conn.commit()
    return n
