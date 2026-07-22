"""
Catálogo de variáveis dos modelos de e-mail + resolvedor.

O corpo de um modelo tem marcadores {{nome}}. Este módulo:
  1. DEFINE quais variáveis existem, o que cada uma significa e em que escopo
     faz sentido (VARIAVEIS);
  2. RESOLVE um modelo contra um contato ou empresa REAL, trocando os
     marcadores pelos valores (renderizar).

DECISÕES
--------
- Nomes limpos ({{empresa}}), não os $contact_..._c do SuiteCRM. O de-para pro
  cliente adaptar os textos antigos está em docs/MODELOS_EMAIL.md.
- Duas famílias de escopo, porque o destinatário muda o que existe:
    * 'contato' → uma PESSOA que administra N CNPJs. Pode listar várias
      empresas ("suas empresas inadimplentes").
    * 'empresa' → UM CNPJ. Fala de si mesmo; não conhece "contato_nome".
  Uma variável de escopo 'empresa' num modelo de contato (ou vice-versa) é
  marcada como órfã no preview, não resolvida silenciosamente pra vazio.
- Variável desconhecida ({{xyz}} que não existe no catálogo) também é órfã.
  Melhor gritar no preview do que mandar "{{xyz}}" pro cliente num envio real.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Callable

from .database import get_pg_connection


# Constantes institucionais. Ficam aqui e não no texto pra que, se o 0800
# mudar, um lugar só precise mudar — e todos os modelos acompanham.
BSS_TELEFONE = "0800 580 3816, opção 2, depois 5"
BSS_EMAIL = "financeiro@bssindical.com.br"


# ---------------------------------------------------------------------------
# Formatação
# ---------------------------------------------------------------------------

def _cnpj(v: str | None) -> str:
    d = re.sub(r"\D", "", v or "")
    if len(d) != 14:
        return v or ""
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def _moeda(v: Any) -> str:
    try:
        return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "R$ 0,00"


def _data(v: Any) -> str:
    if isinstance(v, (date,)):
        return v.strftime("%d/%m/%Y")
    return str(v or "")


def _tabela_texto(cabecalho: list[str], linhas: list[list[str]]) -> str:
    """
    Lista renderizada como tabela de texto (pipe-separated), no estilo do
    legado. Vira <table> no HTML só na hora do envio; no corpo editável e no
    preview fica texto, que é o que o cliente escreve e lê.
    """
    if not linhas:
        return "(nenhum registro)"
    out = [" | ".join(cabecalho)]
    out += [" | ".join(c) for c in linhas]
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Catálogo — cada variável sabe seu escopo, tipo e como se resolver
# ---------------------------------------------------------------------------
# escopo: 'contato' | 'empresa' | 'ambos'
# tipo:   'texto' | 'lista'
# fn:     recebe o contexto (dict montado por _montar_contexto) → string

VARIAVEIS: list[dict[str, Any]] = [
    # --- contato -------------------------------------------------------------
    {"nome": "contato_nome", "escopo": "contato", "tipo": "texto",
     "descricao": "Nome da pessoa que administra os CNPJs",
     "fn": lambda c: c.get("contato", {}).get("nome", "")},
    {"nome": "contato_email", "escopo": "contato", "tipo": "texto",
     "descricao": "E-mail do contato",
     "fn": lambda c: c.get("contato", {}).get("email", "")},
    {"nome": "contato_telefone", "escopo": "contato", "tipo": "texto",
     "descricao": "Telefone do contato",
     "fn": lambda c: c.get("contato", {}).get("telefone", "") or ""},

    # --- empresa (uma) -------------------------------------------------------
    {"nome": "empresa", "escopo": "empresa", "tipo": "texto",
     "descricao": "Razão social da empresa",
     "fn": lambda c: c.get("empresa", {}).get("razao_social", "")},
    {"nome": "cnpj", "escopo": "empresa", "tipo": "texto",
     "descricao": "CNPJ da empresa (formatado)",
     "fn": lambda c: _cnpj(c.get("empresa", {}).get("cnpj"))},
    {"nome": "empresa_cidade", "escopo": "empresa", "tipo": "texto",
     "descricao": "Cidade da empresa",
     "fn": lambda c: c.get("empresa", {}).get("cidade", "") or ""},
    {"nome": "empresa_uf", "escopo": "empresa", "tipo": "texto",
     "descricao": "UF da empresa",
     "fn": lambda c: c.get("empresa", {}).get("uf", "") or ""},

    # --- listas --------------------------------------------------------------
    {"nome": "lista_boletos_vencidos", "escopo": "ambos", "tipo": "lista",
     "descricao": "Tabela dos boletos vencidos (Empresa | CNPJ | Número | Vencimento | Valor)",
     "fn": lambda c: _tabela_texto(
         ["Empresa", "CNPJ", "Número", "Vencimento", "Valor"],
         [[b["empresa"] or "", _cnpj(b["empresa_cnpj"]), b["numero_boleto"] or "",
           _data(b["data_vencimento"]), _moeda(b["valor_total"])]
          for b in c.get("boletos_vencidos", [])])},
    {"nome": "lista_empresas_inadimplentes", "escopo": "contato", "tipo": "lista",
     "descricao": "Empresas do contato que estão inadimplentes (Empresa | CNPJ)",
     "fn": lambda c: _tabela_texto(
         ["Empresa", "CNPJ"],
         [[e["razao_social"] or "", _cnpj(e["cnpj"])]
          for e in c.get("empresas", []) if e.get("adimplencia") == "inadimplente"])},
    {"nome": "lista_empresas_irregulares", "escopo": "contato", "tipo": "lista",
     "descricao": "Empresas do contato que estão irregulares (Empresa | CNPJ)",
     "fn": lambda c: _tabela_texto(
         ["Empresa", "CNPJ"],
         [[e["razao_social"] or "", _cnpj(e["cnpj"])]
          for e in c.get("empresas", []) if e.get("regularidade") == "irregular"])},

    # --- constantes / sempre -------------------------------------------------
    {"nome": "bss_telefone", "escopo": "ambos", "tipo": "texto",
     "descricao": "Telefone da central da BSS", "fn": lambda c: BSS_TELEFONE},
    {"nome": "bss_email", "escopo": "ambos", "tipo": "texto",
     "descricao": "E-mail do financeiro da BSS", "fn": lambda c: BSS_EMAIL},
    {"nome": "data_hoje", "escopo": "ambos", "tipo": "texto",
     "descricao": "Data de hoje (dd/mm/aaaa)",
     "fn": lambda c: date.today().strftime("%d/%m/%Y")},
]

_POR_NOME: dict[str, dict] = {v["nome"]: v for v in VARIAVEIS}

# Marcadores {{ nome }} — tolera espaço interno: {{empresa}} e {{ empresa }}.
_RE_VAR = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def catalogo(destinatario: str | None = None) -> list[dict[str, Any]]:
    """
    Lista de variáveis pra paleta do editor. Filtra pelas que fazem sentido no
    destinatário: um modelo de empresa não mostra {{contato_nome}}.
    """
    def vale(v: dict) -> bool:
        if destinatario is None or v["escopo"] == "ambos":
            return True
        return v["escopo"] == destinatario
    return [
        {k: v[k] for k in ("nome", "escopo", "tipo", "descricao")}
        for v in VARIAVEIS if vale(v)
    ]


def variaveis_orfas(texto: str, destinatario: str) -> list[str]:
    """
    Marcadores {{x}} no texto que NÃO vão resolver: ou não existem no catálogo,
    ou existem mas em escopo incompatível com o destinatário.

    É o que o preview destaca — variável órfã vira lixo no e-mail do cliente.
    """
    orfas = []
    for nome in set(_RE_VAR.findall(texto)):
        v = _POR_NOME.get(nome)
        if v is None:
            orfas.append(nome)
        elif v["escopo"] != "ambos" and v["escopo"] != destinatario:
            orfas.append(nome)
    return sorted(orfas)


# ---------------------------------------------------------------------------
# Contexto — busca os dados reais uma vez, pra todas as variáveis usarem
# ---------------------------------------------------------------------------

def _montar_contexto(destinatario: str, id_contato: int | None,
                     id_empresa: int | None) -> dict[str, Any]:
    """
    Monta o dicionário de dados reais contra o qual as variáveis se resolvem.

    Faz as queries UMA vez aqui, e as lambdas do catálogo só leem o dict — em
    vez de cada variável ir ao banco (o que numa lista de 500 e-mails seria
    milhares de queries).
    """
    ctx: dict[str, Any] = {"contato": {}, "empresa": {}, "empresas": [],
                           "boletos_vencidos": []}

    with get_pg_connection() as conn, conn.cursor() as cur:
        if destinatario == "contato" and id_contato:
            cur.execute(
                "SELECT id, nome, email, telefone FROM bss_users WHERE id = %s",
                (id_contato,),
            )
            ctx["contato"] = cur.fetchone() or {}

            # Todas as empresas do contato (com adimplência/regularidade pras
            # listas filtrarem).
            cur.execute(
                """
                SELECT v.id, v.razao_social, v.cnpj, v.cidade, v.uf,
                       v.adimplencia, v.regularidade
                  FROM bss.usuario_empresa ue
                  JOIN bss.v_empresa v ON v.id = ue.id_empresa
                 WHERE ue.id_usuario = %s AND ue.ativo
                 ORDER BY v.razao_social
                """,
                (id_contato,),
            )
            ctx["empresas"] = list(cur.fetchall())
            ids = [e["id"] for e in ctx["empresas"]]
            ctx["boletos_vencidos"] = _boletos_vencidos(cur, ids)

        elif destinatario == "empresa" and id_empresa:
            cur.execute(
                """
                SELECT id, razao_social, cnpj, cidade, uf, adimplencia, regularidade
                  FROM bss.v_empresa WHERE id = %s
                """,
                (id_empresa,),
            )
            emp = cur.fetchone() or {}
            ctx["empresa"] = emp
            if emp:
                ctx["empresas"] = [emp]
                ctx["boletos_vencidos"] = _boletos_vencidos(cur, [emp["id"]])

    return ctx


def _boletos_vencidos(cur, ids_empresa: list[int]) -> list[dict]:
    if not ids_empresa:
        return []
    cur.execute(
        """
        SELECT numero_boleto, empresa, empresa_cnpj, data_vencimento, valor_total
          FROM bss.v_boleto
         WHERE id_empresa = ANY(%s) AND status = 'vencido'
         ORDER BY empresa, data_vencimento
        """,
        (ids_empresa,),
    )
    return list(cur.fetchall())


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def renderizar(assunto: str, corpo: str, destinatario: str,
               id_contato: int | None = None,
               id_empresa: int | None = None) -> dict[str, Any]:
    """
    Resolve assunto e corpo contra os dados reais. Retorna também as órfãs e
    quem foi o alvo, pra o preview mostrar o contexto usado.
    """
    ctx = _montar_contexto(destinatario, id_contato, id_empresa)

    def troca(texto: str) -> str:
        def _sub(m: re.Match) -> str:
            nome = m.group(1)
            v = _POR_NOME.get(nome)
            if v is None or (v["escopo"] != "ambos" and v["escopo"] != destinatario):
                return m.group(0)   # deixa o {{x}} visível — é órfã
            try:
                return v["fn"](ctx) or ""
            except Exception:
                return m.group(0)
        return _RE_VAR.sub(_sub, texto)

    alvo = ctx["contato"].get("nome") if destinatario == "contato" \
        else ctx["empresa"].get("razao_social")

    return {
        "assunto": troca(assunto or ""),
        "corpo": troca(corpo or ""),
        "orfas": sorted(set(variaveis_orfas(assunto, destinatario)
                            + variaveis_orfas(corpo, destinatario))),
        "alvo": alvo,
        "qtd_boletos_vencidos": len(ctx["boletos_vencidos"]),
    }
