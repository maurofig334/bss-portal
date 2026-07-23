"""
Sincroniza o CONTAS A PAGAR do legado → bss.pagamento.

    pagar_contas_a_pagar  (base: id UUID, name = protocolo/tipo)
    pagar_contas_a_pagar_cstm  (dados: valor, status, datas, beneficiário, banco)
    cases_pagar_contas_a_pagar_1_c  (junção pagar ↔ case/benefício)

Volume: ~10.554 pagar, ~3.926 benefícios com pagamento.

DECISÕES (todas medidas no legado, não assumidas — ver scripts/inspecionar_cpagar*.py)
--------------------------------------------------------------------------------
CHAVE: o id_legado_uuid é o `id` da tabela BASE. NÃO usar id_cpagar_c: ele é
  ZERO em todas as 10.554 linhas (campo morto). numero_pagamento fica NULL.

PARCELA: regra de negócio, não duplicação. Cada tipo de benefício paga em N
  parcelas conforme os parâmetros do sindicato (falecimento em 6, alguns em 11).
  Derivada por ROW_NUMBER() sobre o case, ordenada pela data prevista — o legado
  não guarda o número da parcela, guarda uma linha por parcela.

STATUS: status_c é 99,8% 'Aberto' mesmo em pagamentos antigos — NÃO é um sinal
  confiável de "foi pago". O sinal real é data_pagamento_c preenchida. Então:
      data_pagamento_c preenchida  → 'pago'   (a verdade, venha o status que vier)
      senão status_c = 'Pago'      → 'pago'   (os 17 casos explícitos)
      senão                        → 'pendente'
  ('Aberto'/'Gerado'/'Pendente' todos viram 'pendente'.)

DADOS BANCÁRIOS: o legado guarda conta do BENEFICIÁRIO e da EMPRESA em colunas
  separadas (_benef_c / _empresa_c). Viram linhas em bss.dados_bancarios com
  titular_tipo = 'beneficiario' / 'empresa'. Só grava a que tiver dado.
"""

from __future__ import annotations

from ..database import get_mysql_connection, get_pg_connection
from ._base import Progresso, mysql_iter, pg_executemany, parse_data, so_digitos, trim_or_none


# Uma linha por pagar, com o case a que pertence e o nº da parcela derivado.
# DISTINCT na junção por segurança (se houver vínculo duplicado, não infla).
SQL_LEGADO = """
    SELECT
        b.id                    AS uuid,
        j.case_id               AS uuid_processo,
        b.name                  AS nome,
        b.date_entered          AS criado_em,
        c.valor_c               AS valor,
        c.status_c              AS status_legado,
        c.forma_pagto_c         AS forma_pagto,
        c.documemto_c           AS documento,
        c.data_prevista_c       AS data_prevista,
        c.data_vencimento_c     AS data_vencimento,
        c.data_pagamento_c      AS data_pagamento,
        c.beneficiario_c        AS beneficiario_nome,
        c.cpf_c                 AS beneficiario_cpf,
        -- Conta do beneficiário:
        c.codigo_banco_benef_c  AS banco_benef,
        c.agencia_benef_c       AS agencia_benef,
        c.numero_conta_benef_c  AS conta_benef,
        c.digito_conta_benef_c  AS digito_benef,
        c.chave_pix_benef_c     AS pix_benef,
        -- Conta da empresa:
        c.codigo_banco_empresa_c AS banco_emp,
        c.agencia_empresa_c     AS agencia_emp,
        c.numero_conta_empresa_c AS conta_emp,
        c.digito_conta_empresa_c AS digito_emp,
        c.chave_pix_empresa_c   AS pix_emp,
        c.cnpj_empresa_c        AS cnpj_emp,
        c.tipo_conta_c          AS tipo_conta,
        ROW_NUMBER() OVER (
            PARTITION BY j.case_id
            ORDER BY c.data_prevista_c, c.data_vencimento_c, b.id
        )                       AS parcela
    FROM pagar_contas_a_pagar b
    JOIN pagar_contas_a_pagar_cstm c ON c.id_c = b.id
    JOIN (
        SELECT DISTINCT
               cases_pagar_contas_a_pagar_1cases_ida            AS case_id,
               cases_pagar_contas_a_pagar_1pagar_contas_a_pagar_idb AS pagar_id
          FROM cases_pagar_contas_a_pagar_1_c
         WHERE deleted = 0
    ) j ON j.pagar_id = b.id
    WHERE b.deleted = 0
"""


SQL_UPSERT = """
    INSERT INTO bss.pagamento (
        id_legado_uuid, id_processo, parcela, documento, valor,
        forma_pagamento, status, data_prevista, data_vencimento, data_pagamento,
        beneficiario_nome, beneficiario_cpf, criado_em
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (id_legado_uuid) WHERE id_legado_uuid IS NOT NULL DO UPDATE
        SET id_processo       = EXCLUDED.id_processo,
            parcela           = EXCLUDED.parcela,
            documento         = EXCLUDED.documento,
            valor             = EXCLUDED.valor,
            forma_pagamento   = EXCLUDED.forma_pagamento,
            status            = EXCLUDED.status,
            data_prevista     = EXCLUDED.data_prevista,
            data_vencimento   = EXCLUDED.data_vencimento,
            data_pagamento    = EXCLUDED.data_pagamento,
            beneficiario_nome = EXCLUDED.beneficiario_nome,
            beneficiario_cpf  = EXCLUDED.beneficiario_cpf,
            atualizado_em     = NOW()
"""


# forma_pagto_c → forma_pagamento (valores limpos)
MAPA_FORMA = {
    "pixtrans": "pix",
    "cartao":   "cartao",
}


def _status(status_legado, data_pagamento) -> str:
    """data_pagamento manda; status_c só como reforço. Ver docstring do módulo."""
    if data_pagamento:
        return "pago"
    if (status_legado or "").strip().lower() == "pago":
        return "pago"
    return "pendente"


def _forma(v) -> str | None:
    if not v:
        return None
    return MAPA_FORMA.get(str(v).strip().lower(), str(v).strip().lower()[:30])


def _carregar_processo_map(pg_conn) -> dict[str, int]:
    """uuid do case → id do processo no BSS."""
    m: dict[str, int] = {}
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT id, id_legado_uuid FROM bss.processo_beneficio "
            "WHERE id_legado_uuid IS NOT NULL"
        )
        for r in cur:
            m[r["id_legado_uuid"]] = r["id"]
    return m


def sync(dry_run: bool = False, limite: int | None = None) -> int:
    print(f"\n=== Sync CONTAS A PAGAR ({'dry-run' if dry_run else 'gravação'}) ===")

    with get_pg_connection() as pg, get_mysql_connection() as my:
        proc_map = _carregar_processo_map(pg)
        print(f"  {len(proc_map):,} processos mapeados por id_legado_uuid")

        prog = Progresso(limite or 10554, "pagamento")
        orfaos = 0        # pagar cujo case não existe no BSS
        rows: list[tuple] = []

        def gerar():
            nonlocal orfaos
            n = 0
            for r in mysql_iter(my, SQL_LEGADO):
                id_processo = proc_map.get(r["uuid_processo"])
                if id_processo is None:
                    # Pagar de um benefício que não veio (ou veio sem uuid).
                    # Não inventa vínculo — conta e segue.
                    orfaos += 1
                    prog.tick()
                    continue

                yield (
                    r["uuid"],
                    id_processo,
                    int(r["parcela"] or 1),
                    trim_or_none(r["documento"], 255),
                    r["valor"] or 0,
                    _forma(r["forma_pagto"]),
                    _status(r["status_legado"], r["data_pagamento"]),
                    parse_data(r["data_prevista"]),
                    parse_data(r["data_vencimento"]),
                    parse_data(r["data_pagamento"]),
                    trim_or_none(r["beneficiario_nome"], 255),
                    so_digitos(r["beneficiario_cpf"]),
                    parse_data(r["criado_em"]),
                )
                prog.tick()
                n += 1
                if limite and n >= limite:
                    break

        if dry_run:
            total = sum(1 for _ in gerar())
        else:
            total = pg_executemany(pg, SQL_UPSERT, gerar())

        prog.fim()
        print(f"  {total:,} pagamentos sincronizados")
        print(f"  {orfaos:,} órfãos (case sem processo no BSS) — ignorados")

    return total


if __name__ == "__main__":
    sync(dry_run=True, limite=100)
