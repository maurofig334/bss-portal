"""
Extrai a estrutura do banco MySQL do SuiteCRM e gera 3 arquivos:

  1. schema_suitecrm.sql       — todos os CREATE TABLE (DDL completo)
  2. schema_suitecrm_resumo.md — relatório legível agrupando tabelas por categoria
  3. schema_suitecrm_dados.json — estrutura completa em JSON (pra processar depois)

USO:
  1. Instale dependências:
       pip install pymysql

  2. Defina as variáveis de ambiente do banco (ou edite o bloco DB_CONFIG abaixo):
       set MYSQL_HOST=ip-do-servidor.amazonaws.com
       set MYSQL_PORT=3306
       set MYSQL_DB=suitecrm
       set MYSQL_USER=usuario
       set MYSQL_PASSWORD=senha

  3. Rode:
       python extrair_schema_suitecrm.py

  Os 3 arquivos serão criados na mesma pasta do script.

OBS: Não copia DADOS. Só estrutura (DDL) e amostra (3 linhas por tabela).
     É leitura — não altera nada no SuiteCRM.
"""

import os
import json
from datetime import datetime
from pathlib import Path

try:
    import pymysql
    import pymysql.cursors
except ImportError:
    print("ERRO: instale pymysql primeiro: pip install pymysql")
    raise SystemExit(1)


# === Configuração ============================================================

DB_CONFIG = {
    "host":     os.getenv("MYSQL_HOST",     ""),
    "port":     int(os.getenv("MYSQL_PORT", "3306")),
    "database": os.getenv("MYSQL_DB",       ""),
    "user":     os.getenv("MYSQL_USER",     ""),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "charset":  "utf8mb4",
}

# Quantas linhas de amostra coletar de cada tabela (0 = nenhuma).
SAMPLE_ROWS = 3

# Nome dos arquivos de saída (mesmo diretório do script).
SCRIPT_DIR = Path(__file__).resolve().parent
OUT_SQL  = SCRIPT_DIR / "schema_suitecrm.sql"
OUT_MD   = SCRIPT_DIR / "schema_suitecrm_resumo.md"
OUT_JSON = SCRIPT_DIR / "schema_suitecrm_dados.json"


# === Padrões do SuiteCRM (heurísticas pra categorizar tabelas) ===============

def categorizar_tabela(nome: str) -> str:
    n = nome.lower()
    if n.endswith("_cstm"):
        return "🧩 Custom fields (par de uma tabela base)"
    if n.endswith("_audit"):
        return "📜 Auditoria (log de alterações)"
    if n.endswith("_files"):
        return "📎 Arquivos relacionados"
    if "relationships" in n or n.startswith("rel_"):
        return "🔗 Relacionamentos N-N"
    if n in (
        "users", "user_preferences", "roles", "acl_actions", "acl_roles",
        "acl_roles_actions", "acl_roles_users", "tracker", "sessions",
        "sugarfeed", "scheduler", "scheduler_logs", "config", "saved_search",
        "schedulers", "job_queue",
    ):
        return "⚙️  Sistema SuiteCRM (core)"
    if n.startswith("oauth"):
        return "🔑 OAuth / API"
    if n.startswith("inbound_email") or n.startswith("emails"):
        return "📧 E-mails"
    if n.startswith("aow_") or n.startswith("aok_") or n.startswith("aor_"):
        return "🤖 Workflow / Knowledge Base / Reports do SuiteCRM"
    return "🏢 Tabela de negócio (provável módulo)"


# === Extração ===============================================================

def conectar() -> pymysql.connections.Connection:
    if not DB_CONFIG["host"] or not DB_CONFIG["database"] or not DB_CONFIG["user"]:
        print("ERRO: configure MYSQL_HOST, MYSQL_DB, MYSQL_USER, MYSQL_PASSWORD")
        print("      como variáveis de ambiente, ou edite DB_CONFIG no script.")
        raise SystemExit(2)
    return pymysql.connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["database"],
        charset=DB_CONFIG["charset"],
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=15,
    )


def listar_tabelas(cur, schema: str) -> list[dict]:
    cur.execute(
        """
        SELECT TABLE_NAME AS name, TABLE_ROWS AS rows_estimate, ENGINE AS engine,
               TABLE_COLLATION AS collation, DATA_LENGTH + INDEX_LENGTH AS size_bytes
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = %s
        ORDER BY TABLE_NAME
        """,
        (schema,),
    )
    return cur.fetchall()


def colunas(cur, schema: str, tabela: str) -> list[dict]:
    cur.execute(
        """
        SELECT COLUMN_NAME AS name, COLUMN_TYPE AS type,
               IS_NULLABLE AS nullable, COLUMN_DEFAULT AS default_value,
               COLUMN_KEY AS key_type, EXTRA AS extra, COLUMN_COMMENT AS comment
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
        ORDER BY ORDINAL_POSITION
        """,
        (schema, tabela),
    )
    return cur.fetchall()


def indices(cur, schema: str, tabela: str) -> list[dict]:
    cur.execute(
        """
        SELECT INDEX_NAME AS name, COLUMN_NAME AS column_name,
               NON_UNIQUE AS non_unique, SEQ_IN_INDEX AS seq
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
        ORDER BY INDEX_NAME, SEQ_IN_INDEX
        """,
        (schema, tabela),
    )
    return cur.fetchall()


def fks(cur, schema: str, tabela: str) -> list[dict]:
    cur.execute(
        """
        SELECT CONSTRAINT_NAME AS name, COLUMN_NAME AS column_name,
               REFERENCED_TABLE_NAME AS ref_table, REFERENCED_COLUMN_NAME AS ref_column
        FROM information_schema.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
          AND REFERENCED_TABLE_NAME IS NOT NULL
        """,
        (schema, tabela),
    )
    return cur.fetchall()


def contar(cur, tabela: str) -> int:
    """Faz SELECT COUNT(*) — pode ser lento em tabelas gigantes."""
    try:
        cur.execute(f"SELECT COUNT(*) AS n FROM `{tabela}`")
        return cur.fetchone()["n"]
    except Exception:
        return -1


def sample(cur, tabela: str, n: int) -> list[dict]:
    if n <= 0:
        return []
    try:
        cur.execute(f"SELECT * FROM `{tabela}` LIMIT %s", (n,))
        return cur.fetchall()
    except Exception:
        return []


def ddl(cur, tabela: str) -> str:
    """Pega o CREATE TABLE como o MySQL geraria com SHOW CREATE TABLE."""
    cur.execute(f"SHOW CREATE TABLE `{tabela}`")
    row = cur.fetchone()
    # SHOW CREATE TABLE retorna como dict {'Table': nome, 'Create Table': ddl}
    for k, v in (row or {}).items():
        if k.lower().startswith("create"):
            return v + ";"
    return ""


# === Geração de saídas =======================================================

def gerar_sql(tabelas: list[dict]) -> str:
    linhas = [
        "-- =============================================================================",
        f"-- Schema SuiteCRM exportado em {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"-- Banco: {DB_CONFIG['database']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}",
        f"-- Total de tabelas: {len(tabelas)}",
        "-- =============================================================================",
        "",
    ]
    for t in tabelas:
        linhas.append(f"\n-- ----- {t['name']} -----")
        linhas.append(t.get("ddl", "-- (DDL não obtido)"))
    return "\n".join(linhas)


def gerar_md(tabelas: list[dict]) -> str:
    # Categoriza
    categorias: dict[str, list[dict]] = {}
    for t in tabelas:
        cat = categorizar_tabela(t["name"])
        categorias.setdefault(cat, []).append(t)

    total_rows = sum(int(t.get("count") or 0) for t in tabelas if t.get("count", -1) > 0)
    total_size_mb = sum(int(t.get("size_bytes") or 0) for t in tabelas) / (1024 * 1024)

    out = [
        "# Schema SuiteCRM — Relatório de Análise",
        "",
        f"- **Banco:** `{DB_CONFIG['database']}` @ `{DB_CONFIG['host']}:{DB_CONFIG['port']}`",
        f"- **Gerado em:** {datetime.now():%d/%m/%Y %H:%M:%S}",
        f"- **Total de tabelas:** {len(tabelas)}",
        f"- **Total de registros:** {total_rows:,}".replace(",", "."),
        f"- **Tamanho total:** {total_size_mb:,.1f} MB".replace(",", "."),
        "",
        "## Sumário por categoria",
        "",
        "| Categoria | Tabelas | Registros |",
        "|---|---:|---:|",
    ]
    for cat, ts in sorted(categorias.items(), key=lambda x: -len(x[1])):
        regs = sum(int(t.get("count") or 0) for t in ts if t.get("count", -1) > 0)
        out.append(
            f"| {cat} | {len(ts)} | {regs:,} |".replace(",", ".")
        )
    out.append("")

    for cat, ts in sorted(categorias.items()):
        out.append(f"\n---\n\n## {cat}\n")
        # Ordena por contagem desc
        ts_ord = sorted(ts, key=lambda t: -(int(t.get("count") or 0)))
        out.append("| Tabela | Registros | Tamanho | Colunas | Índices | FKs |")
        out.append("|---|---:|---:|---:|---:|---:|")
        for t in ts_ord:
            cnt = int(t.get("count") or 0)
            size_kb = int(t.get("size_bytes") or 0) / 1024
            tam = f"{size_kb/1024:.1f} MB" if size_kb > 1024 else f"{size_kb:.0f} KB"
            out.append(
                f"| `{t['name']}` | {cnt:,} | {tam} "
                f"| {len(t.get('cols', []))} | {len(t.get('idx', []))} | {len(t.get('fks', []))} |".replace(",", ".")
            )

    out.append("\n---\n\n## Detalhamento das tabelas de NEGÓCIO\n")
    out.append("(apenas tabelas categorizadas como 'Tabela de negócio')\n")
    for t in sorted(tabelas, key=lambda x: -(int(x.get("count") or 0))):
        if categorizar_tabela(t["name"]) != "🏢 Tabela de negócio (provável módulo)":
            continue
        cnt = int(t.get("count") or 0)
        out.append(f"\n### `{t['name']}` — {cnt:,} registros\n".replace(",", "."))
        out.append("**Colunas:**\n")
        out.append("| Nome | Tipo | Null | Chave | Default |")
        out.append("|---|---|---|---|---|")
        for c in t.get("cols", []):
            out.append(
                f"| `{c['name']}` | {c['type']} | {c['nullable']} "
                f"| {c['key_type'] or ''} | {c.get('default_value', '') or ''} |"
            )
        if t.get("idx"):
            out.append("\n**Índices:**\n")
            # Agrupa por nome de índice (composto pode ter várias colunas)
            por_idx: dict[str, list[dict]] = {}
            for i in t["idx"]:
                por_idx.setdefault(i["name"], []).append(i)
            for nome, cols in por_idx.items():
                cols_ord = sorted(cols, key=lambda c: c["seq"])
                cols_str = ", ".join(c["column_name"] for c in cols_ord)
                tipo = "UNIQUE" if not cols_ord[0]["non_unique"] else "INDEX"
                out.append(f"- `{nome}` ({tipo}): {cols_str}")
        if t.get("fks"):
            out.append("\n**Foreign Keys:**\n")
            for f in t["fks"]:
                out.append(
                    f"- `{f['column_name']}` → `{f['ref_table']}.{f['ref_column']}`"
                )

    return "\n".join(out)


def main() -> None:
    print("=" * 70)
    print("Extraindo schema do SuiteCRM...")
    print(f"  Host:     {DB_CONFIG['host']}:{DB_CONFIG['port']}")
    print(f"  Database: {DB_CONFIG['database']}")
    print(f"  User:     {DB_CONFIG['user']}")
    print("=" * 70)

    conn = conectar()
    schema = DB_CONFIG["database"]
    try:
        with conn.cursor() as cur:
            tabelas = listar_tabelas(cur, schema)
            print(f"✓ Encontradas {len(tabelas)} tabelas. Processando...\n")

            for i, t in enumerate(tabelas, 1):
                nome = t["name"]
                print(f"  [{i:3d}/{len(tabelas)}] {nome:50s} ", end="", flush=True)
                with conn.cursor() as c2:
                    t["cols"]   = colunas(c2, schema, nome)
                    t["idx"]    = indices(c2, schema, nome)
                    t["fks"]    = fks(c2, schema, nome)
                    t["count"]  = contar(c2, nome)
                    t["sample"] = sample(c2, nome, SAMPLE_ROWS)
                    t["ddl"]    = ddl(c2, nome)
                print(f"{int(t['count']):>10,} regs".replace(",", "."))

        # Saída
        print("\nGerando arquivos...")
        OUT_SQL.write_text(gerar_sql(tabelas), encoding="utf-8")
        print(f"  ✓ {OUT_SQL.name}  ({OUT_SQL.stat().st_size / 1024:.0f} KB)")

        OUT_MD.write_text(gerar_md(tabelas), encoding="utf-8")
        print(f"  ✓ {OUT_MD.name}  ({OUT_MD.stat().st_size / 1024:.0f} KB)")

        # JSON sem o sample (pode ser grande) e sem o DDL (já tá no .sql)
        dados_json = []
        for t in tabelas:
            dados_json.append({
                "name":      t["name"],
                "engine":    t.get("engine"),
                "rows_est":  t.get("rows_estimate"),
                "size":      t.get("size_bytes"),
                "count":     t.get("count"),
                "cols":      t.get("cols", []),
                "idx":       t.get("idx", []),
                "fks":       t.get("fks", []),
                "categoria": categorizar_tabela(t["name"]),
            })
        OUT_JSON.write_text(
            json.dumps(dados_json, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"  ✓ {OUT_JSON.name}  ({OUT_JSON.stat().st_size / 1024:.0f} KB)")

        print("\n" + "=" * 70)
        print("✓ EXTRAÇÃO CONCLUÍDA")
        print("=" * 70)
        print("Próximo passo: me envie o arquivo `schema_suitecrm_resumo.md`")
        print("(o .md é mais legível que o .sql; uso ele pra desenhar o modelo novo)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
