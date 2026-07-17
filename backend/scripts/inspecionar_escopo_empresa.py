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
from app import boleto_repo, processo_repo, trabalhador_repo


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
                   -- CACHE copiado do legado (comentário do schema: "atualizado
                   -- por job"). É o número que a tela de Empresas mostra.
                   -- Se divergir do COUNT real abaixo, a tela está exibindo um
                   -- total que a própria base não sustenta.
                   e.qtd_trabalhadores_ativos                              AS cache_ativos,
                   (SELECT count(*) FROM bss.trabalhador t
                     WHERE t.id_empresa_atual = e.id)                    AS trab_total,
                   (SELECT count(*) FROM bss.trabalhador t
                     WHERE t.id_empresa_atual = e.id AND t.situacao = 'ativo')
                                                                         AS trab_ativos,
                   (SELECT count(*) FROM bss.boleto b
                     WHERE b.id_empresa = e.id)                          AS boletos,
                   -- O boleto_router força incluir_cancelados=False pro perfil
                   -- empresa (regra do épico #21). Então "quantos boletos
                   -- existem" e "quantos o cliente VÊ" são números diferentes,
                   -- e é o segundo que explica tela vazia.
                   (SELECT count(*) FROM bss.boleto b
                     WHERE b.id_empresa = e.id AND b.status <> 'cancelado')
                                                                         AS bol_visiveis,
                   (SELECT count(*) FROM bss.processo_beneficio p
                     WHERE p.id_empresa = e.id)                          AS processos
              FROM bss.empresa e
             WHERE e.id = ANY(%s)
             ORDER BY e.id
            """,
            (ids,),
        )
        linhas = cur.fetchall()

        cab = (f"{'id':>6}  {'cache':>6} {'ativos':>6} {'trab':>6} "
               f"{'boletos':>7} {'visív':>6} {'proc':>5}  razão social")
        print(cab)
        print("-" * len(cab))
        print("  cache  = e.qtd_trabalhadores_ativos (copiado do legado; é o que a tela mostra)")
        print("  ativos = COUNT real em bss.trabalhador WHERE id_empresa_atual = e.id")
        print("-" * len(cab))

        tot = {"cache_ativos": 0, "trab_ativos": 0, "trab_total": 0,
               "boletos": 0, "bol_visiveis": 0, "processos": 0}
        divergentes = []
        for r in linhas:
            marca = " ←padrão" if r["id"] == ids[0] else ""
            # A divergência é o achado: cache e realidade discordando.
            if r["cache_ativos"] != r["trab_ativos"]:
                marca = " ⚠" + marca
                divergentes.append(r)
            print(f"{r['id']:>6}  {r['cache_ativos']:>6} {r['trab_ativos']:>6} "
                  f"{r['trab_total']:>6} {r['boletos']:>7} {r['bol_visiveis']:>6} "
                  f"{r['processos']:>5}  {r['razao_social'][:34]}{marca}")
            for k in tot:
                tot[k] += r[k]

        print("-" * len(cab))
        print(f"{'TOTAL':>6}  {tot['cache_ativos']:>6} {tot['trab_ativos']:>6} "
              f"{tot['trab_total']:>6} {tot['boletos']:>7} {tot['bol_visiveis']:>6} "
              f"{tot['processos']:>5}")

        if divergentes:
            print(f"\n⚠ {len(divergentes)} empresa(s) com cache ≠ realidade.")
            print("  A tela de Empresas mostra o CACHE. O filtro de Trabalhadores")
            print("  usa o id_empresa_atual REAL. Por isso a tela diz '476' e a")
            print("  listagem vem vazia — os dois números vêm de fontes diferentes.")

        # Status dos boletos da empresa padrão — se 'visív' for 0 com 'boletos'
        # alto, é aqui que a resposta aparece.
        cur.execute(
            """
            SELECT status, count(*) AS qtd
              FROM bss.boleto
             WHERE id_empresa = %s
             GROUP BY status
             ORDER BY qtd DESC
            """,
            (ids[0],),
        )
        st = cur.fetchall()
        if st:
            print(f"\nBoletos da empresa padrão (id={ids[0]}) por status:")
            for r in st:
                print(f"  {r['status']:<15} {r['qtd']:>5}")

    # ------------------------------------------------------------------
    # O TESTE QUE IMPORTA
    # ------------------------------------------------------------------
    # Tudo acima conta a TABELA. A tela não chama a tabela — chama o REPO, que
    # lê VIEW, aplica filtros e paginação. Contar tabela e concluir sobre a tela
    # é o mesmo erro do protocolo: validar a fórmula no lugar errado.
    #
    # Aqui chamamos o repo com EXATAMENTE os argumentos que o router monta pro
    # perfil 'empresa'. Se der o número esperado, o backend está bom e o bug é
    # do frontend. Se der zero, o bug é aqui e o browser é inocente.
    print("\n" + "=" * 64)
    print("ESCOPO COMPLETO — como o router chama HOJE (ids_empresa = todas)")
    print("=" * 64)
    print("Isto é o que a tela deve mostrar sem nenhum filtro escolhido.")

    b = boleto_repo.listar(ids_empresa=ids, incluir_cancelados=False,
                           pagina=1, por_pagina=50)
    t = trabalhador_repo.listar(ids_empresa=ids, situacao="ativo",
                                pagina=1, por_pagina=50)
    p = processo_repo.listar(ids_empresa=ids, pagina=1, por_pagina=50)
    print(f"  boletos    (sem cancelados)   → total={b['total']:<6} linhas={len(b['linhas'])}")
    print(f"  trabalhad. (situacao='ativo') → total={t['total']:<6} linhas={len(t['linhas'])}")
    print(f"  processos                     → total={p['total']:<6} linhas={len(p['linhas'])}")

    if b["total"] == 0:
        # Se o escopo inteiro devolve zero boleto mas a contagem por empresa
        # achou centenas, o problema está DENTRO do boleto_repo — provavelmente
        # no `WHERE v.id_empresa IS NOT NULL` combinado com algo, ou na view.
        print("\n  ⚠ ZERO boletos no escopo inteiro. Comparando com a tabela crua:")
        with get_pg_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) AS na_tabela
                  FROM bss.boleto
                 WHERE id_empresa = ANY(%s) AND status <> 'cancelado'
                """,
                (ids,),
            )
            print(f"     bss.boleto  → {cur.fetchone()['na_tabela']}")
            cur.execute(
                """
                SELECT count(*) AS na_view
                  FROM bss.v_boleto
                 WHERE id_empresa = ANY(%s) AND status <> 'cancelado'
                """,
                (ids,),
            )
            print(f"     bss.v_boleto → {cur.fetchone()['na_view']}")
            print("     Se a view tiver menos que a tabela, o problema é o JOIN da view.")

    print("\n" + "=" * 64)
    print("EMPRESA A EMPRESA (o filtro opcional da tela)")
    print("=" * 64)

    for id_emp in ids:
        # boleto_router: empresa NUNCA vê cancelado (épico #21)
        b = boleto_repo.listar(id_empresa=id_emp, incluir_cancelados=False,
                               pagina=1, por_pagina=50)
        # trabalhador_router: a TELA manda situacao='ativo' (preset do f-preset)
        t_ativo = trabalhador_repo.listar(id_empresa=id_emp, situacao="ativo",
                                          pagina=1, por_pagina=50)
        # ...e sem preset, pra separar "não tem" de "o preset escondeu"
        t_todos = trabalhador_repo.listar(id_empresa=id_emp,
                                          pagina=1, por_pagina=50)
        p = processo_repo.listar(id_empresa=id_emp, pagina=1, por_pagina=50)

        print(f"\nempresa id={id_emp}")
        print(f"  boletos    (incluir_cancelados=False) → total={b['total']:<6} linhas={len(b['linhas'])}")
        print(f"  trabalhad. (situacao='ativo')         → total={t_ativo['total']:<6} linhas={len(t_ativo['linhas'])}")
        print(f"  trabalhad. (sem filtro)               → total={t_todos['total']:<6} linhas={len(t_todos['linhas'])}")
        print(f"  processos                             → total={p['total']:<6} linhas={len(p['linhas'])}")

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
