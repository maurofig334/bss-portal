"""
Emissão de boletos pelo BSS — épico #21.

Modelagem DELTA (regra confirmada com cliente em 2026-05-09):

  - O usuário pode rodar "Gerar Boletos por CNPJ" várias vezes no mesmo mês.
  - Cada chamada gera boleto APENAS pros trabalhadores ATIVOS que ainda
    NÃO estão em nenhum boleto vivo (= não-cancelado, não-pago) pra esse
    par (sindicato × mes_amparo).
  - Boletos NUNCA são editados: se a empresa adiciona trabalhador depois,
    a 2ª geração emite boleto SEPARADO só com os novos.
  - Se a empresa excluiu trabalhador depois da 1ª geração, o boleto velho
    fica intacto — não tem rollback (regra do cliente: "boleto oficial
    é com os trabalhadores existentes na época da 1a geração").

Fluxo:
  1) preview_emissao(usuario, mes_amparo) — retorna estrutura aninhada com:
       empresas que o usuário controla → sindicatos com ativos → trabalhadores
       Indica quantos já estão cobertos e quantos vão entrar no novo boleto.
  2) emitir_boletos(usuario, mes_amparo, ids_empresa=None) — gera 1 boleto por
     (empresa × sindicato × mes_amparo) com APENAS o delta de trabalhadores
     ainda não cobertos. Idempotente.
  3) cancelar_boleto(id, motivo) — flip status pra 'cancelado'.
  4) reemitir_boleto(id_velho) — cancela velho + cria novo apontando
     id_boleto_substituido (mantém os mesmos trabalhadores do velho).

Convenções:
  - mes_amparo  = mês corrente (primeiro dia do mês). Mês do vencimento.
  - competencia = mes_amparo - 1 mês.
  - data_vencimento = max( first_day(mes_amparo) + dia_venc_param,  hoje + 1 dia )
                      [com cap no último dia do mês de amparo]
  - status default 'gerado' (UI mostra como "Aberto").
  - tipo 'Sistema' (distingue dos legados 'Webservice').
  - banco vem de parametros_boleto.banco_geracao_boleto (fallback 'itau50').

Definição de "trabalhador já coberto":
  - Existe bss.boleto_item com esse id_trabalhador apontando pra um
    bss.boleto com mesmo id_sindicato + mes_referencia + status NOT IN
    ('cancelado','pago').

Permissões:
  - admin/interno: emite pra qualquer empresa
  - empresa: emite só pras empresas em usuario.empresas
  - demais perfis: bloqueado
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Any

from .auth import UsuarioInfo
from .database import get_pg_connection


# Vencimentos por mês na parametros_boleto:
_COL_VENCIMENTO = {
    1: "vencimento_jan",  2: "vencimento_fev",  3: "vencimento_mar",
    4: "vencimento_abr",  5: "vencimento_mai",  6: "vencimento_jun",
    7: "vencimento_jul",  8: "vencimento_ago",  9: "vencimento_set",
    10: "vencimento_out", 11: "vencimento_nov", 12: "vencimento_dez",
}

# Status considerado "vivo" (= bloqueia reemissão / é editável):
_STATUS_VIVOS = ("gerado", "vencido", "pendente")

# Perfis que podem disparar emissão:
_PERFIS_EMISSAO = {"admin", "interno", "empresa"}


# =============================================================================
# Helpers
# =============================================================================

def _primeiro_dia(d: date) -> date:
    return d.replace(day=1)


def _ultimo_dia_mes(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def _calcular_vencimento(mes_amparo: date, dia_venc_param: int | None,
                          hoje: date) -> date:
    """Regra confirmada com cliente:
    - Default: dia X do mês de amparo (ex: parametros.vencimento_mai=11 → 11/05).
    - Se hoje > essa data, vencimento vira hoje+1 (até acabar o mês de amparo).
    - Se nem o parâmetro tem (NULL), usa só hoje+1.
    """
    venc = None
    if dia_venc_param:
        try:
            venc = mes_amparo.replace(day=int(dia_venc_param))
        except ValueError:
            venc = _ultimo_dia_mes(mes_amparo)
    minimo = hoje + timedelta(days=1)
    if venc is None or venc < minimo:
        venc = minimo
    fim = _ultimo_dia_mes(mes_amparo)
    if venc > fim:
        venc = fim
    return venc


def _empresas_visiveis(conn, usuario: UsuarioInfo) -> list[int] | None:
    """Retorna a lista de id_empresa que o usuário pode operar na emissão.

    None = sem filtro (admin/interno enxergam todas as empresas com ativos).
    Lista vazia = nenhuma empresa (perfil sem permissão ou empresa sem vínculo).
    """
    if usuario.perfil in ("admin", "interno"):
        return None
    if usuario.perfil == "empresa":
        return list(usuario.empresas)
    return []


# =============================================================================
# Preview (passo 2 do fluxo: tela com empresas → sindicatos → trabalhadores)
# =============================================================================

def preview_emissao(usuario: UsuarioInfo, mes_amparo: date,
                    id_empresa: int | None = None) -> dict[str, Any]:
    """
    Retorna estrutura pra renderizar a tela de preview da emissão.

    Comportamento por perfil:
      - empresa: lista TODAS as empresas em usuario.empresas (id_empresa ignorado)
      - admin/interno: REQUER id_empresa (sem ele retorna vazio com aviso —
        evita varrer toda a base de 6.1M trabalhadores)

    Estrutura:
        {
          "mes_amparo": "2026-05",
          "competencia": "2026-04",
          "empresas": [...],
          "aviso": "..." (opcional)
        }
    """
    if usuario.perfil not in _PERFIS_EMISSAO:
        return {"empresas": [], "erro": "Perfil sem permissão de emissão"}

    mes_amparo = _primeiro_dia(mes_amparo)
    competencia = (mes_amparo.replace(day=1) - timedelta(days=1)).replace(day=1)

    # Determina filtro de empresas conforme perfil:
    if usuario.perfil == "empresa":
        # Empresa sempre vê todas as suas (ignora id_empresa do request):
        filtro_empresas = list(usuario.empresas)
        if not filtro_empresas:
            return {"empresas": [], "mes_amparo": mes_amparo.strftime("%Y-%m"),
                    "competencia": competencia.strftime("%Y-%m"),
                    "aviso": "Usuário sem empresas vinculadas"}
    else:
        # admin/interno: REQUER id_empresa pra evitar varrer base inteira
        if id_empresa is None:
            return {"empresas": [], "mes_amparo": mes_amparo.strftime("%Y-%m"),
                    "competencia": competencia.strftime("%Y-%m"),
                    "aviso": "Selecione uma empresa pra ver o preview"}
        filtro_empresas = [id_empresa]

    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            # Empresas do usuário com pelo menos 1 trabalhador ativo:
            sql_emp = """
                SELECT e.id, e.razao_social, e.cnpj,
                       COUNT(t.id) AS qtd_ativos
                  FROM bss.empresa e
                  JOIN bss.trabalhador t
                    ON t.id_empresa_atual = e.id AND t.situacao = 'ativo'
                 WHERE e.status = 'ativa'
            """
            params: list[Any] = []
            if filtro_empresas is not None:
                sql_emp += " AND e.id = ANY(%s)"
                params.append(filtro_empresas)
            sql_emp += " GROUP BY e.id, e.razao_social, e.cnpj ORDER BY e.razao_social"
            cur.execute(sql_emp, params)
            empresas = cur.fetchall()
            if not empresas:
                return {"empresas": [], "mes_amparo": mes_amparo.strftime("%Y-%m"),
                        "competencia": competencia.strftime("%Y-%m")}

            ids_empresa = [e["id"] for e in empresas]

            # Sindicatos com ativos por empresa, com tarifa do parâmetro:
            sql_sind = """
                SELECT t.id_empresa_atual    AS id_empresa,
                       t.id_sindicato_atual  AS id_sindicato,
                       s.razao_social        AS sindicato,
                       p.id                  AS id_parametro,
                       p.nome                AS parametro_nome,
                       p.tarifa_titular,
                       p.tarifa_dependente,
                       p.aceita_dependentes,
                       p.banco_geracao_boleto,
                       SUM(CASE WHEN t.titularidade = 'titular' THEN 1 ELSE 0 END) AS qtd_titulares,
                       SUM(CASE WHEN t.titularidade = 'dependente' THEN 1 ELSE 0 END) AS qtd_dependentes
                  FROM bss.trabalhador t
                  JOIN bss.sindicato s ON s.id = t.id_sindicato_atual
             LEFT JOIN bss.parametros_boleto p
                    ON p.id_sindicato = s.id AND p.ativo
                 WHERE t.id_empresa_atual = ANY(%s)
                   AND t.situacao = 'ativo'
                   AND t.id_sindicato_atual IS NOT NULL
                 GROUP BY t.id_empresa_atual, t.id_sindicato_atual,
                          s.razao_social, p.id, p.nome, p.tarifa_titular,
                          p.tarifa_dependente, p.aceita_dependentes,
                          p.banco_geracao_boleto
                 ORDER BY t.id_empresa_atual, s.razao_social
            """
            cur.execute(sql_sind, (ids_empresa,))
            grupos_sind = cur.fetchall()

            # Trabalhadores JÁ COBERTOS por boleto vivo (não-cancelado/não-pago)
            # pra (sindicato × mes_amparo) — independente da empresa atual:
            cur.execute(
                """
                SELECT bi.id_trabalhador, bi.id_sindicato
                  FROM bss.boleto_item bi
                  JOIN bss.boleto b ON b.id = bi.id_boleto
                 WHERE bi.mes_referencia = %s
                   AND b.status NOT IN ('cancelado','pago')
                """,
                (mes_amparo,),
            )
            cobertos: set[tuple[int, int]] = set()  # (id_trabalhador, id_sindicato)
            for r in cur.fetchall():
                cobertos.add((r["id_trabalhador"], r["id_sindicato"]))

            # Boletos vivos por (empresa, sindicato) só pra mostrar referência
            # ("já tem boletos do mês — adicionando os novos"):
            cur.execute(
                """
                SELECT id_empresa, id_sindicato,
                       COUNT(*) AS qtd_boletos,
                       SUM(qtd_trabalhadores + qtd_dependentes) AS qtd_pessoas
                  FROM bss.boleto
                 WHERE id_empresa = ANY(%s)
                   AND mes_referencia = %s
                   AND status NOT IN ('cancelado','pago')
                 GROUP BY id_empresa, id_sindicato
                """,
                (ids_empresa, mes_amparo),
            )
            ja_emitidos = {
                (r["id_empresa"], r["id_sindicato"]): r for r in cur.fetchall()
            }

            # Trabalhadores por (empresa, sindicato) — pra dropdown:
            cur.execute(
                """
                SELECT t.id_empresa_atual    AS id_empresa,
                       t.id_sindicato_atual  AS id_sindicato,
                       t.id, t.cpf, t.nome_completo, t.titularidade
                  FROM bss.trabalhador t
                 WHERE t.id_empresa_atual = ANY(%s)
                   AND t.situacao = 'ativo'
                   AND t.id_sindicato_atual IS NOT NULL
                 ORDER BY t.titularidade DESC, t.nome_completo
                """,
                (ids_empresa,),
            )
            trabs = cur.fetchall()

    # Separa trabalhadores em "novos" (a gerar) vs "já cobertos":
    trabs_novos: dict[tuple[int, int], list[dict[str, Any]]] = {}
    trabs_cobertos: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for t in trabs:
        chave = (t["id_empresa"], t["id_sindicato"])
        info = {
            "id": t["id"], "cpf": t["cpf"],
            "nome": t["nome_completo"],
            "tipo": "TRABALHADOR" if t["titularidade"] == "titular" else "DEPENDENTE",
        }
        if (t["id"], t["id_sindicato"]) in cobertos:
            trabs_cobertos.setdefault(chave, []).append(info)
        else:
            trabs_novos.setdefault(chave, []).append(info)

    # Indexa sindicatos por id_empresa:
    sind_por_empresa: dict[int, list[dict[str, Any]]] = {}
    for g in grupos_sind:
        emp_id = g["id_empresa"]
        sind_id = g["id_sindicato"]
        tarifa_t = float(g["tarifa_titular"] or 0)
        tarifa_d = float(g["tarifa_dependente"] or 0) if g["aceita_dependentes"] else 0.0
        chave = (emp_id, sind_id)

        # qtd a gerar = só trabalhadores ainda não cobertos
        novos = trabs_novos.get(chave, [])
        qtd_t_novos = sum(1 for x in novos if x["tipo"] == "TRABALHADOR")
        qtd_d_novos = sum(1 for x in novos if x["tipo"] == "DEPENDENTE") if g["aceita_dependentes"] else 0
        valor = round(qtd_t_novos * tarifa_t + qtd_d_novos * tarifa_d, 2)

        cob = trabs_cobertos.get(chave, [])
        qtd_t_cob = sum(1 for x in cob if x["tipo"] == "TRABALHADOR")
        qtd_d_cob = sum(1 for x in cob if x["tipo"] == "DEPENDENTE")

        ref_existente = ja_emitidos.get(chave)
        sind_por_empresa.setdefault(emp_id, []).append({
            "id_sindicato":     sind_id,
            "razao_social":     g["sindicato"],
            "parametro_nome":   g["parametro_nome"],
            "id_parametro":     g["id_parametro"],
            "tarifa_titular":   tarifa_t,
            "tarifa_dependente": tarifa_d,
            "aceita_dependentes": bool(g["aceita_dependentes"]),
            "qtd_titulares":    qtd_t_novos,        # a GERAR
            "qtd_dependentes":  qtd_d_novos,        # a GERAR
            "qtd_titulares_cobertos":   qtd_t_cob,  # já em boleto vivo
            "qtd_dependentes_cobertos": qtd_d_cob,
            "valor_estimado":   valor,
            "ja_tem_boleto":    ref_existente is not None,
            "qtd_boletos_existentes": int(ref_existente["qtd_boletos"]) if ref_existente else 0,
            "banco":            g["banco_geracao_boleto"] or "itau50",
            "trabalhadores":    novos,                                 # só os a GERAR
            "trabalhadores_cobertos": cob,                             # informativo
        })

    # Monta resposta:
    saida = []
    for e in empresas:
        sinds = sind_por_empresa.get(e["id"], [])
        if not sinds:
            continue  # empresa sem sindicato apontado em nenhum trabalhador
        saida.append({
            "id":              e["id"],
            "razao_social":    e["razao_social"],
            "cnpj":            e["cnpj"],
            "qtd_ativos_total": int(e["qtd_ativos"] or 0),
            "sindicatos":      sinds,
        })

    return {
        "mes_amparo":   mes_amparo.strftime("%Y-%m"),
        "competencia":  competencia.strftime("%Y-%m"),
        "empresas":     saida,
    }


# =============================================================================
# Emissão (passo 3 do fluxo)
# =============================================================================

def emitir_boletos(usuario: UsuarioInfo, mes_amparo: date,
                   ids_empresa: list[int] | None = None) -> dict[str, Any]:
    """
    Gera boletos pra todas as combinações (empresa × sindicato × mes_amparo)
    do usuário onde houver trabalhadores ativos e ainda não existir boleto vivo.

    Retorna:
        {
          "gerados":   [ {id_boleto, nosso_numero, empresa, sindicato, valor, qtd}, ... ],
          "pulados":   [ {empresa, sindicato, motivo}, ... ],
          "erros":     [ {empresa, sindicato, motivo}, ... ],
          "mes_amparo":"2026-05",
        }
    """
    if usuario.perfil not in _PERFIS_EMISSAO:
        return {"gerados": [], "pulados": [], "erros": [
            {"motivo": "Perfil sem permissão de emissão"}
        ]}

    mes_amparo = _primeiro_dia(mes_amparo)
    hoje = date.today()
    mes_int = mes_amparo.month
    col_venc = _COL_VENCIMENTO[mes_int]

    # Determina escopo conforme perfil:
    if usuario.perfil == "empresa":
        if not usuario.empresas:
            return {"gerados": [], "pulados": [], "erros": [
                {"motivo": "Usuário não tem empresas vinculadas"}
            ], "mes_amparo": mes_amparo.strftime("%Y-%m")}
        # Empresa: usa o subset informado (se válido), senão todas as suas.
        if ids_empresa:
            ids_empresa = [i for i in ids_empresa if i in usuario.empresas]
            if not ids_empresa:
                return {"gerados": [], "pulados": [], "erros": [
                    {"motivo": "Nenhuma empresa do filtro está no escopo do usuário"}
                ], "mes_amparo": mes_amparo.strftime("%Y-%m")}
        else:
            ids_empresa = list(usuario.empresas)
    else:
        # admin/interno: REQUER ids_empresa (não varremos base inteira)
        if not ids_empresa:
            return {"gerados": [], "pulados": [], "erros": [
                {"motivo": "Internos devem informar ids_empresa específicos"}
            ], "mes_amparo": mes_amparo.strftime("%Y-%m")}

    gerados: list[dict[str, Any]] = []
    pulados: list[dict[str, Any]] = []
    erros: list[dict[str, Any]] = []

    with get_pg_connection() as conn:
        try:
            with conn.cursor() as cur:
                # 1) Lista pares (empresa, sindicato) com ativos + parâmetro:
                sql_pares = f"""
                    SELECT t.id_empresa_atual    AS id_empresa,
                           e.razao_social        AS empresa,
                           t.id_sindicato_atual  AS id_sindicato,
                           s.razao_social        AS sindicato,
                           p.id                  AS id_parametro,
                           p.tarifa_titular,
                           p.tarifa_dependente,
                           p.aceita_dependentes,
                           p.{col_venc}          AS dia_venc,
                           p.banco_geracao_boleto AS banco
                      FROM bss.trabalhador t
                      JOIN bss.empresa  e ON e.id = t.id_empresa_atual
                      JOIN bss.sindicato s ON s.id = t.id_sindicato_atual
                      LEFT JOIN bss.parametros_boleto p
                             ON p.id_sindicato = s.id AND p.ativo
                     WHERE t.situacao = 'ativo'
                       AND t.id_sindicato_atual IS NOT NULL
                """
                params_pares: list[Any] = []
                if ids_empresa is not None:
                    sql_pares += " AND t.id_empresa_atual = ANY(%s)"
                    params_pares.append(ids_empresa)
                sql_pares += """
                     GROUP BY t.id_empresa_atual, e.razao_social,
                              t.id_sindicato_atual, s.razao_social,
                              p.id, p.tarifa_titular, p.tarifa_dependente,
                              p.aceita_dependentes, p.""" + col_venc + """, p.banco_geracao_boleto
                """
                cur.execute(sql_pares, params_pares)
                pares = cur.fetchall()

                if not pares:
                    return {"gerados": [], "pulados": [], "erros": [
                        {"motivo": "Nenhum trabalhador ativo encontrado"}
                    ], "mes_amparo": mes_amparo.strftime("%Y-%m")}

                # 2) Pra cada par, calcula DELTA (trabs ativos − já cobertos):
                for p in pares:
                    id_empresa = p["id_empresa"]
                    id_sindicato = p["id_sindicato"]

                    # Sindicato sem parametros_boleto: erro
                    if p["id_parametro"] is None:
                        erros.append({"empresa": p["empresa"], "sindicato": p["sindicato"],
                                      "motivo": "Sindicato sem parametros_boleto ativo"})
                        continue
                    if p["tarifa_titular"] is None:
                        erros.append({"empresa": p["empresa"], "sindicato": p["sindicato"],
                                      "motivo": "Sindicato sem tarifa_titular configurada"})
                        continue

                    # Trabalhadores ativos do par:
                    cur.execute(
                        """
                        SELECT id, nome_completo, cpf, titularidade
                          FROM bss.trabalhador
                         WHERE id_empresa_atual = %s AND id_sindicato_atual = %s
                           AND situacao = 'ativo' AND titularidade = 'titular'
                         ORDER BY nome_completo
                        """,
                        (id_empresa, id_sindicato),
                    )
                    todos_titulares = cur.fetchall()

                    todos_deps: list[dict[str, Any]] = []
                    if p["aceita_dependentes"] and p["tarifa_dependente"]:
                        cur.execute(
                            """
                            SELECT id, nome_completo, cpf, titularidade
                              FROM bss.trabalhador
                             WHERE id_empresa_atual = %s AND id_sindicato_atual = %s
                               AND situacao = 'ativo' AND titularidade = 'dependente'
                             ORDER BY nome_completo
                            """,
                            (id_empresa, id_sindicato),
                        )
                        todos_deps = cur.fetchall()

                    # Filtra os já cobertos (estão em boleto vivo desse mês × sindicato):
                    cur.execute(
                        """
                        SELECT bi.id_trabalhador
                          FROM bss.boleto_item bi
                          JOIN bss.boleto b ON b.id = bi.id_boleto
                         WHERE bi.mes_referencia = %s
                           AND b.id_sindicato = %s
                           AND b.status NOT IN ('cancelado','pago')
                        """,
                        (mes_amparo, id_sindicato),
                    )
                    cobertos = {r["id_trabalhador"] for r in cur.fetchall()}

                    titulares = [t for t in todos_titulares if t["id"] not in cobertos]
                    deps = [d for d in todos_deps if d["id"] not in cobertos]

                    qtd_t = len(titulares)
                    qtd_d = len(deps)
                    if qtd_t + qtd_d == 0:
                        # Todos os ativos já estão cobertos — pula.
                        pulados.append({
                            "empresa": p["empresa"], "sindicato": p["sindicato"],
                            "motivo": (
                                f'Todos os {len(todos_titulares)} trabalhador(es) ativo(s) '
                                'já estão em boleto vivo deste mês'
                            ),
                        })
                        continue

                    tarifa_t = float(p["tarifa_titular"])
                    tarifa_d = float(p["tarifa_dependente"] or 0)
                    valor_total = round(qtd_t * tarifa_t + qtd_d * tarifa_d, 2)

                    venc = _calcular_vencimento(mes_amparo, p["dia_venc"], hoje)
                    banco = p["banco"] or "itau50"

                    # Gera nosso_numero da sequence:
                    cur.execute("SELECT nextval('bss.seq_boleto_nosso_numero') AS n")
                    nosso = str(cur.fetchone()["n"]).zfill(8)

                    # Insere boleto:
                    cur.execute(
                        """
                        INSERT INTO bss.boleto (
                            id_empresa, id_sindicato, mes_referencia,
                            qtd_trabalhadores, qtd_dependentes, valor_total,
                            banco, nosso_numero, status, tipo,
                            data_emissao, data_vencimento
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s,
                            %s, %s, 'gerado', 'Sistema',
                            NOW(), %s
                        )
                        RETURNING id
                        """,
                        (id_empresa, id_sindicato, mes_amparo,
                         qtd_t, qtd_d, valor_total,
                         banco, nosso, venc),
                    )
                    id_boleto = cur.fetchone()["id"]

                    # Insere itens (titulares + dependentes):
                    itens = [(id_boleto, t["id"], id_sindicato, mes_amparo,
                              tarifa_t, False) for t in titulares]
                    if deps:
                        itens += [(id_boleto, d["id"], id_sindicato, mes_amparo,
                                   tarifa_d, True) for d in deps]
                    cur.executemany(
                        """
                        INSERT INTO bss.boleto_item (
                            id_boleto, id_trabalhador, id_sindicato,
                            mes_referencia, taxa_aplicada, eh_dependente
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        itens,
                    )

                    gerados.append({
                        "id_boleto":     id_boleto,
                        "nosso_numero":  nosso,
                        "empresa":       p["empresa"],
                        "id_empresa":    id_empresa,
                        "sindicato":     p["sindicato"],
                        "id_sindicato":  id_sindicato,
                        "valor_total":   valor_total,
                        "qtd_titulares": qtd_t,
                        "qtd_dependentes": qtd_d,
                        "data_vencimento": venc.isoformat(),
                    })

            conn.commit()
        except Exception:
            conn.rollback()
            raise

    return {
        "gerados":    gerados,
        "pulados":    pulados,
        "erros":      erros,
        "mes_amparo": mes_amparo.strftime("%Y-%m"),
    }


# =============================================================================
# Cancelamento e Reemissão
# =============================================================================

def cancelar_boleto(usuario: UsuarioInfo, id_boleto: int, motivo: str) -> dict[str, Any]:
    """Cancela um boleto (status='cancelado'). Apenas admin/interno."""
    if usuario.perfil not in ("admin", "interno"):
        return {"ok": False, "erro": "Perfil sem permissão de cancelamento"}
    if not motivo or not motivo.strip():
        return {"ok": False, "erro": "Motivo do cancelamento é obrigatório"}

    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, status FROM bss.boleto WHERE id = %s",
                (id_boleto,),
            )
            row = cur.fetchone()
            if not row:
                return {"ok": False, "erro": "Boleto não encontrado"}
            if row["status"] in ("cancelado", "pago"):
                return {"ok": False, "erro": f"Boleto já está '{row['status']}'"}
            cur.execute(
                """
                UPDATE bss.boleto
                   SET status = 'cancelado',
                       motivo_cancelamento = %s,
                       atualizado_em = NOW()
                 WHERE id = %s
                """,
                (motivo.strip(), id_boleto),
            )
        conn.commit()
    return {"ok": True}


def reemitir_boleto(usuario: UsuarioInfo, id_boleto_velho: int) -> dict[str, Any]:
    """
    Reemite (segunda via): cancela o boleto velho e cria um novo apontando
    id_boleto_substituido. Apenas pra status 'vencido' ou 'pendente'.
    """
    if usuario.perfil not in _PERFIS_EMISSAO:
        return {"ok": False, "erro": "Perfil sem permissão de reemissão"}

    hoje = date.today()
    with get_pg_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, id_empresa, id_sindicato, mes_referencia,
                           qtd_trabalhadores, qtd_dependentes, valor_total,
                           banco, status
                      FROM bss.boleto
                     WHERE id = %s
                    """,
                    (id_boleto_velho,),
                )
                v = cur.fetchone()
                if not v:
                    return {"ok": False, "erro": "Boleto não encontrado"}
                if v["status"] not in ("vencido", "pendente"):
                    return {"ok": False, "erro":
                            f"Só é possível reemitir boletos 'vencido' ou 'pendente' (atual: {v['status']})"}

                # Permissão de empresa: só sua própria
                if usuario.perfil == "empresa" and v["id_empresa"] not in usuario.empresas:
                    return {"ok": False, "erro": "Boleto fora do escopo"}

                # Recalcula data_vencimento usando hoje:
                mes_amparo = v["mes_referencia"]
                col_venc = _COL_VENCIMENTO[mes_amparo.month]
                cur.execute(
                    f"SELECT {col_venc} AS dia FROM bss.parametros_boleto "
                    "WHERE id_sindicato = %s AND ativo LIMIT 1",
                    (v["id_sindicato"],),
                )
                row_param = cur.fetchone()
                dia_venc = row_param["dia"] if row_param else None
                venc = _calcular_vencimento(mes_amparo, dia_venc, hoje)

                # Gera nosso_numero novo:
                cur.execute("SELECT nextval('bss.seq_boleto_nosso_numero') AS n")
                nosso = str(cur.fetchone()["n"]).zfill(8)

                # Insere o novo:
                cur.execute(
                    """
                    INSERT INTO bss.boleto (
                        id_empresa, id_sindicato, mes_referencia,
                        qtd_trabalhadores, qtd_dependentes, valor_total,
                        banco, nosso_numero, status, tipo,
                        data_emissao, data_vencimento,
                        id_boleto_substituido
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, 'gerado', 'Sistema',
                        NOW(), %s,
                        %s
                    )
                    RETURNING id
                    """,
                    (v["id_empresa"], v["id_sindicato"], mes_amparo,
                     v["qtd_trabalhadores"], v["qtd_dependentes"], v["valor_total"],
                     v["banco"] or "itau50", nosso, venc,
                     id_boleto_velho),
                )
                id_novo = cur.fetchone()["id"]

                # Copia os itens do velho pro novo (snapshot mantido):
                cur.execute(
                    """
                    INSERT INTO bss.boleto_item
                        (id_boleto, id_trabalhador, id_sindicato,
                         mes_referencia, taxa_aplicada, eh_dependente)
                    SELECT %s, id_trabalhador, id_sindicato,
                           mes_referencia, taxa_aplicada, eh_dependente
                      FROM bss.boleto_item
                     WHERE id_boleto = %s
                    """,
                    (id_novo, id_boleto_velho),
                )

                # Cancela o velho:
                cur.execute(
                    """
                    UPDATE bss.boleto
                       SET status = 'cancelado',
                           motivo_cancelamento = COALESCE(motivo_cancelamento, '')
                                                 || CASE WHEN motivo_cancelamento IS NULL OR motivo_cancelamento = ''
                                                         THEN '' ELSE ' | ' END
                                                 || %s,
                           atualizado_em = NOW()
                     WHERE id = %s
                    """,
                    (f"Reemitido como boleto {id_novo} (nosso_numero {nosso})", id_boleto_velho),
                )

            conn.commit()
        except Exception:
            conn.rollback()
            raise

    return {
        "ok": True,
        "id_boleto_velho": id_boleto_velho,
        "id_boleto_novo":  id_novo,
        "nosso_numero":    nosso,
        "data_vencimento": venc.isoformat(),
    }
