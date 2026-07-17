"""
Panorama dos usuários do BSS — quem existe, com que perfil, e quem consegue
de fato logar.

Uso (do diretório backend/):
    venv/bin/python -m scripts.inspecionar_usuarios            # panorama geral
    venv/bin/python -m scripts.inspecionar_usuarios maurofig   # + busca por email

POR QUE ISTO EXISTE
-------------------
Os 2.515 contatos vieram do legado pela sync com senha DELIBERADAMENTE
inutilizável (bcrypt de 32 bytes aleatórios — ver sync/contato.py). Eles
existem, têm perfil e vínculo corretos, e NENHUM consegue logar. Isso não é
defeito: as senhas do legado são cifra reversível e não podem ser herdadas
(ver migração 18).

Consequência prática: antes de qualquer demo, escolher os usuários e rodar
    venv/bin/python -m scripts.resetar_senha

Este script mostra o estado real sem precisar de psql (que não está no PATH
da OCI) nem de Python inline por ssh — que já quebrou três vezes tentando
sobreviver a PowerShell + ssh + bash + aspas.
"""

import sys

from app.database import get_pg_connection


def _linha(titulo: str) -> None:
    print(f"\n=== {titulo} " + "=" * max(0, 58 - len(titulo)))


def main() -> None:
    busca = sys.argv[1] if len(sys.argv) > 1 else None

    with get_pg_connection() as conn, conn.cursor() as cur:

        _linha("PERFIS")
        cur.execute(
            """
            SELECT perfil,
                   count(*)                            AS total,
                   count(*) FILTER (WHERE ativo)       AS ativos,
                   count(*) FILTER (WHERE tipo_cadastro = 'auto') AS autocadastro
              FROM bss_users
             GROUP BY perfil
             ORDER BY total DESC
            """
        )
        for r in cur.fetchall():
            print(f"  {r['perfil']:<15} total={r['total']:<6} "
                  f"ativos={r['ativos']:<6} autocadastro={r['autocadastro']}")

        _linha("ORIGEM")
        # id_legado_uuid preenchido = veio da sync = senha inutilizável.
        # NULL = criado aqui (criar_usuario.py ou autocadastro) = senha real.
        cur.execute(
            """
            SELECT CASE WHEN id_legado_uuid IS NULL
                        THEN 'nascido no BSS (senha utilizavel)'
                        ELSE 'veio do legado (senha INUTILIZAVEL)'
                   END AS origem,
                   count(*) AS total
              FROM bss_users
             GROUP BY 1
             ORDER BY 2 DESC
            """
        )
        for r in cur.fetchall():
            print(f"  {r['origem']:<40} {r['total']}")

        _linha("QUEM CONSEGUE LOGAR HOJE")
        cur.execute(
            """
            SELECT u.id, u.email, u.nome, u.perfil, u.ativo,
                   (SELECT count(*) FROM bss.usuario_empresa e
                     WHERE e.id_usuario = u.id) AS empresas,
                   (SELECT count(*) FROM bss.usuario_sindicato s
                     WHERE s.id_usuario = u.id) AS sindicatos
              FROM bss_users u
             WHERE u.id_legado_uuid IS NULL
             ORDER BY u.id
            """
        )
        linhas = cur.fetchall()
        if not linhas:
            print("  (nenhum — todo mundo veio do legado e precisa de reset)")
        for r in linhas:
            print(f"  id={r['id']:<5} {r['email']:<38} {r['perfil']:<14} "
                  f"ativo={str(r['ativo']):<5} emp={r['empresas']} sind={r['sindicatos']}")

        if busca:
            _linha(f"BUSCA: {busca}")
            cur.execute(
                """
                SELECT u.id, u.email, u.nome, u.perfil, u.ativo,
                       u.id_legado_uuid IS NOT NULL AS do_legado,
                       (SELECT count(*) FROM bss.usuario_empresa e
                         WHERE e.id_usuario = u.id) AS empresas
                  FROM bss_users u
                 WHERE u.email ILIKE %s OR u.nome ILIKE %s
                 ORDER BY u.id
                 LIMIT 30
                """,
                (f"%{busca}%", f"%{busca}%"),
            )
            achados = cur.fetchall()
            if not achados:
                print("  (nada encontrado)")
            for r in achados:
                senha = "INUTILIZAVEL (precisa reset)" if r["do_legado"] else "utilizavel"
                print(f"  id={r['id']:<5} {r['email']}")
                print(f"        nome={r['nome']!r} perfil={r['perfil']!r} "
                      f"ativo={r['ativo']} empresas={r['empresas']}")
                print(f"        senha: {senha}")

                # As empresas vinculadas importam pra demo: perfil 'empresa'
                # sem vínculo não enxerga nada, e hoje o backend só usa a
                # PRIMEIRA (usuario.empresas[0]) — não há dropdown de troca.
                if r["empresas"]:
                    cur.execute(
                        """
                        SELECT em.id, em.razao_social, em.cnpj
                          FROM bss.usuario_empresa ue
                          JOIN bss.empresa em ON em.id = ue.id_empresa
                         WHERE ue.id_usuario = %s
                         ORDER BY em.razao_social
                        """,
                        (r["id"],),
                    )
                    for e in cur.fetchall():
                        print(f"          → empresa id={e['id']} "
                              f"{e['razao_social']} ({e['cnpj']})")

    print()


if __name__ == "__main__":
    main()
