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


def _derivar_estado_tipo(arquivos: list[dict[str, Any]]) -> tuple[str, bool]:
    """
    Deriva o estado de um TIPO de documento a partir dos arquivos anexados.

    Regra confirmada com o cliente (01/07/2026), espelhando o legado — que só
    tem status por ARQUIVO, nunca por tipo:

        aprovado    ≥1 arquivo aceito   → trava o upload no portal (não pode
                                          substituir documento já aceito)
        rejeitado   nenhum aceito + ≥1 rejeitado → libera reenvio, mostra motivo
        pendente    só arquivos em análise
        nao_enviado nenhum arquivo

    Arquivos rejeitados antigos PERMANECEM como histórico — por isso um tipo
    com [rejeitado 06/04, aceito 26/06] está aprovado, e frente+verso (dois
    aceitos no mesmo tipo) também.

    Retorna (estado, bloqueado).
    """
    if not arquivos:
        return ("nao_enviado", False)
    if any(a.get("status") == "aprovado" for a in arquivos):
        return ("aprovado", True)
    if any(a.get("status") == "rejeitado" for a in arquivos):
        return ("rejeitado", False)
    return ("pendente", False)


def listar_documentos(id_processo: int, id_tipo_beneficio: int | None) -> list[dict[str, Any]]:
    """
    CHECKLIST de documentos do processo.

    Cruza a REGRA (bss.tipo_beneficio_documento — o que o tipo de benefício
    exige) com TODOS os arquivos anexados (bss.processo_documento). Um tipo
    pode ter N arquivos convivendo: reenvios após rejeição E páginas distintas
    do mesmo documento (ex.: frente e verso do RG, ambos aceitos).

    Retorna uma linha por TIPO, com os arquivos aninhados em `arquivos` e o
    estado derivado por _derivar_estado_tipo().

    Ordem: pela `ordem` da regra (obrigatórios primeiro, 'Outros' por último);
    arquivos dentro do tipo, por versão.
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
          LEFT JOIN bss.processo_documento pd
                 ON pd.id_processo = %(id_processo)s
                AND pd.id_tipo_documento = tbd.id
          LEFT JOIN bss.motivo_rejeicao_documento mr ON mr.id = pd.id_motivo_rejeicao
          LEFT JOIN bss.documento d ON d.id = pd.id_documento
         WHERE tbd.id_tipo_beneficio = %(id_tipo)s
           AND tbd.ativo
         ORDER BY tbd.ordem, tbd.nome, pd.versao
    """
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"id_processo": id_processo, "id_tipo": id_tipo_beneficio})
            linhas = cur.fetchall()

    # Agrupa por tipo, aninhando os arquivos
    tipos: dict[int, dict[str, Any]] = {}
    for r in linhas:
        tid = r["id_tipo_documento"]
        if tid not in tipos:
            tipos[tid] = {
                "id_tipo_documento": tid,
                "codigo": r["codigo"],
                "nome": r["nome"],
                "obrigatorio": r["obrigatorio"],
                "ordem": r["ordem"],
                "arquivos": [],
            }
        # LEFT JOIN sem anexo devolve a linha do tipo com tudo NULL:
        if r["id_processo_documento"] is not None:
            tipos[tid]["arquivos"].append({
                "id": r["id_processo_documento"],
                "status": r["status"],
                "versao": r["versao"],
                "observacao": r["observacao"],
                "avaliado_em": r["avaliado_em"],
                "motivo_rejeicao_codigo": r["motivo_rejeicao_codigo"],
                "motivo_rejeicao": r["motivo_rejeicao"],
                "nome_original": r["nome_original"],
                "arquivo_url": r["arquivo_url"],
                "mime_type": r["mime_type"],
                "tamanho_bytes": r["tamanho_bytes"],
                "enviado_em": r["enviado_em"],
            })

    resultado = []
    for t in tipos.values():
        estado, bloqueado = _derivar_estado_tipo(t["arquivos"])
        t["estado"] = estado
        t["bloqueado"] = bloqueado
        t["qtd_arquivos"] = len(t["arquivos"])
        resultado.append(t)
    resultado.sort(key=lambda x: (x["ordem"], x["nome"]))
    return resultado


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
