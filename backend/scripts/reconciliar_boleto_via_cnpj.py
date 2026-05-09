"""
Reconcilia bss.boleto.id_empresa puxando CNPJ do legado SuiteCRM.

A migração inicial pulou id_empresa (não havia esse campo no SuiteCRM —
o vínculo era por CNPJ em bolet_boletos_cstm.cnpj_empresa_c). Esse script:

  1. Lista bss.boleto com id_empresa IS NULL e id_legado_uuid preenchido
  2. Busca em massa cnpj_empresa_c em bolet_boletos_cstm
  3. Normaliza CNPJ (só dígitos)
  4. Faz match com bss.empresa.cnpj (também normalizado)
  5. UPDATE em batch

Roda na OCI (precisa de acesso ao MySQL legado RDS):
    cd /home/opc/bss-portal/backend
    source venv/bin/activate
    python -m scripts.reconciliar_boleto_via_cnpj

Idempotente — só atualiza quem ainda tem id_empresa NULL.
"""

from app.database import get_mysql_connection, get_pg_connection


BATCH_LOOKUP = 5000   # quantos UUIDs por consulta no MySQL
BATCH_UPDATE = 1000   # quantos UPDATEs por executemany no Postgres


def so_digitos(s: str | None) -> str:
    if not s:
        return ""
    return "".join(c for c in s if c.isdigit())


def main() -> None:
    # 1) Lista boletos órfãos no Postgres
    print("[1/4] Listando boletos órfãos no Postgres…")
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, id_legado_uuid
                  FROM bss.boleto
                 WHERE id_empresa IS NULL
                   AND id_legado_uuid IS NOT NULL
            """)
            boletos = cur.fetchall()
    print(f"      {len(boletos):,} boletos a reconciliar")
    if not boletos:
        return

    uuids = [b["id_legado_uuid"] for b in boletos]
    map_id_uuid = {b["id_legado_uuid"]: b["id"] for b in boletos}

    # 2) Busca CNPJ no MySQL em batches
    print(f"[2/4] Buscando CNPJ no MySQL legado em batches de {BATCH_LOOKUP}…")
    cnpj_por_uuid: dict[str, str] = {}
    with get_mysql_connection() as my_conn:
        with my_conn.cursor() as my_cur:
            for i in range(0, len(uuids), BATCH_LOOKUP):
                chunk = uuids[i:i + BATCH_LOOKUP]
                placeholders = ",".join(["%s"] * len(chunk))
                my_cur.execute(
                    f"""
                    SELECT id_c, cnpj_empresa_c
                      FROM bolet_boletos_cstm
                     WHERE id_c IN ({placeholders})
                       AND cnpj_empresa_c IS NOT NULL
                    """,
                    chunk,
                )
                for r in my_cur.fetchall():
                    digs = so_digitos(r["cnpj_empresa_c"])
                    if digs:
                        cnpj_por_uuid[r["id_c"]] = digs
                print(f"      {min(i + BATCH_LOOKUP, len(uuids)):,}/{len(uuids):,} (achou {len(cnpj_por_uuid):,} com CNPJ)")
    print(f"      Total com CNPJ no legado: {len(cnpj_por_uuid):,}")

    # 3) Map CNPJ → id_empresa no Postgres
    print("[3/4] Mapeando CNPJ → id_empresa no bss.empresa…")
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, cnpj FROM bss.empresa WHERE cnpj IS NOT NULL")
            emp_por_cnpj: dict[str, int] = {}
            for r in cur.fetchall():
                digs = so_digitos(r["cnpj"])
                if digs:
                    emp_por_cnpj[digs] = r["id"]
    print(f"      {len(emp_por_cnpj):,} empresas no BSS com CNPJ")

    # 4) Calcula updates
    print("[4/4] Calculando updates…")
    updates: list[tuple[int, int]] = []  # (id_empresa, id_boleto)
    sem_cnpj_no_legado = 0
    cnpj_sem_match = 0
    cnpjs_sem_match: set[str] = set()
    for uuid, id_boleto in map_id_uuid.items():
        cnpj = cnpj_por_uuid.get(uuid)
        if not cnpj:
            sem_cnpj_no_legado += 1
            continue
        id_emp = emp_por_cnpj.get(cnpj)
        if not id_emp:
            cnpj_sem_match += 1
            cnpjs_sem_match.add(cnpj)
            continue
        updates.append((id_emp, id_boleto))

    print(f"      A atualizar:                     {len(updates):,}")
    print(f"      Sem cnpj_empresa_c no legado:    {sem_cnpj_no_legado:,}")
    print(f"      CNPJ não bate com bss.empresa:   {cnpj_sem_match:,} ({len(cnpjs_sem_match):,} CNPJs distintos)")

    if not updates:
        return

    # Roda em batches pra não estourar o WAL
    print(f"      Aplicando em batches de {BATCH_UPDATE}…")
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            for i in range(0, len(updates), BATCH_UPDATE):
                chunk = updates[i:i + BATCH_UPDATE]
                cur.executemany(
                    "UPDATE bss.boleto SET id_empresa = %s, atualizado_em = NOW() WHERE id = %s",
                    chunk,
                )
                conn.commit()
                print(f"      {min(i + BATCH_UPDATE, len(updates)):,}/{len(updates):,}")
    print("      OK — UPDATE concluído.")

    # Estatísticas finais
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FILTER (WHERE id_empresa IS NULL)     AS sem_empresa,
                       COUNT(*) FILTER (WHERE id_empresa IS NOT NULL) AS com_empresa
                  FROM bss.boleto
            """)
            r = cur.fetchone()
    print()
    print("=" * 60)
    print(f"FINAL: sem_empresa={r['sem_empresa']:,}, com_empresa={r['com_empresa']:,}")
    print("=" * 60)


if __name__ == "__main__":
    main()
