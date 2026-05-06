"""
Acesso a bss.processo_beneficio (via VIEW v_processo).
"""

from __future__ import annotations

import re
from typing import Any

from .database import get_pg_connection


ORDER_BY_OK = {
    "criado_em", "data_evento", "data_finalizacao",
    "status", "tipo_beneficio", "empresa", "trabalhador_nome",
    "ultima_atualizacao_portal_em",
}


def _so_digitos(s: str | None) -> str:
    return re.sub(r"\D+", "", s or "")


def listar(
    busca: str | None = None,
    status: str | None = None,
    status_categoria: str | None = None,
    tipo: str | None = None,
    id_empresa: int | None = None,
    id_sindicato: int | None = None,
    pagina: int = 1,
    por_pagina: int = 50,
    ordem: str = "criado_em",
    desc: bool = True,
) -> dict[str, Any]:
    pagina = max(1, int(pagina))
    por_pagina = min(200, max(10, int(por_pagina)))
    if ordem not in ORDER_BY_OK:
        ordem = "criado_em"
    direcao = "DESC" if desc else "ASC"

    where = ["1=1"]
    params: dict[str, Any] = {}

    if busca:
        digitos = _so_digitos(busca)
        if len(digitos) >= 6:
            where.append("(v.trabalhador_cpf LIKE %(cpf)s OR v.beneficiario_cpf LIKE %(cpf)s)")
            params["cpf"] = digitos + "%"
        else:
            where.append("(v.trabalhador_nome ILIKE %(s)s OR v.beneficiario_nome ILIKE %(s)s OR v.empresa ILIKE %(s)s OR v.protocolo = %(busca_raw)s)")
            params["s"] = f"%{busca}%"
            params["busca_raw"] = busca

    if status:
        where.append("v.status = %(status)s")
        params["status"] = status
    if status_categoria:
        where.append("v.status_categoria = %(cat)s")
        params["cat"] = status_categoria
    if tipo:
        where.append("v.tipo_beneficio_codigo = %(tipo)s")
        params["tipo"] = tipo
    if id_empresa:
        where.append("v.id_empresa = %(id_empresa)s")
        params["id_empresa"] = id_empresa
    if id_sindicato:
        where.append("v.id_sindicato = %(id_sindicato)s")
        params["id_sindicato"] = id_sindicato

    where_sql = " AND ".join(where)
    sql_total = f"SELECT COUNT(*) AS total FROM bss.v_processo v WHERE {where_sql}"
    sql_lista = f"""
        SELECT
            v.id, v.numero_processo, v.protocolo,
            v.status, v.status_nome, v.status_categoria, v.status_cor,
            v.tipo_beneficio, v.tipo_beneficio_codigo,
            v.empresa, v.empresa_cnpj, v.sindicato,
            v.trabalhador_cpf, v.trabalhador_nome,
            v.beneficiario_nome, v.liberalidade,
            v.data_evento, v.data_finalizacao, v.criado_em,
            v.ultima_atualizacao_portal_em
        FROM bss.v_processo v
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


def buscar_por_id(id_processo: int) -> dict[str, Any] | None:
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM bss.v_processo WHERE id = %s", (id_processo,))
            processo = cur.fetchone()
            if not processo:
                return None
            cur.execute(
                "SELECT id, titulo, corpo, interno, criado_em "
                "FROM bss.processo_mensagem WHERE id_processo = %s "
                "ORDER BY criado_em ASC",
                (id_processo,),
            )
            processo["mensagens"] = cur.fetchall()
    return processo
