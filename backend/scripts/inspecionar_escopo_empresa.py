"""
Mostra, para cada empresa vinculada a um usuário, quanto dado existe de fato.

Uso (do diretório backend/):
    venv/bin/python -m scripts.inspecionar_escopo_empresa maurofig334@gmail.com

POR QUE ISTO EXISTE
-------------------
Quando a tela de Trabalhadores/Benefícios/Boletos vem vazia pro perfil
'empresa', existem duas explicações completamente diferentes:

  1. BUG   — o filtro está errado e escondendo dado que existe;
  2. DADO  — a empresa selecionada realmente não tem nada, e a tela está certa.

Chutar entre as duas custa caro. Este script responde com número: pra cada
empresa do usuário, quantos trabalhadores, boletos e processos existem no BSS.
Se der tudo zero, o problema não está no filtro.

Também imprime qual empresa o backend escolhe como padrão (usuario.empresas[0],
agora ordenado por id em auth._carregar_vinculos) — que é o que a tela mostra
quando o frontend não manda id_empresa.
"""

import sys

from app.database import get_pg_connection


def main() -> None:
    if len(sys.argv) < 2:
        print("uso: python -m scripts.inspecionar_escopo_empresa <email>")
        return
    email = sys.argv[1].strip().lower()

    with get_pg_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, nome, perfil FROM bss_users WHERE email = %s", (email,)
        )
        user = cur.fetchone()
        if not user:
            print(f"✗ usuário '{email}' não encontrado")
            return
        print(f"\nUsuário id={user['id']} {user['nome']!r} perfil={user['perfil']!r}")

        # Mesma query do auth._carregar_vinculos, ORDER BY incluso:
        # o primeiro da lista é o que o backend usa como padrão.
        cur.execute(
            "SELECT id_empresa FROM bss.usuario_empresa "
            " WHERE id_usuario = %s AND ativo "
            " ORDER BY id_empresa",
            (user["id"],),
        )
        ids = [r["id_empresa"] for r in cur.fetchall()]
        if not ids:
            print("✗ nenhuma empresa vinculada — o usuário não veria nada")
            return

        print(f"Vínculos ativos: {len(ids)}")
        print(f"Padrão do backend (empresas[0]): id={ids[0]}\n")

        cur.execute(
            """
            SELECT e.id,
                   e.razao_social,
                   e.cnpj,
                   e.status,
                   (SELECT count(*) FROM bss.trabalhador t
                     WHERE t.id_empresa_atual = e.id)                    AS trab_total,
                   (SELECT count(*) FROM bss.trabalhador t
                     WHERE t.id_empresa_atual = e.id AND t.situacao = 'ativo')
                                                                         AS trab_ativos,
                   (SELECT count(*) FROM bss.boleto b
                     WHERE b.id_empresa = e.id)                          AS boletos,
                   (SELECT count(*) FROM bss.processo_beneficio p
                     WHERE p.id_empresa = e.id)                          AS processos
              FROM bss.empresa e
             WHERE e.id = ANY(%s)
             ORDER BY e.id
            """,
            (ids,),
        )
        linhas = cur.fetchall()

        cab = f"{'id':>6}  {'trab':>6} {'ativos':>6} {'boletos':>7} {'proc':>5}  razão social"
        print(cab)
        print("-" * len(cab))
        tot = {"trab_total": 0, "trab_ativos": 0, "boletos": 0, "processos": 0}
        for r in linhas:
            marca = " ←padrão" if r["id"] == ids[0] else ""
            print(f"{r['id']:>6}  {r['trab_total']:>6} {r['trab_ativos']:>6} "
                  f"{r['boletos']:>7} {r['processos']:>5}  "
                  f"{r['razao_social'][:45]}{marca}")
            for k in tot:
                tot[k] += r[k]

        print("-" * len(cab))
        print(f"{'TOTAL':>6}  {tot['trab_total']:>6} {tot['trab_ativos']:>6} "
              f"{tot['boletos']:>7} {tot['processos']:>5}")

        # A tela de Trabalhadores abre com o preset situacao='ativo'. Uma
        # empresa com 500 trabalhadores INATIVOS aparece vazia — e está certa.
        if tot["trab_ativos"] == 0 and tot["trab_total"] > 0:
            print("\n⚠ Nenhum trabalhador ATIVO em nenhuma das empresas.")
            print("  A tela abre com o preset situacao='ativo' — vazia é o esperado.")
        if tot["trab_total"] == 0 and tot["boletos"] == 0 and tot["processos"] == 0:
            print("\n⚠ Zero em tudo: as telas vazias estão CORRETAS.")
            print("  O usuário está vinculado a empresas sem movimento no BSS.")

    print()


if __name__ == "__main__":
    main()
