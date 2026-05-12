"""
Atualiza os caches qtd_trabalhadores_*  em bss.sindicato e bss.empresa,
recalculando a partir de bss.trabalhador (fonte da verdade).

Caches afetados:
  bss.sindicato.qtd_trabalhadores_ativos     = COUNT (todos ativos no sindicato)
  bss.sindicato.qtd_trabalhadores_inativos   = COUNT (todos inativos no sindicato)
  bss.empresa.qtd_trabalhadores_ativos       = COUNT (titulares ativos na empresa)
  bss.empresa.qtd_trabalhadores_inativos     = COUNT (titulares inativos na empresa)
  bss.empresa.qtd_dependentes_ativos         = COUNT (dependentes ativos na empresa)

Uso:
    python -m scripts.reconciliar_qtd_trabalhadores
    python -m scripts.reconciliar_qtd_trabalhadores --dry-run

NÃO interfere em trabalhadores ou outras tabelas. Idempotente.
"""

from __future__ import annotations

import argparse

from app.database import get_pg_connection


# Regra de "inativo" (replica o validar_qtd_trabalhadores.py):
#   situacao IN ('inativo','desligado','demitido')

SQL_SINDICATO = """
    UPDATE bss.sindicato s
       SET qtd_trabalhadores_ativos   = COALESCE(c.real_ativos, 0),
           qtd_trabalhadores_inativos = COALESCE(c.real_inativos, 0),
           atualizado_em              = NOW()
      FROM (
        SELECT id_sindicato_atual AS id_sindicato,
               COUNT(*) FILTER (WHERE situacao = 'ativo')                              AS real_ativos,
               COUNT(*) FILTER (WHERE situacao IN ('inativo','desligado','demitido'))  AS real_inativos
          FROM bss.trabalhador
         WHERE id_sindicato_atual IS NOT NULL
         GROUP BY id_sindicato_atual
      ) c
     WHERE s.id = c.id_sindicato
       AND (s.qtd_trabalhadores_ativos   <> COALESCE(c.real_ativos, 0)
         OR s.qtd_trabalhadores_inativos <> COALESCE(c.real_inativos, 0))
    RETURNING s.id
"""

# Sindicatos que ficaram sem trabalhador algum precisam zerar:
SQL_SINDICATO_ZERAR = """
    UPDATE bss.sindicato s
       SET qtd_trabalhadores_ativos   = 0,
           qtd_trabalhadores_inativos = 0,
           atualizado_em              = NOW()
     WHERE NOT EXISTS (
        SELECT 1 FROM bss.trabalhador t
         WHERE t.id_sindicato_atual = s.id
     )
     AND (s.qtd_trabalhadores_ativos <> 0 OR s.qtd_trabalhadores_inativos <> 0)
    RETURNING s.id
"""

SQL_EMPRESA = """
    UPDATE bss.empresa e
       SET qtd_trabalhadores_ativos   = COALESCE(c.titulares_ativos, 0),
           qtd_trabalhadores_inativos = COALESCE(c.titulares_inativos, 0),
           qtd_dependentes_ativos     = COALESCE(c.deps_ativos, 0),
           atualizado_em              = NOW()
      FROM (
        SELECT id_empresa_atual AS id_empresa,
               COUNT(*) FILTER (WHERE situacao = 'ativo'  AND titularidade = 'titular')    AS titulares_ativos,
               COUNT(*) FILTER (WHERE situacao IN ('inativo','desligado','demitido')
                                 AND titularidade = 'titular')                              AS titulares_inativos,
               COUNT(*) FILTER (WHERE situacao = 'ativo'  AND titularidade = 'dependente') AS deps_ativos
          FROM bss.trabalhador
         WHERE id_empresa_atual IS NOT NULL
         GROUP BY id_empresa_atual
      ) c
     WHERE e.id = c.id_empresa
       AND (e.qtd_trabalhadores_ativos   <> COALESCE(c.titulares_ativos, 0)
         OR e.qtd_trabalhadores_inativos <> COALESCE(c.titulares_inativos, 0)
         OR e.qtd_dependentes_ativos     <> COALESCE(c.deps_ativos, 0))
    RETURNING e.id
"""

SQL_EMPRESA_ZERAR = """
    UPDATE bss.empresa e
       SET qtd_trabalhadores_ativos   = 0,
           qtd_trabalhadores_inativos = 0,
           qtd_dependentes_ativos     = 0,
           atualizado_em              = NOW()
     WHERE NOT EXISTS (
        SELECT 1 FROM bss.trabalhador t
         WHERE t.id_empresa_atual = e.id
     )
     AND (e.qtd_trabalhadores_ativos   <> 0
       OR e.qtd_trabalhadores_inativos <> 0
       OR e.qtd_dependentes_ativos     <> 0)
    RETURNING e.id
"""


def main(dry_run: bool = False) -> None:
    print(f"=== Reconciliar qtd_trabalhadores ({'DRY-RUN' if dry_run else 'GRAVANDO'}) ===")

    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            print("\n[1/4] Sindicatos — atualizando caches a partir da contagem real...")
            cur.execute(SQL_SINDICATO)
            sind_atualizados = len(cur.fetchall())
            print(f"      {sind_atualizados:,} sindicato(s) com diff atualizados")

            print("\n[2/4] Sindicatos — zerando os que ficaram sem trabalhador...")
            cur.execute(SQL_SINDICATO_ZERAR)
            sind_zerados = len(cur.fetchall())
            print(f"      {sind_zerados:,} sindicato(s) zerados")

            print("\n[3/4] Empresas — atualizando caches (titulares/dependentes)...")
            cur.execute(SQL_EMPRESA)
            emp_atualizadas = len(cur.fetchall())
            print(f"      {emp_atualizadas:,} empresa(s) com diff atualizadas")

            print("\n[4/4] Empresas — zerando as que ficaram sem trabalhador...")
            cur.execute(SQL_EMPRESA_ZERAR)
            emp_zeradas = len(cur.fetchall())
            print(f"      {emp_zeradas:,} empresa(s) zeradas")

        if dry_run:
            print("\n→ DRY-RUN: ROLLBACK (nada foi salvo).")
            conn.rollback()
        else:
            conn.commit()
            print("\n→ COMMIT: alterações salvas.")

    # Resumo final (sempre lê, mesmo em dry-run mostra estado pós-rollback = original)
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    (SELECT SUM(qtd_trabalhadores_ativos)   FROM bss.sindicato) AS sind_ativos,
                    (SELECT SUM(qtd_trabalhadores_inativos) FROM bss.sindicato) AS sind_inativos,
                    (SELECT SUM(qtd_trabalhadores_ativos)   FROM bss.empresa)   AS emp_titulares_ativos,
                    (SELECT SUM(qtd_trabalhadores_inativos) FROM bss.empresa)   AS emp_titulares_inativos,
                    (SELECT SUM(qtd_dependentes_ativos)     FROM bss.empresa)   AS emp_deps_ativos,
                    (SELECT COUNT(*) FROM bss.trabalhador WHERE situacao = 'ativo')              AS trab_ativos,
                    (SELECT COUNT(*) FROM bss.trabalhador
                      WHERE situacao IN ('inativo','desligado','demitido'))                       AS trab_inativos
            """)
            r = cur.fetchone()
    print("\n=== ESTADO FINAL DOS CACHES ===")
    print(f"  bss.sindicato:  SUM ativos = {r['sind_ativos']:>10,}   SUM inativos = {r['sind_inativos']:>10,}")
    print(f"  bss.empresa:    SUM titulares ativos = {r['emp_titulares_ativos']:>10,}")
    print(f"                  SUM titulares inativos = {r['emp_titulares_inativos']:>10,}")
    print(f"                  SUM dependentes ativos = {r['emp_deps_ativos']:>10,}")
    print(f"  bss.trabalhador (fonte):  total ativos = {r['trab_ativos']:>10,}  total inativos = {r['trab_inativos']:>10,}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Calcula mas não grava")
    args = parser.parse_args()
    main(args.dry_run)
