"""
Investiga os e-mails repetidos em contacts_cstm.username_c.

POR QUÊ
-------
O Mauro explicou que o SuiteCRM só aceita 1 empresa por contato, e a saída foi
criar o MESMO contato N vezes, cada cópia com uma empresa — o "bacalhau".
Baseado nisso, o sync consolida por e-mail e SOMA os vínculos.

Mas a conferência pós-sync mostrou algo estranho:
    anapaula.brito@audtecgestao.com.br (5 cópias no legado)
    → virou 1 pessoa com 1 empresa (esperado: 5)
    → e com o nome "RENATA CRISTINA TAMANAHA GARCIA"

Nome diferente do e-mail sugere que talvez NÃO sejam a mesma pessoa duplicada,
e sim pessoas diferentes compartilhando um login (comum em escritório contábil).
Se for isso, a fusão está juntando gente distinta — e é bug, não cura.

Este script mostra, pra cada e-mail repetido: os nomes, as empresas de cada
cópia e as datas. Aí dá pra ver se é bacalhau (mesma pessoa, empresas
diferentes) ou pessoas distintas (nomes diferentes, mesma ou várias empresas).

READ-ONLY. Uso (do diretório backend/, com venv ativa):
    python -m scripts.inspecionar_email_duplicado
    python -m scripts.inspecionar_email_duplicado anapaula.brito@audtecgestao.com.br
"""

import sys

from app.database import get_mysql_connection


SQL_DETALHE = """
    SELECT c.id,
           c.first_name, c.last_name,
           c.date_entered,
           c.phone_mobile,
           cc.username_c,
           cc.enable_portal_c,
           c.lock_portal_user,
           a.id            AS uuid_empresa,
           a.name          AS empresa,
           acc.cnpj_c      AS cnpj
      FROM contacts c
      JOIN contacts_cstm cc ON cc.id_c = c.id
      LEFT JOIN accounts_contacts ac ON ac.contact_id = c.id AND ac.deleted = 0
      LEFT JOIN accounts a           ON a.id = ac.account_id AND a.deleted = 0
      LEFT JOIN accounts_cstm acc    ON acc.id_c = a.id
     WHERE c.deleted = 0
       AND LOWER(TRIM(cc.username_c)) = %s
     ORDER BY c.date_entered
"""

SQL_TOP_DUPS = """
    SELECT LOWER(TRIM(cc.username_c)) AS email,
           COUNT(DISTINCT c.id)                          AS copias,
           COUNT(DISTINCT CONCAT(COALESCE(c.first_name,''),' ',
                                 COALESCE(c.last_name,''))) AS nomes_distintos,
           COUNT(DISTINCT ac.account_id)                 AS empresas_distintas
      FROM contacts c
      JOIN contacts_cstm cc ON cc.id_c = c.id
      LEFT JOIN accounts_contacts ac ON ac.contact_id = c.id AND ac.deleted = 0
     WHERE c.deleted = 0
       AND cc.tipocontato_c = 'EMPRESA'
       AND cc.username_c IS NOT NULL AND TRIM(cc.username_c) <> ''
     GROUP BY LOWER(TRIM(cc.username_c))
    HAVING COUNT(DISTINCT c.id) > 1
     ORDER BY copias DESC
     LIMIT 20
"""


def main() -> None:
    alvo = sys.argv[1].strip().lower() if len(sys.argv) > 1 else None

    with get_mysql_connection() as conn:
        with conn.cursor() as cur:
            print("=" * 78)
            print("E-mails repetidos: é bacalhau (mesma pessoa) ou gente diferente?")
            print("=" * 78)
            print("\ncopias = registros de contato · nomes = nomes distintos")
            print("empresas = empresas distintas ligadas\n")
            print(f"  {'email':45s} {'copias':>6} {'nomes':>6} {'empresas':>9}")
            print("  " + "-" * 70)
            cur.execute(SQL_TOP_DUPS)
            for r in cur.fetchall():
                # nomes>1 → pessoas diferentes no mesmo login (NÃO é bacalhau)
                # nomes=1 e empresas>1 → bacalhau clássico
                marca = ""
                if r["nomes_distintos"] > 1:
                    marca = "  << nomes diferentes!"
                print(f"  {r['email'][:45]:45s} {r['copias']:>6} "
                      f"{r['nomes_distintos']:>6} {r['empresas_distintas']:>9}{marca}")

            alvos = [alvo] if alvo else ["anapaula.brito@audtecgestao.com.br"]
            for email in alvos:
                print(f"\n{'=' * 78}\nDetalhe de {email}\n{'=' * 78}")
                cur.execute(SQL_DETALHE, (email,))
                linhas = cur.fetchall()
                if not linhas:
                    print("  (não encontrado)")
                    continue
                for r in linhas:
                    nome = f"{r['first_name'] or ''} {r['last_name'] or ''}".strip()
                    print(f"  contato {r['id'][:8]}… · {r['date_entered']}")
                    print(f"      nome    : {nome}")
                    print(f"      empresa : {r['empresa']}  (cnpj {r['cnpj']})")
                    print(f"      portal  : enable={r['enable_portal_c']} lock={r['lock_portal_user']}")

    print("\n" + "=" * 78)
    print("LEITURA:")
    print("  nomes=1 e empresas>1  → bacalhau: consolidar por e-mail está CERTO")
    print("  nomes>1               → pessoas diferentes no mesmo login:")
    print("                          consolidar FUNDE GENTE DISTINTA — é bug")
    print("=" * 78)


if __name__ == "__main__":
    main()
