"""
Acesso a bss.empresa (via VIEW v_empresa).
"""

from __future__ import annotations

import re
from typing import Any

from .database import get_pg_connection


ORDER_BY_OK = {
    "razao_social", "cnpj", "cidade", "uf", "status",
    "adimplencia", "regularidade",
    "qtd_trabalhadores_ativos", "ultimo_boleto_em", "atualizado_em",
}


def _so_digitos(s: str | None) -> str:
    return re.sub(r"\D+", "", s or "")


def listar(
    busca: str | None = None,
    status: str | None = None,
    adimplencia: str | None = None,
    regularidade: str | None = None,
    uf: str | None = None,
    pagina: int = 1,
    por_pagina: int = 50,
    ordem: str = "razao_social",
    desc: bool = False,
) -> dict[str, Any]:
    pagina = max(1, int(pagina))
    por_pagina = min(200, max(10, int(por_pagina)))
    if ordem not in ORDER_BY_OK:
        ordem = "razao_social"
    direcao = "DESC" if desc else "ASC"

    where = ["1=1"]
    params: dict[str, Any] = {}

    if busca:
        digitos = _so_digitos(busca)
        if len(digitos) >= 6:
            where.append("v.cnpj LIKE %(cnpj)s")
            params["cnpj"] = digitos + "%"
        else:
            where.append("(v.razao_social ILIKE %(s)s OR v.nome_fantasia ILIKE %(s)s)")
            params["s"] = f"%{busca}%"

    if status:
        where.append("v.status = %(status)s")
        params["status"] = status
    if adimplencia:
        where.append("v.adimplencia = %(adim)s")
        params["adim"] = adimplencia
    if regularidade:
        where.append("v.regularidade = %(reg)s")
        params["reg"] = regularidade
    if uf:
        where.append("v.uf = %(uf)s")
        params["uf"] = uf

    where_sql = " AND ".join(where)
    sql_total = f"SELECT COUNT(*) AS total FROM bss.v_empresa v WHERE {where_sql}"
    sql_lista = f"""
        SELECT
            v.id, v.cnpj, v.razao_social, v.cidade, v.uf,
            v.status, v.adimplencia, v.regularidade,
            v.qtd_trabalhadores_ativos, v.qtd_dependentes_ativos,
            v.ultimo_boleto_em
        FROM bss.v_empresa v
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


def buscar_por_id(id_empresa: int) -> dict[str, Any] | None:
    sql = "SELECT * FROM bss.v_empresa WHERE id = %s"
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (id_empresa,))
            return cur.fetchone()


def buscar_detalhe(id_empresa: int) -> dict[str, Any] | None:
    """
    Detalhe completo da empresa pra tela de detalhe.
    Lê a tabela direto (não a view) por causa do endereço completo
    (logradouro/numero/bairro/cep) que v_empresa não expõe.
    """
    sql = "SELECT * FROM bss.empresa WHERE id = %s"
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (id_empresa,))
            return cur.fetchone()


def listar_usuarios(id_empresa: int) -> list[dict[str, Any]]:
    """Usuários com acesso à empresa (via bss.usuario_empresa)."""
    sql = """
        SELECT u.id, u.nome, u.email, u.perfil,
               u.ativo, ue.ativo AS acesso_ativo
          FROM bss.usuario_empresa ue
          JOIN bss_users u ON u.id = ue.id_usuario
         WHERE ue.id_empresa = %s
         ORDER BY u.nome
    """
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (id_empresa,))
            return list(cur.fetchall())
