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


def buscar_detalhe(id_processo: int) -> dict[str, Any] | None:
    """
    Detalhe completo do processo pra tela de detalhe (#22).

    v_processo já resolve empresa/sindicato/trabalhador/tipo/status; aqui
    complementamos com os campos que a view não expõe (endereço e telefone do
    beneficiário, valores, causa mortis) e anexamos os dados bancários.
    """
    sql = """
        SELECT v.*,
               p.beneficiario_telefone,
               p.beneficiario_data_nasc,
               p.beneficiario_endereco_logradouro,
               p.beneficiario_endereco_numero,
               p.beneficiario_endereco_complemento,
               p.beneficiario_endereco_bairro,
               p.beneficiario_endereco_cidade,
               p.beneficiario_endereco_uf,
               p.beneficiario_endereco_cep,
               p.valor_solicitado,
               p.valor_aprovado,
               p.qtd_parcelas,
               p.causa_mortis,
               p.situacao_acionamento,
               p.bloqueio_motivo,
               p.id_legado_uuid
          FROM bss.v_processo v
          JOIN bss.processo_beneficio p ON p.id = v.id
         WHERE v.id = %s
    """
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (id_processo,))
            row = cur.fetchone()
            if not row:
                return None
            cur.execute(
                "SELECT * FROM bss.dados_bancarios WHERE id_processo = %s "
                "ORDER BY id LIMIT 1",
                (id_processo,),
            )
            row["dados_bancarios"] = cur.fetchone()
    return row


def listar_documentos(id_processo: int, id_tipo_beneficio: int | None) -> list[dict[str, Any]]:
    """
    CHECKLIST de documentos do processo.

    Cruza a REGRA (bss.tipo_beneficio_documento — o que o tipo de benefício
    exige) com o ANEXADO (bss.processo_documento — a versão mais recente de
    cada tipo). Um documento nunca anexado vem com status NULL, o que a UI
    mostra como pendente de envio.

    Ordem: pela `ordem` da regra (obrigatórios primeiro, 'Outros' por último).
    """
    if not id_tipo_beneficio:
        return []
    sql = """
        SELECT tbd.id           AS id_tipo_documento,
               tbd.codigo,
               tbd.nome,
               tbd.obrigatorio,
               tbd.ordem,
               pd.id            AS id_processo_documento,
               pd.status,
               pd.versao,
               pd.observacao,
               pd.avaliado_em,
               mr.codigo        AS motivo_rejeicao_codigo,
               mr.nome          AS motivo_rejeicao,
               d.nome_original,
               d.arquivo_url,
               d.mime_type,
               d.tamanho_bytes,
               d.criado_em      AS enviado_em
          FROM bss.tipo_beneficio_documento tbd
          LEFT JOIN LATERAL (
              SELECT x.*
                FROM bss.processo_documento x
               WHERE x.id_processo = %(id_processo)s
                 AND x.id_tipo_documento = tbd.id
               ORDER BY x.versao DESC
               LIMIT 1
          ) pd ON TRUE
          LEFT JOIN bss.motivo_rejeicao_documento mr ON mr.id = pd.id_motivo_rejeicao
          LEFT JOIN bss.documento d ON d.id = pd.id_documento
         WHERE tbd.id_tipo_beneficio = %(id_tipo)s
           AND tbd.ativo
         ORDER BY tbd.ordem, tbd.nome
    """
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"id_processo": id_processo, "id_tipo": id_tipo_beneficio})
            return list(cur.fetchall())


def listar_pagamentos(id_processo: int) -> list[dict[str, Any]]:
    """Parcelas de contas a pagar do processo (aba de relacionamento)."""
    sql = """
        SELECT id, numero_pagamento, parcela, valor, forma_pagamento, status,
               data_prevista, data_vencimento, data_pagamento,
               beneficiario_nome, documento
          FROM bss.pagamento
         WHERE id_processo = %s
         ORDER BY parcela, id
    """
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (id_processo,))
            return list(cur.fetchall())


def listar_mensagens(id_processo: int, incluir_internas: bool = True) -> list[dict[str, Any]]:
    """
    Mensagens do processo (canal cliente ↔ analista).
    `interno=TRUE` é visível só pro staff — o portal do cliente não mostra.
    """
    sql = """
        SELECT id, titulo, corpo, interno, id_usuario, criado_em
          FROM bss.processo_mensagem
         WHERE id_processo = %s
    """
    if not incluir_internas:
        sql += " AND interno = FALSE"
    sql += " ORDER BY criado_em ASC"
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (id_processo,))
            return list(cur.fetchall())
