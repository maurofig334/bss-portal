"""
Acesso a bss.trabalhador (via VIEW v_trabalhador).

Função principal: listar() com paginação + filtros + busca textual.
"""

from __future__ import annotations

import re
from typing import Any

from .database import get_pg_connection


# Whitelist de colunas pra ORDER BY (segurança contra SQL injection)
ORDER_BY_OK = {
    "nome_completo", "cpf", "empresa", "sindicato",
    "situacao", "ultimo_pagamento_em", "atualizado_em",
    "trab_uf",
}


def _so_digitos(s: str | None) -> str:
    """Mantém só dígitos. Pra normalizar busca por CPF."""
    if not s:
        return ""
    return re.sub(r"\D+", "", s)


def listar(
    busca: str | None = None,
    situacao: str | None = None,
    id_empresa: int | None = None,
    id_sindicato: int | None = None,
    uf: str | None = None,
    pagina: int = 1,
    por_pagina: int = 50,
    ordem: str = "nome_completo",
    desc: bool = False,
) -> dict[str, Any]:
    """
    Lista trabalhadores com paginação.
    Retorna {linhas: [...], total: N, pagina, por_pagina, paginas}.
    """
    pagina = max(1, int(pagina))
    por_pagina = min(200, max(10, int(por_pagina)))
    if ordem not in ORDER_BY_OK:
        ordem = "nome_completo"
    direcao = "DESC" if desc else "ASC"

    # Monta WHERE dinâmico
    where = ["1=1"]
    params: dict[str, Any] = {}

    if busca:
        # Busca:
        #   - texto livre  → nome do trabalhador (ILIKE %X%)
        #   - 14 dígitos   → CNPJ EXATO da empresa atual (filiais = CNPJs distintos)
        #   - 11 dígitos   → CPF EXATO do trabalhador
        #   - 6-10 dígitos → prefixo de CPF (busca enquanto digita)
        digitos = _so_digitos(busca)
        if len(digitos) == 14:
            where.append("v.empresa_cnpj = %(cnpj)s")
            params["cnpj"] = digitos
        elif len(digitos) == 11:
            where.append("v.cpf = %(cpf)s")
            params["cpf"] = digitos
        elif len(digitos) >= 6:
            where.append("v.cpf LIKE %(cpf_like)s")
            params["cpf_like"] = digitos + "%"
        else:
            where.append("v.nome_completo ILIKE %(nome_like)s")
            params["nome_like"] = f"%{busca}%"

    if situacao:
        where.append("v.situacao = %(situacao)s")
        params["situacao"] = situacao
    if id_empresa:
        where.append("v.id_empresa_atual = %(id_empresa)s")
        params["id_empresa"] = id_empresa
    if id_sindicato:
        where.append("v.id_sindicato_atual = %(id_sindicato)s")
        params["id_sindicato"] = id_sindicato
    if uf:
        where.append("v.trab_uf = %(uf)s")
        params["uf"] = uf

    where_sql = " AND ".join(where)

    sql_total = f"SELECT COUNT(*) AS total FROM bss.v_trabalhador v WHERE {where_sql}"
    sql_lista = f"""
        SELECT
            v.id, v.cpf, v.nome_completo, v.titularidade, v.cpf_titular,
            v.qtd_dependentes_ativos,
            v.situacao,
            v.empresa, v.empresa_cnpj, v.sindicato, v.sindicato_categoria,
            v.trab_cidade, v.trab_uf,
            v.mes_ultimo_vinculo, v.ultimo_pagamento_em
        FROM bss.v_trabalhador v
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
    return {
        "linhas": linhas,
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "paginas": paginas,
    }


def buscar_por_id(id: int) -> dict[str, Any] | None:
    """Pega um trabalhador completo (com endereço, etc.)"""
    sql = """
        SELECT
            v.id, v.cpf, v.nome_completo, v.titularidade, v.cpf_titular,
            v.situacao, v.data_nascimento, v.data_admissao, v.data_demissao,
            v.telefone, v.email, v.trab_cidade, v.trab_uf,
            v.id_empresa_atual, v.empresa, v.empresa_cnpj,
            v.id_sindicato_atual, v.sindicato, v.sindicato_categoria,
            v.mes_ultimo_vinculo, v.ultimo_pagamento_em,
            v.qtd_dependentes_ativos
        FROM bss.v_trabalhador v
        WHERE v.id = %s
    """
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (id,))
            return cur.fetchone()

def buscar_dependentes(cpf_titular: str) -> list[dict[str, Any]]:
    """Lista dependentes de um titular (por cpf_titular)."""
    if not cpf_titular:
        return []
    sql = """
        SELECT id, cpf, nome_completo, situacao, data_nascimento
          FROM bss.trabalhador
         WHERE cpf_titular = %s
           AND titularidade = 'dependente'
         ORDER BY nome_completo
    """
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (cpf_titular,))
            return list(cur.fetchall())


def buscar_detalhe(id: int) -> dict[str, Any] | None:
    """
    Detalhe completo do trabalhador pra tela de detalhe (#37).
    Lê bss.trabalhador direto (não a view) porque precisa do endereço
    completo, criado_em e id_legado_uuid — campos que v_trabalhador não expõe.
    """
    sql = """
        SELECT
            t.id, t.cpf, t.nome_completo, t.titularidade, t.cpf_titular,
            t.situacao, t.data_nascimento, t.data_admissao, t.data_demissao,
            t.ultimo_pagamento_em, t.mes_ultimo_vinculo,
            t.telefone, t.email,
            t.logradouro, t.numero, t.complemento, t.bairro,
            t.cidade, t.uf, t.cep,
            t.qtd_dependentes_ativos,
            t.id_empresa_atual,   e.razao_social AS empresa,   e.cnpj AS empresa_cnpj,
            t.id_sindicato_atual, s.razao_social AS sindicato,  s.categoria AS sindicato_categoria,
            t.criado_em, t.atualizado_em, t.id_legado_uuid
          FROM bss.trabalhador t
          LEFT JOIN bss.empresa   e ON e.id = t.id_empresa_atual
          LEFT JOIN bss.sindicato s ON s.id = t.id_sindicato_atual
         WHERE t.id = %s
    """
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (id,))
            return cur.fetchone()


def buscar_titular(cpf: str) -> dict[str, Any] | None:
    """Acha o titular (id + nome) por CPF — pra link do dependente -> titular."""
    if not cpf:
        return None
    sql = """
        SELECT id, nome_completo
          FROM bss.trabalhador
         WHERE cpf = %s AND titularidade = 'titular'
         LIMIT 1
    """
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (cpf,))
            return cur.fetchone()
