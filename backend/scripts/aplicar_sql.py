"""
Aplica um arquivo .sql no PostgreSQL do BSS usando a conexão do próprio app.

Existe porque o `psql` não está no PATH da máquina Windows do Mauro — e a venv
do projeto já tem psycopg + as credenciais do .env. Assim as migrations rodam
com um comando só, sem depender do cliente do PostgreSQL instalado.

As migrations do BSS são idempotentes (DO blocks / ON CONFLICT), então rodar
duas vezes é seguro.

Uso (do diretório backend/, com venv ativa):
    python -m scripts.aplicar_sql scripts/10_tipo_beneficio_documento_seed.sql
"""

import sys
from pathlib import Path

from app.config import settings
from app.database import get_pg_connection


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python -m scripts.aplicar_sql <arquivo.sql>")
        sys.exit(1)

    caminho = Path(sys.argv[1])
    if not caminho.exists():
        print(f"ERRO: arquivo não encontrado: {caminho}")
        sys.exit(1)

    sql = caminho.read_text(encoding="utf-8")
    print("=" * 72)
    print(f"Aplicando: {caminho.name}  ({len(sql):,} bytes)")
    print(f"Destino:   {settings.PG_USER}@{settings.PG_HOST}:{settings.PG_PORT}/{settings.PG_DB}")
    print("=" * 72)

    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            # Se o script terminar com um SELECT, mostra o resultado:
            try:
                if cur.description:
                    linhas = cur.fetchall()
                    for r in linhas:
                        print("  ", r)
            except Exception:
                pass
        conn.commit()

    print("\n[OK] Aplicado e commitado.")


if __name__ == "__main__":
    main()
