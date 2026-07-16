"""
Sincroniza documentos de processo:
    documents + documents_cases + document_revisions  →  bss.documento
                                                      →  bss.processo_documento

Volume: ~21.5k vínculos (documents_cases), 99,7% com categoria preenchida.

O QUE VEM E O QUE NÃO VEM
-------------------------
Vem: metadado (nome, arquivo, mime), a CATEGORIA (= tipo de documento) e o
STATUS de aprovação, com o motivo da rejeição.

NÃO vem: o BINÁRIO. Os arquivos ficam no filesystem do servidor da aplicação
SuiteCRM (AWS), ao qual não temos acesso — o único canal com a AWS é a conexão
de banco. Por isso `arquivo_url` recebe um PONTEIRO (legado://...) que deverá
ser trocado pela chave real do storage quando os arquivos forem extraídos
(via HTTP no entryPoint=download, único caminho possível). Isso é
pré-requisito do Big Bang: desligar o legado antes de extrair = perder os
arquivos.

MAPEAMENTO DE STATUS (documents.status_id → processo_documento)
---------------------------------------------------------------
    em_analise / pendente / Active  → 'pendente'
    aceito / conforme               → 'aprovado'   (trava upload no portal)
    Dados_Incorretos                → 'rejeitado' + motivo 'invalido'
    Ilegivel                        → 'rejeitado' + motivo 'ilegivel'
    Rasurado                        → 'rejeitado' + motivo 'rasura'

VERSÃO
------
Um tipo pode ter N arquivos convivendo: reenvios após rejeição E páginas
distintas (frente/verso, ambas aceitas). `versao` é só um sequencial por
(processo × categoria) ordenado por data — NÃO é a chave de idempotência.
A chave é id_legado_uuid (migration 12).
"""

from __future__ import annotations

from ..database import get_mysql_connection, get_pg_connection
from ._base import Progresso, mysql_iter, pg_executemany, trim_or_none


# Traz só documentos ligados a processo (documents_cases).
# ROW_NUMBER dá o sequencial de versão por (processo × categoria).
SQL_LEGADO = """
    SELECT
        d.id                AS uuid,
        dc.case_id          AS uuid_processo,
        d.document_name     AS nome,
        d.category_id       AS categoria,
        d.status_id         AS status_legado,
        d.description       AS descricao,
        d.date_entered      AS criado_em,
        dr.id               AS uuid_revisao,
        dr.filename         AS filename,
        dr.file_mime_type   AS mime_type,
        ROW_NUMBER() OVER (
            PARTITION BY dc.case_id, d.category_id
            ORDER BY d.date_entered, d.id
        )                   AS versao
    FROM documents_cases dc
    JOIN documents d
      ON d.id = dc.document_id AND d.deleted = 0
    LEFT JOIN document_revisions dr
      ON dr.id = d.document_revision_id
    WHERE dc.deleted = 0
"""


SQL_UPSERT_DOC = """
    INSERT INTO bss.documento (
        id_legado_uuid, nome_original, arquivo_url, mime_type,
        entidade_tipo, entidade_id, categoria, descricao, criado_em
    )
    VALUES (%s, %s, %s, %s, 'processo', %s, %s, %s, %s)
    ON CONFLICT (id_legado_uuid) DO UPDATE
        SET nome_original = EXCLUDED.nome_original,
            arquivo_url   = EXCLUDED.arquivo_url,
            mime_type     = EXCLUDED.mime_type,
            entidade_id   = EXCLUDED.entidade_id,
            categoria     = EXCLUDED.categoria,
            descricao     = EXCLUDED.descricao
"""

SQL_UPSERT_PDOC = """
    INSERT INTO bss.processo_documento (
        id_legado_uuid, id_processo, id_tipo_documento, id_documento,
        versao, status, id_motivo_rejeicao, observacao, criado_em, atualizado_em
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (id_legado_uuid) DO UPDATE
        SET id_processo        = EXCLUDED.id_processo,
            id_tipo_documento  = EXCLUDED.id_tipo_documento,
            id_documento       = EXCLUDED.id_documento,
            versao             = EXCLUDED.versao,
            status             = EXCLUDED.status,
            id_motivo_rejeicao = EXCLUDED.id_motivo_rejeicao,
            observacao         = EXCLUDED.observacao,
            atualizado_em      = NOW()
"""


# documents.status_id → (status BSS, codigo do motivo de rejeição)
MAPA_STATUS: dict[str, tuple[str, str | None]] = {
    "em_analise":       ("pendente", None),
    "pendente":         ("pendente", None),
    "Active":           ("pendente", None),   # default do SuiteCRM (7 linhas)
    "aceito":           ("aprovado", None),
    "conforme":         ("aprovado", None),   # 1 linha
    "Dados_Incorretos": ("rejeitado", "invalido"),
    "Ilegivel":         ("rejeitado", "ilegivel"),
    "Rasurado":         ("rejeitado", "rasura"),
}


def _carregar_processo_map(pg_conn) -> dict[str, tuple[int, int | None]]:
    """uuid case → (id_processo, id_tipo_beneficio)."""
    m: dict[str, tuple[int, int | None]] = {}
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT id, id_legado_uuid, id_tipo_beneficio FROM bss.processo_beneficio "
            "WHERE id_legado_uuid IS NOT NULL"
        )
        for r in cur:
            m[r["id_legado_uuid"]] = (r["id"], r["id_tipo_beneficio"])
    return m


def _carregar_tipo_doc_map(pg_conn) -> dict[tuple[int, str], int]:
    """(id_tipo_beneficio, codigo) → id_tipo_documento. codigo == category_id do legado."""
    m: dict[tuple[int, str], int] = {}
    with pg_conn.cursor() as cur:
        cur.execute("SELECT id, id_tipo_beneficio, codigo FROM bss.tipo_beneficio_documento WHERE ativo")
        for r in cur:
            m[(r["id_tipo_beneficio"], r["codigo"])] = r["id"]
    return m


def _carregar_motivo_map(pg_conn) -> dict[str, int]:
    m: dict[str, int] = {}
    with pg_conn.cursor() as cur:
        cur.execute("SELECT id, codigo FROM bss.motivo_rejeicao_documento")
        for r in cur:
            m[r["codigo"]] = r["id"]
    return m


def _carregar_documento_map(pg_conn) -> dict[str, int]:
    """uuid documento legado → id em bss.documento (pra ligar processo_documento)."""
    m: dict[str, int] = {}
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT id, id_legado_uuid FROM bss.documento "
            "WHERE id_legado_uuid IS NOT NULL AND entidade_tipo = 'processo'"
        )
        for r in cur:
            m[r["id_legado_uuid"]] = r["id"]
    return m


def _ponteiro_arquivo(linha: dict) -> str:
    """
    arquivo_url provisório. O binário ainda está no servidor do SuiteCRM (AWS,
    sem acesso). Guardamos o id da revisão, que é o nome do arquivo em upload/
    e também o parâmetro do entryPoint=download — assim a extração futura já
    tem tudo que precisa.
    """
    rev = linha.get("uuid_revisao")
    return f"legado://document_revision/{rev}" if rev else f"legado://document/{linha['uuid']}"


def sync(dry_run: bool = False, limite: int | None = None) -> int:
    print(f"\n=== Sync DOCUMENTO (processo) ({'dry-run' if dry_run else 'gravação'}) ===")

    with get_pg_connection() as pg_conn:
        proc_map = _carregar_processo_map(pg_conn)
        tipo_doc_map = _carregar_tipo_doc_map(pg_conn)
        motivo_map = _carregar_motivo_map(pg_conn)
    print(f"  ✓ {len(proc_map)} processos, {len(tipo_doc_map)} regras de documento, "
          f"{len(motivo_map)} motivos em memória")

    sql = SQL_LEGADO + (f" LIMIT {int(limite)}" if limite else "")

    # ---------- Passada 1: bss.documento ----------
    prog1 = Progresso(total=None, nome="documento")
    pulados_proc = 0
    pulados_tipo: dict[str, int] = {}
    linhas_cache: list[dict] = []

    with get_mysql_connection() as mysql_conn:
        def doc_iter():
            nonlocal pulados_proc
            for linha in mysql_iter(mysql_conn, sql, batch_size=2000):
                prog1.tick()
                dados = proc_map.get(linha.get("uuid_processo"))
                if not dados:
                    pulados_proc += 1
                    continue
                id_processo, _ = dados
                linhas_cache.append(linha)
                if dry_run and prog1.contador <= 3:
                    print(f"  amostra: cat={linha.get('categoria')} "
                          f"status={linha.get('status_legado')} v{linha.get('versao')} "
                          f"arq={linha.get('filename')}")
                yield (
                    linha["uuid"],
                    trim_or_none(linha.get("filename") or linha.get("nome"), 255) or "sem-nome",
                    _ponteiro_arquivo(linha),
                    trim_or_none(linha.get("mime_type"), 100),
                    id_processo,
                    trim_or_none(linha.get("categoria"), 50),
                    linha.get("descricao"),
                    linha.get("criado_em"),
                )

        if dry_run:
            for _ in doc_iter():
                pass
        else:
            with get_pg_connection() as pg_conn:
                pg_executemany(pg_conn, SQL_UPSERT_DOC, doc_iter(), batch_size=1000)
    prog1.fim()

    if dry_run:
        print(f"  (dry-run) {len(linhas_cache)} documento(s) seriam gravados")
        if pulados_proc:
            print(f"  ⚠ {pulados_proc} sem processo correspondente no BSS")
        return prog1.contador

    # ---------- Passada 2: bss.processo_documento ----------
    print("  ligando processo_documento (resolvendo ids de documento)...")
    with get_pg_connection() as pg_conn:
        doc_map = _carregar_documento_map(pg_conn)
    print(f"  ✓ {len(doc_map)} documentos em memória")

    prog2 = Progresso(total=len(linhas_cache), nome="processo_documento")
    sem_regra = 0

    def pdoc_iter():
        nonlocal sem_regra
        for linha in linhas_cache:
            prog2.tick()
            id_processo, id_tipo_beneficio = proc_map[linha["uuid_processo"]]
            categoria = (linha.get("categoria") or "").strip()
            id_tipo_documento = tipo_doc_map.get((id_tipo_beneficio, categoria))
            if not id_tipo_documento:
                # Categoria sem regra pro tipo do processo (ou categoria vazia).
                # Não inventamos regra: fica só em bss.documento, fora do checklist.
                sem_regra += 1
                pulados_tipo[categoria or "(vazia)"] = pulados_tipo.get(categoria or "(vazia)", 0) + 1
                continue
            id_documento = doc_map.get(linha["uuid"])
            status, motivo_cod = MAPA_STATUS.get(
                (linha.get("status_legado") or "").strip(), ("pendente", None)
            )
            yield (
                linha["uuid"],
                id_processo,
                id_tipo_documento,
                id_documento,
                int(linha.get("versao") or 1),
                status,
                motivo_map.get(motivo_cod) if motivo_cod else None,
                linha.get("descricao"),
                linha.get("criado_em"),
                linha.get("criado_em"),
            )

    with get_pg_connection() as pg_conn:
        pg_executemany(pg_conn, SQL_UPSERT_PDOC, pdoc_iter(), batch_size=1000)
    prog2.fim()

    if pulados_proc:
        print(f"  ⚠ {pulados_proc} documento(s) sem processo correspondente no BSS")
    if sem_regra:
        print(f"  ⚠ {sem_regra} documento(s) sem regra pro tipo do processo "
              f"(ficam em bss.documento, fora do checklist):")
        for cat, n in sorted(pulados_tipo.items(), key=lambda x: -x[1])[:10]:
            print(f"      {cat:35s} {n:>6,}")
    return prog2.contador
