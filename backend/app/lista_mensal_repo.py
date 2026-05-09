"""
Acesso a bss.lista_mensal e bss.lista_mensal_item.

Funções principais:
  - resolver_empresas(cnpjs)         → {cnpj_digitos: id_empresa}
  - resolver_sindicatos(nomes)       → {nome_normalizado: id_sindicato}
  - empresas_do_usuario(usuario)     → set[id_empresa]
  - processar_carga_trabalhadores(...) → grava lista_mensal + items + atualiza vínculos

A lógica de "lista é a verdade do mês" é POR (CNPJ × mes_referencia):
  trabalhadores que estavam ativos no CNPJ X e não vieram → registra
  situacao_no_upload='inativo' como item daquele upload (snapshot da saída).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from .database import get_pg_connection


def _so_digitos(s: Any) -> str:
    if s is None:
        return ""
    return re.sub(r"\D+", "", str(s))


def _norm_sindicato(s: str) -> str:
    """Normaliza nome de sindicato pra match: UPPER + TRIM + colapsa espaços."""
    return re.sub(r"\s+", " ", (s or "").strip().upper())


def primeiro_dia_do_mes(d: date | None = None) -> date:
    d = d or date.today()
    return d.replace(day=1)


# ──────────────────────────────────────────────────────────────────────────
# Lookups
# ──────────────────────────────────────────────────────────────────────────
def resolver_empresas(cnpjs: list[str]) -> dict[str, int]:
    """Recebe lista de CNPJs (14 dígitos). Retorna {cnpj: id_empresa}."""
    if not cnpjs:
        return {}
    cnpjs_set = sorted({_so_digitos(c) for c in cnpjs if _so_digitos(c)})
    sql = "SELECT id, cnpj FROM bss.empresa WHERE cnpj = ANY(%s) AND status = 'ativa'"
    out: dict[str, int] = {}
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (cnpjs_set,))
            for r in cur.fetchall():
                out[r["cnpj"]] = r["id"]
    return out


def resolver_sindicatos(nomes: list[str]) -> dict[str, int]:
    """Recebe nomes de sindicato (texto livre). Retorna {nome_norm: id_sindicato}.

    Match: UPPER+TRIM(razao_social) == UPPER+TRIM(nome_planilha).
    """
    if not nomes:
        return {}
    norm_set = sorted({_norm_sindicato(n) for n in nomes if n})
    sql = """
        SELECT id,
               UPPER(REGEXP_REPLACE(TRIM(razao_social), '\\s+', ' ', 'g')) AS chave
          FROM bss.sindicato
         WHERE ativo = TRUE
           AND UPPER(REGEXP_REPLACE(TRIM(razao_social), '\\s+', ' ', 'g'))
               = ANY(%s)
    """
    out: dict[str, int] = {}
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (norm_set,))
            for r in cur.fetchall():
                out[r["chave"]] = r["id"]
    return out


def empresas_do_usuario(id_usuario: int) -> set[int]:
    """IDs de bss.empresa vinculados ao usuário (perfil=empresa)."""
    sql = "SELECT id_empresa FROM bss.usuario_empresa WHERE id_usuario = %s"
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (id_usuario,))
            return {r["id_empresa"] for r in cur.fetchall()}


# ──────────────────────────────────────────────────────────────────────────
# Gravação principal
# ──────────────────────────────────────────────────────────────────────────
def processar_carga_trabalhadores(
    *,
    linhas: list[dict],          # [{linha, cnpj, cpf, nome, sindicato, id_empresa, id_sindicato}, ...]
    mes_referencia: date,
    id_usuario_upload: int,
    arquivo_nome: str | None = None,
) -> dict[str, Any]:
    """
    Grava em transação:
      1) Cria 1 bss.lista_mensal por (id_empresa) — agrega todas as
         linhas dessa empresa, mesmo se houver múltiplos sindicatos.
      2) Para cada linha:
         - UPSERT em bss.trabalhador (insere novo OU atualiza nome/empresa/sind)
         - INSERT em bss.lista_mensal_item (snapshot do mês)
      3) Para cada CNPJ presente: marca como 'inativo' os vínculos antigos
         (mesma empresa, mes anterior, ainda ativos) que não vieram nesta carga.
      4) Recalcula bss.trabalhador.situacao: 'ativo' se tem >=1 vínculo
         ativo no mes corrente, senão 'inativo'.

    Retorna {qtd_processadas, qtd_inativadas, listas_criadas: [ids]}.
    """
    if not linhas:
        return {"qtd_processadas": 0, "qtd_inativadas": 0, "listas_criadas": []}

    # Agrupa por empresa (1 lista_mensal por empresa)
    por_empresa: dict[int, list[dict]] = {}
    for ln in linhas:
        por_empresa.setdefault(ln["id_empresa"], []).append(ln)

    listas_criadas: list[int] = []
    qtd_processadas = 0
    qtd_inativadas = 0

    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            for id_empresa, items in por_empresa.items():
                # 1) Cria lista_mensal pra essa empresa+mes
                cur.execute(
                    """
                    INSERT INTO bss.lista_mensal
                        (id_empresa, tipo_upload, mes_referencia, arquivo_original_nome,
                         qtd_linhas_processadas, status)
                    VALUES (%s, 'ativos', %s, %s, %s, 'concluido')
                    RETURNING id
                    """,
                    (id_empresa, mes_referencia, arquivo_nome, len(items)),
                )
                id_lista = cur.fetchone()["id"]
                listas_criadas.append(id_lista)

                # 2) Pra cada linha: upsert trabalhador + insert lista_mensal_item
                cpfs_neste_upload: set[str] = set()
                for it in items:
                    # UPSERT trabalhador (chave: cpf)
                    cur.execute(
                        """
                        INSERT INTO bss.trabalhador
                            (cpf, nome_completo, id_empresa_atual, id_sindicato_atual,
                             mes_ultimo_vinculo, situacao, titularidade)
                        VALUES (%s, %s, %s, %s, %s, 'ativo', 'titular')
                        ON CONFLICT (cpf) DO UPDATE
                           SET nome_completo       = EXCLUDED.nome_completo,
                               id_empresa_atual    = EXCLUDED.id_empresa_atual,
                               id_sindicato_atual  = EXCLUDED.id_sindicato_atual,
                               mes_ultimo_vinculo  = EXCLUDED.mes_ultimo_vinculo,
                               situacao            = 'ativo',
                               atualizado_em       = NOW()
                         RETURNING id
                        """,
                        (it["cpf"], it["nome"], id_empresa, it["id_sindicato"],
                         mes_referencia),
                    )
                    id_trab = cur.fetchone()["id"]

                    # INSERT lista_mensal_item (UNIQUE por trab+mes+empresa permite multi)
                    cur.execute(
                        """
                        INSERT INTO bss.lista_mensal_item
                            (id_lista_mensal, id_trabalhador, id_empresa, id_sindicato,
                             mes_referencia, nome_completo, titularidade, situacao_no_upload)
                        VALUES (%s, %s, %s, %s, %s, %s, 'titular', 'ativo')
                        ON CONFLICT (id_trabalhador, mes_referencia, id_empresa) DO UPDATE
                           SET id_lista_mensal     = EXCLUDED.id_lista_mensal,
                               id_sindicato        = EXCLUDED.id_sindicato,
                               nome_completo       = EXCLUDED.nome_completo,
                               situacao_no_upload  = 'ativo'
                        """,
                        (id_lista, id_trab, id_empresa, it["id_sindicato"],
                         mes_referencia, it["nome"]),
                    )
                    cpfs_neste_upload.add(it["cpf"])
                    qtd_processadas += 1

                # 3) Desativação automática POR CNPJ (= por id_empresa):
                #    trabalhadores que estavam ativos nesta empresa e não vieram.
                #    Marca lista_mensal_item desse upload com situacao_no_upload='inativo'
                #    pra registrar a saída como snapshot.
                if cpfs_neste_upload:
                    cur.execute(
                        """
                        WITH ausentes AS (
                            SELECT t.id, t.cpf, t.nome_completo, t.id_sindicato_atual
                              FROM bss.trabalhador t
                             WHERE t.id_empresa_atual = %s
                               AND t.situacao = 'ativo'
                               AND t.cpf <> ALL(%s)
                        )
                        INSERT INTO bss.lista_mensal_item
                            (id_lista_mensal, id_trabalhador, id_empresa, id_sindicato,
                             mes_referencia, nome_completo, titularidade, situacao_no_upload)
                        SELECT %s, id, %s, COALESCE(id_sindicato_atual, %s),
                               %s, nome_completo, 'titular', 'inativo'
                          FROM ausentes
                        ON CONFLICT (id_trabalhador, mes_referencia, id_empresa) DO UPDATE
                            SET situacao_no_upload = 'inativo'
                        RETURNING id_trabalhador
                        """,
                        (id_empresa, sorted(cpfs_neste_upload),
                         id_lista, id_empresa, items[0]["id_sindicato"],
                         mes_referencia),
                    )
                    inativados_ids = [r["id_trabalhador"] for r in cur.fetchall()]
                    if inativados_ids:
                        # Atualiza t.situacao='inativo' SE não tem vínculo ativo em
                        # nenhuma outra empresa neste mês
                        cur.execute(
                            """
                            UPDATE bss.trabalhador t
                               SET situacao = 'inativo', atualizado_em = NOW()
                             WHERE t.id = ANY(%s)
                               AND NOT EXISTS (
                                   SELECT 1 FROM bss.lista_mensal_item lmi
                                    WHERE lmi.id_trabalhador = t.id
                                      AND lmi.mes_referencia = %s
                                      AND lmi.situacao_no_upload = 'ativo'
                               )
                            """,
                            (inativados_ids, mes_referencia),
                        )
                        qtd_inativadas += cur.rowcount

        conn.commit()

    return {
        "qtd_processadas": qtd_processadas,
        "qtd_inativadas": qtd_inativadas,
        "listas_criadas": listas_criadas,
    }

# ──────────────────────────────────────────────────────────────────────────
# INATIVAÇÃO (delta)
# ──────────────────────────────────────────────────────────────────────────
def analisar_inativacao(
    *,
    linhas_planilha: list,         # list[(linha, cnpj, cpf)]
    id_usuario_upload: int,
    perfil_usuario: str,
    mes_referencia: date,
) -> dict[str, Any]:
    """
    Análise (read-only) das linhas da planilha de inativação.
    Retorna dict com:
      - validas: lista de dicts {cnpj, cpf, id_empresa, id_trabalhador}
      - erros: dict[categoria → list[valor]]
        categorias: cnpj_nao_cadastrado, cnpj_sem_permissao,
                    cpf_nao_cadastrado, cpf_nao_ativo_neste_cnpj
    NÃO grava nada.
    """
    erros: dict[str, list[str]] = {
        "cnpj_nao_cadastrado":      [],
        "cnpj_sem_permissao":       [],
        "cpf_nao_cadastrado":       [],
        "cpf_nao_ativo_neste_cnpj": [],
    }
    if not linhas_planilha:
        return {"validas": [], "erros": erros}

    cnpjs = sorted({l.cnpj for l in linhas_planilha})
    cpfs = sorted({l.cpf for l in linhas_planilha})
    map_emp = resolver_empresas(cnpjs)

    permitidas: set[int] = set()
    if perfil_usuario == "empresa":
        permitidas = empresas_do_usuario(id_usuario_upload)

    # Resolve trabalhadores (cpf → id, id_empresa_atual, situacao)
    map_trab: dict[str, dict] = {}
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, cpf, situacao FROM bss.trabalhador WHERE cpf = ANY(%s)",
                (cpfs,),
            )
            for r in cur.fetchall():
                map_trab[r["cpf"]] = {"id": r["id"], "situacao": r["situacao"]}

            # Verifica vínculo ativo no mes_referencia
            cur.execute(
                """
                SELECT t.cpf, lmi.id_empresa
                  FROM bss.trabalhador t
                  JOIN bss.lista_mensal_item lmi ON lmi.id_trabalhador = t.id
                 WHERE t.cpf = ANY(%s)
                   AND lmi.mes_referencia = %s
                   AND lmi.situacao_no_upload = 'ativo'
                """,
                (cpfs, mes_referencia),
            )
            vinculos_ativos: set[tuple[str, int]] = {
                (r["cpf"], r["id_empresa"]) for r in cur.fetchall()
            }

    validas: list[dict] = []
    cnpjs_sem_perm: set[str] = set()
    cnpjs_nao_cad: set[str] = set()
    cpfs_nao_cad: set[str] = set()

    for ln in linhas_planilha:
        # CNPJ
        if ln.cnpj not in map_emp:
            cnpjs_nao_cad.add(_fmt_cnpj_local(ln.cnpj))
            continue
        id_empresa = map_emp[ln.cnpj]
        if perfil_usuario == "empresa" and id_empresa not in permitidas:
            cnpjs_sem_perm.add(_fmt_cnpj_local(ln.cnpj))
            continue
        # CPF
        info_trab = map_trab.get(ln.cpf)
        if not info_trab:
            cpfs_nao_cad.add(ln.cpf)
            continue
        # Vínculo ativo neste CNPJ no mês
        if (ln.cpf, id_empresa) not in vinculos_ativos:
            erros["cpf_nao_ativo_neste_cnpj"].append(
                f"{ln.cpf} no CNPJ {_fmt_cnpj_local(ln.cnpj)}"
            )
            continue
        validas.append({
            "cnpj": ln.cnpj, "cpf": ln.cpf,
            "id_empresa": id_empresa, "id_trabalhador": info_trab["id"],
        })

    erros["cnpj_nao_cadastrado"] = sorted(cnpjs_nao_cad)
    erros["cnpj_sem_permissao"]  = sorted(cnpjs_sem_perm)
    erros["cpf_nao_cadastrado"]  = sorted(cpfs_nao_cad)

    return {"validas": validas, "erros": {k: v for k, v in erros.items() if v}}


def efetivar_inativacao(
    *,
    validas: list[dict],            # [{cnpj, cpf, id_empresa, id_trabalhador}, ...]
    mes_referencia: date,
    arquivo_nome: str | None = None,
) -> dict[str, Any]:
    """Marca como inativos os vínculos validados. Idempotente."""
    if not validas:
        return {"qtd_inativadas": 0, "listas_criadas": []}

    # Agrupa por empresa pra criar 1 lista_mensal por empresa
    por_empresa: dict[int, list[dict]] = {}
    for v in validas:
        por_empresa.setdefault(v["id_empresa"], []).append(v)

    listas_criadas: list[int] = []
    qtd_inativadas = 0

    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            for id_empresa, items in por_empresa.items():
                cur.execute(
                    """
                    INSERT INTO bss.lista_mensal
                        (id_empresa, tipo_upload, mes_referencia, arquivo_original_nome,
                         qtd_linhas_processadas, status)
                    VALUES (%s, 'inativacao', %s, %s, %s, 'concluido')
                    RETURNING id
                    """,
                    (id_empresa, mes_referencia, arquivo_nome, len(items)),
                )
                id_lista = cur.fetchone()["id"]
                listas_criadas.append(id_lista)

                trab_ids = [it["id_trabalhador"] for it in items]
                # Marca lista_mensal_item como inativo (UPDATE — já existe pelo upload Carregar)
                cur.execute(
                    """
                    UPDATE bss.lista_mensal_item
                       SET situacao_no_upload = 'inativo',
                           id_lista_mensal    = %s
                     WHERE id_empresa     = %s
                       AND mes_referencia = %s
                       AND id_trabalhador = ANY(%s)
                    """,
                    (id_lista, id_empresa, mes_referencia, trab_ids),
                )
                qtd_inativadas += cur.rowcount

                # Recalcula trabalhador.situacao
                cur.execute(
                    """
                    UPDATE bss.trabalhador t
                       SET situacao = 'inativo', atualizado_em = NOW()
                     WHERE t.id = ANY(%s)
                       AND NOT EXISTS (
                           SELECT 1 FROM bss.lista_mensal_item lmi
                            WHERE lmi.id_trabalhador = t.id
                              AND lmi.mes_referencia = %s
                              AND lmi.situacao_no_upload = 'ativo'
                       )
                    """,
                    (trab_ids, mes_referencia),
                )
        conn.commit()

    return {"qtd_inativadas": qtd_inativadas, "listas_criadas": listas_criadas}


def _fmt_cnpj_local(c: str) -> str:
    if not c or len(c) != 14:
        return c
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"


# ──────────────────────────────────────────────────────────────────────────
# DEPENDENTES (adiciona — não desativa)
# ──────────────────────────────────────────────────────────────────────────
def analisar_e_processar_dependentes(
    *,
    linhas_planilha: list,    # list[LinhaDependente]
    id_usuario_upload: int,
    perfil_usuario: str,
    mes_referencia: date,
    arquivo_nome: str | None = None,
) -> dict[str, Any]:
    """
    Valida + grava dependentes em uma só passada (delta puro).
    Retorna {validas, erros, qtd_processadas, listas_criadas} no formato all-or-nothing:
      - se há erros que bloqueiam, retorna {erros: ..., qtd_processadas: 0}
      - se ok, grava e retorna qtd_processadas + listas_criadas
    """
    erros: dict[str, list[str]] = {
        "cnpj_nao_cadastrado":         [],
        "cnpj_sem_permissao":          [],
        "titular_nao_cadastrado":      [],
        "titular_nao_ativo_neste_cnpj":[],
    }
    if not linhas_planilha:
        return {"erros": {}, "qtd_processadas": 0, "listas_criadas": []}

    cnpjs = sorted({l.cnpj for l in linhas_planilha})
    cpfs_titular = sorted({l.cpf_titular for l in linhas_planilha})
    map_emp = resolver_empresas(cnpjs)
    permitidas: set[int] = (
        empresas_do_usuario(id_usuario_upload) if perfil_usuario == "empresa" else set()
    )

    # Lookup titulares + vínculos ativos
    map_trab_titular: dict[str, int] = {}
    vinculos_ativos: set[tuple[str, int]] = set()
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, cpf FROM bss.trabalhador WHERE cpf = ANY(%s) AND titularidade = 'titular'",
                (cpfs_titular,),
            )
            for r in cur.fetchall():
                map_trab_titular[r["cpf"]] = r["id"]
            cur.execute(
                """
                SELECT t.cpf, lmi.id_empresa
                  FROM bss.trabalhador t
                  JOIN bss.lista_mensal_item lmi ON lmi.id_trabalhador = t.id
                 WHERE t.cpf = ANY(%s)
                   AND lmi.mes_referencia = %s
                   AND lmi.situacao_no_upload = 'ativo'
                """,
                (cpfs_titular, mes_referencia),
            )
            vinculos_ativos = {(r["cpf"], r["id_empresa"]) for r in cur.fetchall()}

    cnpjs_nao_cad: set[str] = set()
    cnpjs_sem_perm: set[str] = set()
    cpfs_titular_nao_cad: set[str] = set()
    pares_titular_sem_vinc: set[str] = set()
    validas: list[dict] = []

    for ln in linhas_planilha:
        if ln.cnpj not in map_emp:
            cnpjs_nao_cad.add(_fmt_cnpj_local(ln.cnpj)); continue
        id_empresa = map_emp[ln.cnpj]
        if perfil_usuario == "empresa" and id_empresa not in permitidas:
            cnpjs_sem_perm.add(_fmt_cnpj_local(ln.cnpj)); continue
        id_titular = map_trab_titular.get(ln.cpf_titular)
        if not id_titular:
            cpfs_titular_nao_cad.add(ln.cpf_titular); continue
        if (ln.cpf_titular, id_empresa) not in vinculos_ativos:
            pares_titular_sem_vinc.add(
                f"{ln.cpf_titular} no CNPJ {_fmt_cnpj_local(ln.cnpj)}"
            ); continue
        validas.append({
            "cnpj": ln.cnpj, "cpf_dep": ln.cpf_dep, "nome_dep": ln.nome_dep,
            "cpf_titular": ln.cpf_titular, "id_empresa": id_empresa,
        })

    erros["cnpj_nao_cadastrado"]          = sorted(cnpjs_nao_cad)
    erros["cnpj_sem_permissao"]           = sorted(cnpjs_sem_perm)
    erros["titular_nao_cadastrado"]       = sorted(cpfs_titular_nao_cad)
    erros["titular_nao_ativo_neste_cnpj"] = sorted(pares_titular_sem_vinc)
    erros = {k: v for k, v in erros.items() if v}

    # All-or-nothing: se algum erro, não grava nada
    if erros:
        return {"erros": erros, "qtd_processadas": 0, "listas_criadas": []}

    # Grava em transação
    por_empresa: dict[int, list[dict]] = {}
    for v in validas:
        por_empresa.setdefault(v["id_empresa"], []).append(v)
    listas_criadas: list[int] = []
    qtd = 0

    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            for id_empresa, items in por_empresa.items():
                cur.execute(
                    """
                    INSERT INTO bss.lista_mensal
                        (id_empresa, tipo_upload, mes_referencia, arquivo_original_nome,
                         qtd_linhas_processadas, status)
                    VALUES (%s, 'dependentes', %s, %s, %s, 'concluido')
                    RETURNING id
                    """,
                    (id_empresa, mes_referencia, arquivo_nome, len(items)),
                )
                id_lista = cur.fetchone()["id"]
                listas_criadas.append(id_lista)

                for it in items:
                    # Pega o id_sindicato_atual do titular pra herdar pro dependente
                    cur.execute(
                        "SELECT id, id_sindicato_atual FROM bss.trabalhador WHERE cpf = %s",
                        (it["cpf_titular"],),
                    )
                    tit = cur.fetchone()
                    id_sindicato = tit["id_sindicato_atual"]

                    # UPSERT trabalhador (dependente)
                    cur.execute(
                        """
                        INSERT INTO bss.trabalhador
                            (cpf, nome_completo, id_empresa_atual, id_sindicato_atual,
                             mes_ultimo_vinculo, situacao, titularidade, cpf_titular)
                        VALUES (%s, %s, %s, %s, %s, 'ativo', 'dependente', %s)
                        ON CONFLICT (cpf) DO UPDATE
                           SET nome_completo      = EXCLUDED.nome_completo,
                               id_empresa_atual   = EXCLUDED.id_empresa_atual,
                               id_sindicato_atual = EXCLUDED.id_sindicato_atual,
                               mes_ultimo_vinculo = EXCLUDED.mes_ultimo_vinculo,
                               situacao           = 'ativo',
                               titularidade       = 'dependente',
                               cpf_titular        = EXCLUDED.cpf_titular,
                               atualizado_em      = NOW()
                         RETURNING id
                        """,
                        (it["cpf_dep"], it["nome_dep"], id_empresa, id_sindicato,
                         mes_referencia, it["cpf_titular"]),
                    )
                    id_dep = cur.fetchone()["id"]
                    cur.execute(
                        """
                        INSERT INTO bss.lista_mensal_item
                            (id_lista_mensal, id_trabalhador, id_empresa, id_sindicato,
                             mes_referencia, nome_completo, titularidade, situacao_no_upload)
                        VALUES (%s, %s, %s, %s, %s, %s, 'dependente', 'ativo')
                        ON CONFLICT (id_trabalhador, mes_referencia, id_empresa) DO UPDATE
                           SET id_lista_mensal    = EXCLUDED.id_lista_mensal,
                               nome_completo      = EXCLUDED.nome_completo,
                               situacao_no_upload = 'ativo',
                               titularidade       = 'dependente'
                        """,
                        (id_lista, id_dep, id_empresa, id_sindicato,
                         mes_referencia, it["nome_dep"]),
                    )
                    # Atualiza qtd_dependentes_ativos do titular
                    cur.execute(
                        """
                        UPDATE bss.trabalhador
                           SET qtd_dependentes_ativos = (
                               SELECT COUNT(*) FROM bss.trabalhador
                                WHERE cpf_titular = %s AND situacao = 'ativo'
                           )
                         WHERE cpf = %s
                        """,
                        (it["cpf_titular"], it["cpf_titular"]),
                    )
                    qtd += 1

        conn.commit()

    return {"erros": {}, "qtd_processadas": qtd, "listas_criadas": listas_criadas}
