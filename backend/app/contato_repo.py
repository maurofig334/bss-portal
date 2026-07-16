"""
Acesso aos CONTATOS — os usuários externos que administram empresas.

O "Contato" do legado É o bss_users com perfil='empresa'; não é entidade
separada (ver docs/AUTOCADASTRO.md). Cada um administra N CNPJs via
bss.usuario_empresa — relação N:N de verdade, diferente do legado, onde o
SuiteCRM só aceita 1 empresa por contato e a saída foi duplicar o contato.
"""

from __future__ import annotations

import re
from typing import Any

from .database import get_pg_connection


ORDER_BY_OK = {
    "nome", "email", "criado_em", "ultimo_login", "qtd_empresas", "ativo",
}


def _so_digitos(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def listar(
    busca: str | None = None,
    ativo: bool | None = None,
    tipo_cadastro: str | None = None,
    id_empresa: int | None = None,
    pagina: int = 1,
    por_pagina: int = 50,
    ordem: str = "nome",
    desc: bool = False,
) -> dict[str, Any]:
    """
    Lista contatos (perfil='empresa') com a contagem de empresas que cada um
    administra. `busca` casa nome, e-mail ou CNPJ de empresa administrada.
    """
    where = ["u.perfil = 'empresa'"]
    params: dict[str, Any] = {}

    if busca:
        digitos = _so_digitos(busca)
        if len(digitos) == 14:
            # Busca por CNPJ: acha quem administra aquela empresa
            where.append("""EXISTS (
                SELECT 1 FROM bss.usuario_empresa ue
                  JOIN bss.empresa e ON e.id = ue.id_empresa
                 WHERE ue.id_usuario = u.id AND e.cnpj = %(cnpj)s
            )""")
            params["cnpj"] = digitos
        else:
            where.append("(u.nome ILIKE %(busca)s OR u.email ILIKE %(busca)s)")
            params["busca"] = f"%{busca}%"

    if ativo is not None:
        where.append("u.ativo = %(ativo)s")
        params["ativo"] = ativo

    if tipo_cadastro:
        where.append("u.tipo_cadastro = %(tipo_cadastro)s")
        params["tipo_cadastro"] = tipo_cadastro

    if id_empresa:
        where.append("""EXISTS (
            SELECT 1 FROM bss.usuario_empresa ue
             WHERE ue.id_usuario = u.id AND ue.id_empresa = %(id_empresa)s
        )""")
        params["id_empresa"] = id_empresa

    where_sql = " AND ".join(where)
    ordem_sql = ordem if ordem in ORDER_BY_OK else "nome"
    direcao = "DESC" if desc else "ASC"

    sql_total = f"SELECT COUNT(*) AS total FROM bss_users u WHERE {where_sql}"
    sql_lista = f"""
        SELECT u.id, u.nome, u.email, u.telefone, u.ativo,
               u.tipo_cadastro, u.criado_em, u.ultimo_login,
               u.preferencias_notificacao,
               (SELECT COUNT(*) FROM bss.usuario_empresa ue
                 WHERE ue.id_usuario = u.id AND ue.ativo) AS qtd_empresas
          FROM bss_users u
         WHERE {where_sql}
         ORDER BY {ordem_sql} {direcao} NULLS LAST
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
    return {"linhas": linhas, "total": total, "pagina": pagina,
            "por_pagina": por_pagina, "paginas": paginas}


def buscar_detalhe(id_contato: int) -> dict[str, Any] | None:
    """Cabeçalho do contato: só o que ele É. As empresas vão na aba."""
    sql = """
        SELECT u.id, u.nome, u.email, u.telefone, u.ativo, u.perfil,
               u.tipo_cadastro, u.criado_em, u.ultimo_login,
               u.preferencias_notificacao, u.id_legado_uuid,
               (SELECT COUNT(*) FROM bss.usuario_empresa ue
                 WHERE ue.id_usuario = u.id AND ue.ativo) AS qtd_empresas
          FROM bss_users u
         WHERE u.id = %s AND u.perfil = 'empresa'
    """
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (id_contato,))
            return cur.fetchone()


def listar_empresas(id_contato: int) -> list[dict[str, Any]]:
    """
    As empresas que o contato administra — o coração do N:N.

    É esta lista que o legado NÃO consegue mostrar: lá o contato tem um campo
    "Nome da Empresa" com UM valor, e quem administra 54 CNPJs aparece com 1.
    """
    sql = """
        SELECT e.id, e.cnpj, e.razao_social, e.status, e.adimplencia,
               e.regularidade, e.cidade, e.uf,
               e.qtd_trabalhadores_ativos,
               ue.ativo        AS acesso_ativo,
               ue.criado_em    AS vinculado_em
          FROM bss.usuario_empresa ue
          JOIN bss.empresa e ON e.id = ue.id_empresa
         WHERE ue.id_usuario = %s
         ORDER BY e.razao_social
    """
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (id_contato,))
            return list(cur.fetchall())


def listar_solicitacoes(id_contato: int) -> list[dict[str, Any]]:
    """Histórico de pedidos de acesso do contato (fila do autocadastro)."""
    sql = """
        SELECT s.id, s.criado_em, s.origem, s.status, s.empresa_preexistente,
               s.motivo_reprovacao, s.avaliado_em, s.ip_origem,
               e.cnpj, e.razao_social AS empresa,
               a.nome AS avaliado_por
          FROM bss.solicitacao_acesso s
          JOIN bss.empresa e ON e.id = s.id_empresa
          LEFT JOIN bss_users a ON a.id = s.avaliado_por_id
         WHERE s.id_usuario = %s
         ORDER BY s.criado_em DESC
    """
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (id_contato,))
            return list(cur.fetchall())


def contar_pendentes() -> int:
    """O sininho: quantas solicitações aguardam análise."""
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM bss.v_solicitacao_pendente")
            return cur.fetchone()["n"]


def listar_pendentes() -> list[dict[str, Any]]:
    """A fila que o analista aprova. A view já traz o contexto pra decidir."""
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM bss.v_solicitacao_pendente ORDER BY criado_em"
            )
            return list(cur.fetchall())
