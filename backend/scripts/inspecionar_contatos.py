"""
Mapeia CONTATOS (usuários externos) e o vínculo com EMPRESAS no legado —
base pro módulo de Autocadastro e pra modelagem de Contatos no BSS.

CONTEXTO
--------
O Autocadastro (portal.beneficiosocialsindical.com.br/cadastro) coleta
CNPJ + e-mail + aceite de termo. O fluxo, confirmado com o Mauro (01/07/2026):
    CNPJ existe na base? SIM → cadastrante vira SEGUNDO gestor → OP aprova
                         NÃO → consulta RFB → cria empresa → 1º gestor → OP aprova
Ou seja: um CNPJ tem N gestores, um gestor tem N CNPJs. No SuiteCRM, esses
gestores são os `contacts`, ligados às empresas por um campo customizado de
CNPJ (informação do Mauro).

PERGUNTAS QUE ESTE SCRIPT RESPONDE
----------------------------------
1. Como é `contacts` + `contacts_cstm`? Onde está o CNPJ?
2. O vínculo contato↔empresa é por campo de CNPJ, por N-N (accounts_contacts),
   ou pelos dois? Qual manda?
3. Qual a distribuição real de CNPJs por contato? (prova o N:N)
4. `accounts`/`accounts_cstm` têm: tipo de cadastro (auto x interno), dados da
   RFB (situação cadastral, CNAE), e-mail, fila/status de aprovação?
5. Existe registro do ACEITE DO TERMO (quem, quando, versão)?

READ-ONLY. Uso (do diretório backend/, com venv ativa):
    python -m scripts.inspecionar_contatos
"""

from app.database import get_mysql_connection
from app.config import settings


def secao(t: str) -> None:
    print(f"\n{'-' * 76}\n{t}\n{'-' * 76}")


def colunas(cur, tabela: str) -> list[dict]:
    cur.execute(
        """
        SELECT COLUMN_NAME, COLUMN_TYPE
          FROM information_schema.COLUMNS
         WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
         ORDER BY ORDINAL_POSITION
        """,
        (settings.MYSQL_DB, tabela),
    )
    return cur.fetchall()


def existe(cur, tabela: str) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
        (settings.MYSQL_DB, tabela),
    )
    return cur.fetchone() is not None


def distintos(cur, tabela: str, coluna: str, limite: int = 12) -> None:
    try:
        cur.execute(
            f"SELECT {coluna} AS v, COUNT(*) AS n FROM {tabela} "
            f"WHERE deleted = 0 GROUP BY {coluna} ORDER BY n DESC LIMIT {limite}"
        )
        for r in cur.fetchall():
            print(f"      {str(r['v'])[:45]:45s} {r['n']:>7,}")
    except Exception as e:
        print(f"      (erro: {e})")


def main() -> None:
    print("=" * 76)
    print(f"CONTATOS e vínculo com EMPRESAS — base do Autocadastro ({settings.MYSQL_DB})")
    print("=" * 76)

    with get_mysql_connection() as conn:
        with conn.cursor() as cur:

            # ---------------------------------------------------------------
            # 1. Estrutura
            # ---------------------------------------------------------------
            for t in ("contacts", "contacts_cstm"):
                secao(f"Tabela: {t}")
                if not existe(cur, t):
                    print("  (não existe)")
                    continue
                cols = colunas(cur, t)
                cur.execute(f"SELECT COUNT(*) n FROM {t}")
                print(f"  {len(cols)} colunas · {cur.fetchone()['n']:,} registros")
                for c in cols:
                    print(f"    {c['COLUMN_NAME']:40s} {c['COLUMN_TYPE']}")

            # ---------------------------------------------------------------
            # 2. Onde está o CNPJ nos contatos?
            # ---------------------------------------------------------------
            secao("Colunas com cara de CNPJ / empresa / termo / cadastro")
            cur.execute(
                """
                SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE
                  FROM information_schema.COLUMNS
                 WHERE TABLE_SCHEMA = %s
                   AND TABLE_NAME IN ('contacts','contacts_cstm','accounts','accounts_cstm')
                   AND (COLUMN_NAME LIKE '%%cnpj%%'  OR COLUMN_NAME LIKE '%%empresa%%'
                     OR COLUMN_NAME LIKE '%%termo%%' OR COLUMN_NAME LIKE '%%aceit%%'
                     OR COLUMN_NAME LIKE '%%cadastr%%' OR COLUMN_NAME LIKE '%%tipo%%'
                     OR COLUMN_NAME LIKE '%%situacao%%' OR COLUMN_NAME LIKE '%%cnae%%'
                     OR COLUMN_NAME LIKE '%%atividade%%' OR COLUMN_NAME LIKE '%%rfb%%'
                     OR COLUMN_NAME LIKE '%%receita%%' OR COLUMN_NAME LIKE '%%aprov%%'
                     OR COLUMN_NAME LIKE '%%status%%' OR COLUMN_NAME LIKE '%%email%%'
                     OR COLUMN_NAME LIKE '%%estado%%' OR COLUMN_NAME LIKE '%%ip%%')
                 ORDER BY TABLE_NAME, COLUMN_NAME
                """,
                (settings.MYSQL_DB,),
            )
            for r in cur.fetchall():
                print(f"    {r['TABLE_NAME']:16s}.{r['COLUMN_NAME']:36s} {r['COLUMN_TYPE']}")

            # ---------------------------------------------------------------
            # 3. Amostra de contatos ativos
            # ---------------------------------------------------------------
            secao("Amostra: 5 contatos (campos preenchidos)")
            try:
                cur.execute(
                    """
                    SELECT c.id, c.first_name, c.last_name, c.date_entered, cc.*
                      FROM contacts c
                      LEFT JOIN contacts_cstm cc ON cc.id_c = c.id
                     WHERE c.deleted = 0
                     ORDER BY c.date_entered DESC
                     LIMIT 5
                    """
                )
                for r in cur.fetchall():
                    print("    " + "-" * 60)
                    for k, v in r.items():
                        if v is None:
                            continue
                        s = str(v).strip()
                        if s and s not in ("0", "0.00"):
                            print(f"      {k:36s} = {s[:55]}")
            except Exception as e:
                print(f"    (erro: {e})")

            # ---------------------------------------------------------------
            # 4. A PERGUNTA CENTRAL: quantos CNPJs por contato?
            # ---------------------------------------------------------------
            secao("N:N — tabela de relacionamento accounts_contacts")
            if existe(cur, "accounts_contacts"):
                cur.execute("SELECT COUNT(*) n FROM accounts_contacts WHERE deleted = 0")
                print(f"  vínculos ativos: {cur.fetchone()['n']:,}")
                cur.execute(
                    """
                    SELECT qtd_empresas, COUNT(*) AS contatos FROM (
                        SELECT contact_id, COUNT(DISTINCT account_id) AS qtd_empresas
                          FROM accounts_contacts WHERE deleted = 0
                         GROUP BY contact_id
                    ) x GROUP BY qtd_empresas ORDER BY qtd_empresas
                    """
                )
                print("\n  distribuição de EMPRESAS por CONTATO:")
                for r in cur.fetchall():
                    print(f"      {r['qtd_empresas']:>3} empresa(s) → {r['contatos']:>6,} contato(s)")
                cur.execute(
                    """
                    SELECT qtd_contatos, COUNT(*) AS empresas FROM (
                        SELECT account_id, COUNT(DISTINCT contact_id) AS qtd_contatos
                          FROM accounts_contacts WHERE deleted = 0
                         GROUP BY account_id
                    ) x GROUP BY qtd_contatos ORDER BY qtd_contatos
                    """
                )
                print("\n  distribuição de CONTATOS por EMPRESA (gestores por CNPJ):")
                for r in cur.fetchall():
                    print(f"      {r['qtd_contatos']:>3} contato(s) → {r['empresas']:>6,} empresa(s)")
            else:
                print("  (accounts_contacts não existe — o vínculo deve ser só por CNPJ)")

            # ---------------------------------------------------------------
            # 5. accounts_cstm: tipo de cadastro, RFB, aprovação
            # ---------------------------------------------------------------
            secao("accounts_cstm: valores das colunas de cadastro/situação")
            if existe(cur, "accounts_cstm"):
                for c in colunas(cur, "accounts_cstm"):
                    nome = c["COLUMN_NAME"].lower()
                    if any(t in nome for t in ("cadastr", "tipo", "situacao", "status",
                                               "aprov", "cnae", "atividade", "estado")):
                        print(f"\n    · {c['COLUMN_NAME']}")
                        try:
                            cur.execute(
                                f"SELECT {c['COLUMN_NAME']} AS v, COUNT(*) AS n "
                                f"FROM accounts_cstm GROUP BY {c['COLUMN_NAME']} "
                                f"ORDER BY n DESC LIMIT 8"
                            )
                            for r in cur.fetchall():
                                print(f"        {str(r['v'])[:45]:45s} {r['n']:>7,}")
                        except Exception as e:
                            print(f"        (erro: {e})")

            # ---------------------------------------------------------------
            # 6. Contatos ligados a bss_users? (o contato loga no portal)
            # ---------------------------------------------------------------
            secao("Contatos têm login? (portal_user / user_hash / password)")
            try:
                cur.execute(
                    """
                    SELECT COLUMN_NAME, COLUMN_TYPE
                      FROM information_schema.COLUMNS
                     WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'contacts'
                       AND (COLUMN_NAME LIKE '%%portal%%' OR COLUMN_NAME LIKE '%%pass%%'
                         OR COLUMN_NAME LIKE '%%hash%%'   OR COLUMN_NAME LIKE '%%user%%'
                         OR COLUMN_NAME LIKE '%%login%%')
                     ORDER BY COLUMN_NAME
                    """,
                    (settings.MYSQL_DB,),
                )
                for r in cur.fetchall():
                    print(f"    contacts.{r['COLUMN_NAME']:34s} {r['COLUMN_TYPE']}")
                cur.execute(
                    "SELECT portal_user_type AS v, COUNT(*) n FROM contacts "
                    "WHERE deleted=0 GROUP BY portal_user_type ORDER BY n DESC LIMIT 5"
                )
                print("\n    portal_user_type:")
                for r in cur.fetchall():
                    print(f"      {str(r['v'])[:30]:30s} {r['n']:>7,}")
            except Exception as e:
                print(f"    (erro: {e})")

    print("\n" + "=" * 76)
    print("Cole a saída no chat — com ela eu escrevo o desenho do Autocadastro")
    print("e a modelagem de Contatos no BSS, aterrados no que o legado faz.")
    print("=" * 76)


if __name__ == "__main__":
    main()
