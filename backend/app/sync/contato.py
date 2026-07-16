"""
Sincroniza CONTATOS (usuários externos): contacts + contacts_cstm → bss_users
                             accounts_contacts → bss.usuario_empresa

Ver docs/AUTOCADASTRO.md. O "Contato" do SuiteCRM É o bss_users com
perfil='empresa' — não é entidade separada. O schema já dizia isso:
    'empresa' = cliente — opera N empresas via bss.usuario_empresa

ESCOPO (decisão do Mauro, 01/07/2026)
-------------------------------------
Só o grupo EMPRESAS (tipocontato_c='EMPRESA'). Funerárias e Sindicatos ficam
de fora até definirmos o que cada grupo enxerga — e o BSS nem tem perfil
'funeraria' ainda.

⚠️ O BACALHAU DO SUITECRM — leia antes de mexer neste arquivo
--------------------------------------------------------------
O SuiteCRM tem um defeito estrutural: **um contato só pode ter UMA empresa**.
Como um gerente de RH administra 4 ou 5 CNPJs, a saída foi criar **o MESMO
contato N vezes**, cada cópia apontando pra uma empresa diferente. Mesmo nome,
mesmo e-mail, N registros.

Ou seja: e-mail repetido NÃO é sujeira — é o contorno do defeito.

CONSEQUÊNCIA PRO SYNC: deduplicar por e-mail e **UNIR os vínculos de todas as
cópias**. Se pegássemos "o primeiro e descartássemos o resto", a pessoa perderia
acesso às outras empresas — silenciosamente, sem erro nenhum aparecer.

Por isso a chave aqui é o **E-MAIL**, não o id_legado_uuid: são N UUIDs pra uma
pessoa só. `id_legado_uuid` fica como referência (guarda um dos UUIDs), mas quem
manda no ON CONFLICT é o e-mail — que já é UNIQUE em bss_users e é a identidade
real da pessoa.

Isso faz da migração uma CURA, não uma cópia: bss_users + usuario_empresa é o
N:N que o SuiteCRM não conseguia expressar. Um e-mail, uma pessoa, N empresas.

SENHAS — NÃO SÃO MIGRADAS
-------------------------
`contacts_cstm.password_c` guarda cifra REVERSÍVEL (16 bytes base64, ex.:
"Lr/Q78KQNmivwoez0uJSDA=="), não hash. Quem tem a chave lê a senha de todos os
usuários do portal. O BSS usa bcrypt (via única), então cada contato migrado
recebe um bcrypt de bytes ALEATÓRIOS: hash válido, senha que ninguém conhece.
Login falha limpo (401) e a pessoa é obrigada a usar "esqueci minha senha".

⚠️ BIG BANG: no corte, TODO contato externo precisa redefinir senha. É tarefa
de comunicação com o cliente, não detalhe técnico.

MAPEAMENTO DOS CONTROLES DE ACESSO
----------------------------------
O legado tem DOIS controles independentes (dá pra estar autorizado e bloqueado):
    enable_portal_c   = autorização do contato novo  → usuario_empresa.ativo
    lock_portal_user  = bloqueia a pessoa            → bss_users.ativo = false
O BSS já separa isso corretamente.
"""

from __future__ import annotations

import json
import os

import bcrypt

from ..database import get_mysql_connection, get_pg_connection
from ._base import Progresso, mysql_iter, pg_executemany, trim_or_none


SQL_LEGADO = """
    SELECT
        c.id                          AS uuid,
        c.first_name                  AS primeiro_nome,
        c.last_name                   AS sobrenome,
        c.phone_mobile                AS celular,
        c.phone_work                  AS telefone_trabalho,
        c.date_entered                AS criado_em,
        c.lock_portal_user            AS bloqueado,
        cc.username_c                 AS username,
        cc.enable_portal_c            AS portal_habilitado,
        cc.register_from_c            AS origem,
        cc.tipocontato_c              AS tipo_contato,
        cc.ufabrangencia_c            AS uf_abrangencia,
        cc.recebeemailfinanceiro_c    AS pref_financeiro,
        cc.recebeemailbeneficio_c     AS pref_beneficio,
        cc.recebeemailatualizacao_c   AS pref_atualizacao,
        cc.recebeemailboleto_c        AS pref_boleto
    FROM contacts c
    JOIN contacts_cstm cc ON cc.id_c = c.id
    WHERE c.deleted = 0
      AND cc.tipocontato_c = 'EMPRESA'
"""
# Sem filtro de username: contato sem e-mail vem também (é ficha de
# telefone/endereço, não usuário do portal — ver _email_sintetico).

# Conflito pelo E-MAIL, não pelo id_legado_uuid: o mesmo e-mail vem em N
# registros do legado (o bacalhau — ver docstring). Cada um deles reforça a
# MESMA pessoa; o que varia é a empresa, e isso vai pro N:N na passada 2.
SQL_UPSERT_USER = """
    INSERT INTO bss_users (
        id_legado_uuid, email, nome, senha_hash, telefone,
        perfil, ativo, tipo_cadastro, preferencias_notificacao, criado_em
    )
    VALUES (%s, %s, %s, %s, %s, 'empresa', %s, %s, %s::jsonb, %s)
    ON CONFLICT (email) DO UPDATE
        SET nome     = EXCLUDED.nome,
            telefone = COALESCE(EXCLUDED.telefone, bss_users.telefone),
            -- Basta UMA cópia desbloqueada pra pessoa estar liberada:
            -- o bloqueio no legado é por registro, mas a pessoa é uma só.
            ativo    = bss_users.ativo OR EXCLUDED.ativo,
            tipo_cadastro = EXCLUDED.tipo_cadastro,
            preferencias_notificacao = EXCLUDED.preferencias_notificacao
            -- senha_hash NÃO entra no UPDATE: se a pessoa já redefiniu a senha
            -- no BSS, um re-sync não pode jogar fora.
            -- id_legado_uuid também não: fica o da primeira cópia vista.
"""

# Vínculos: cada cópia do contato traz a SUA empresa. Ao resolver o contato
# pelo E-MAIL (e não pelo uuid), as N cópias convergem pra uma pessoa só e os
# vínculos se somam — desfazendo o bacalhau.
SQL_VINCULOS_LEGADO = """
    SELECT ac.contact_id                            AS uuid_contato,
           LOWER(TRIM(COALESCE(cc.username_c, ''))) AS email,
           ac.account_id                            AS uuid_empresa
      FROM accounts_contacts ac
      JOIN contacts c        ON c.id = ac.contact_id AND c.deleted = 0
      JOIN contacts_cstm cc  ON cc.id_c = c.id
     WHERE ac.deleted = 0
       AND cc.tipocontato_c = 'EMPRESA'
"""

SQL_UPSERT_VINCULO = """
    INSERT INTO bss.usuario_empresa (id_usuario, id_empresa, ativo)
    VALUES (%s, %s, %s)
    ON CONFLICT (id_usuario, id_empresa) DO UPDATE
        SET ativo = EXCLUDED.ativo
"""


_SENHA_CACHE: str | None = None


def _senha_inutilizavel() -> str:
    """
    bcrypt de 32 bytes aleatórios. Hash VÁLIDO (bcrypt.checkpw não explode),
    senha que ninguém conhece — força "esqueci minha senha".
    Não usar marcador tipo '!migrado': checkpw levanta ValueError e vira 500.

    Gerado UMA VEZ por execução e reusado. bcrypt é deliberadamente caro
    (~100ms), e 2.500 contatos × 100ms = 4 minutos gastos só pra produzir
    hashes que ninguém vai conferir. Compartilhar o hash é seguro aqui: o
    texto original são 32 bytes aleatórios que nunca saem desta função — não
    existe senha a ser descoberta, nem para um, nem para todos.
    """
    global _SENHA_CACHE
    if _SENHA_CACHE is None:
        _SENHA_CACHE = bcrypt.hashpw(os.urandom(32), bcrypt.gensalt()).decode()
    return _SENHA_CACHE


def _email_sintetico(uuid: str) -> str:
    """
    Contato SEM e-mail: existe no legado como ficha de telefone/endereço, não
    como usuário do portal (decisão do Mauro: trazer e deixar como está).

    Mas bss_users.email é UNIQUE NOT NULL — é o login. Então geramos um
    endereço que grita que é falso e não recebe nada: `.invalid` é TLD
    reservado (RFC 2606) exatamente pra isso, então ninguém escreve pra lá por
    engano. Estes entram com ativo=false: login é impossível de qualquer jeito.
    """
    return f"sem-email-{uuid[:8]}@contato.invalid"


def _sim(valor) -> bool:
    """O legado grava '1'/'0' como varchar, e às vezes 'Sim'/None."""
    if valor is None:
        return False
    return str(valor).strip().lower() in ("1", "sim", "true", "y", "on")


def _diagnostico(cur) -> None:
    """Roda antes do sync: mostra o terreno e os riscos conhecidos."""
    print("\n  --- tipocontato_c (o filtro do escopo) ---")
    cur.execute(
        "SELECT tipocontato_c v, COUNT(*) n FROM contacts_cstm "
        "GROUP BY tipocontato_c ORDER BY n DESC"
    )
    for r in cur.fetchall():
        print(f"      {str(r['v']):20s} {r['n']:>6,}")

    # Portal User Group ≠ tipocontato_c. O primeiro (Empresas/Funerárias/
    # Sindicatos) define o que a pessoa ENXERGA; o segundo é a natureza do
    # contato. A funerária provavelmente é tipocontato_c='EMPRESA' com grupo
    # 'Funerárias' — e não pode entrar como perfil='empresa'.
    print("\n  --- Portal User Group x tipocontato_c (securitygroups) ---")
    try:
        cur.execute(
            """
            SELECT sg.name AS grupo, cc.tipocontato_c AS tipo, COUNT(*) AS n
              FROM securitygroups_records sr
              JOIN securitygroups sg ON sg.id = sr.securitygroup_id AND sg.deleted = 0
              JOIN contacts c        ON c.id = sr.record_id AND c.deleted = 0
              LEFT JOIN contacts_cstm cc ON cc.id_c = c.id
             WHERE sr.module = 'Contacts' AND sr.deleted = 0
             GROUP BY sg.name, cc.tipocontato_c
             ORDER BY n DESC
            """
        )
        linhas = cur.fetchall()
        if linhas:
            for r in linhas:
                print(f"      {str(r['grupo'])[:22]:22s} × {str(r['tipo']):12s} {r['n']:>6,}")
            print("      → se houver grupo 'Funerárias' com tipo EMPRESA, o filtro")
            print("        por tipocontato_c NÃO basta: traria funerária como gestor")
        else:
            print("      (nenhum contato em securitygroups — grupo deve vir de outro lugar)")
    except Exception as e:
        print(f"      (securitygroups não acessível: {e})")

    print("\n  --- username_c duplicado? (email é UNIQUE no BSS) ---")
    cur.execute(
        """
        SELECT COUNT(*) AS dups FROM (
            SELECT LOWER(TRIM(cc.username_c)) u
              FROM contacts c JOIN contacts_cstm cc ON cc.id_c = c.id
             WHERE c.deleted = 0 AND cc.tipocontato_c = 'EMPRESA'
               AND cc.username_c IS NOT NULL AND TRIM(cc.username_c) <> ''
             GROUP BY LOWER(TRIM(cc.username_c)) HAVING COUNT(*) > 1
        ) x
        """
    )
    dups = cur.fetchone()["dups"]
    if dups:
        print(f"      ⚠ {dups} e-mail(s) repetido(s) — vão colidir na UNIQUE de bss_users.email")
        cur.execute(
            """
            SELECT LOWER(TRIM(cc.username_c)) u, COUNT(*) n
              FROM contacts c JOIN contacts_cstm cc ON cc.id_c = c.id
             WHERE c.deleted = 0 AND cc.tipocontato_c = 'EMPRESA'
               AND cc.username_c IS NOT NULL AND TRIM(cc.username_c) <> ''
             GROUP BY LOWER(TRIM(cc.username_c)) HAVING COUNT(*) > 1
             ORDER BY n DESC LIMIT 10
            """
        )
        for r in cur.fetchall():
            print(f"        {r['u']:45s} {r['n']}x")
    else:
        print("      ✓ nenhum — cada contato tem e-mail único")


def _carregar_empresa_map(pg_conn) -> dict[str, int]:
    m: dict[str, int] = {}
    with pg_conn.cursor() as cur:
        cur.execute("SELECT id, id_legado_uuid FROM bss.empresa WHERE id_legado_uuid IS NOT NULL")
        for r in cur:
            m[r["id_legado_uuid"]] = r["id"]
    return m


def _carregar_user_map(pg_conn) -> dict[str, int]:
    """
    email → bss_users.id.

    Por E-MAIL, não por uuid: o legado tem N cópias do mesmo contato (o
    bacalhau), e todas convergem pra uma pessoa só. É assim que os vínculos
    das cópias se somam em vez de se perderem.
    """
    m: dict[str, int] = {}
    with pg_conn.cursor() as cur:
        cur.execute("SELECT id, email FROM bss_users WHERE perfil = 'empresa'")
        for r in cur:
            m[r["email"]] = r["id"]
    return m


def _converter(linha: dict) -> tuple | None:
    email = (linha.get("username") or "").strip().lower()
    sem_email = not email or "@" not in email
    if sem_email:
        # Não é usuário do portal — é ficha de telefone/endereço. Trazemos
        # assim mesmo (ver _email_sintetico), inativo.
        email = _email_sintetico(linha["uuid"])

    # O nome completo vive em last_name (first_name costuma estar vazio)
    nome = " ".join(
        p for p in [(linha.get("primeiro_nome") or "").strip(),
                    (linha.get("sobrenome") or "").strip()] if p
    ) or email

    telefone = trim_or_none(linha.get("celular") or linha.get("telefone_trabalho"), 20)

    # Dois controles independentes no legado:
    #   lock_portal_user = pessoa bloqueada     → bss_users.ativo = false
    #   enable_portal_c  = autorização de acesso → vai pro usuario_empresa.ativo
    # Sem e-mail = sem login possível, então inativo por construção.
    ativo = (not sem_email) and (not _sim(linha.get("bloqueado")))

    prefs = json.dumps({
        "financeiro":  _sim(linha.get("pref_financeiro")),
        "beneficio":   _sim(linha.get("pref_beneficio")),
        "atualizacao": _sim(linha.get("pref_atualizacao")),
        "boleto":      _sim(linha.get("pref_boleto")),
    })

    origem = (linha.get("origem") or "").strip().lower()
    tipo_cadastro = "auto" if origem == "portal" else "interno"

    return (
        linha["uuid"],
        email,
        trim_or_none(nome, 120),
        _senha_inutilizavel(),
        telefone,
        ativo,
        tipo_cadastro,
        prefs,
        linha.get("criado_em"),
    )


def sync(dry_run: bool = False, limite: int | None = None) -> int:
    print(f"\n=== Sync CONTATO (grupo Empresas) ({'dry-run' if dry_run else 'gravação'}) ===")

    with get_mysql_connection() as mysql_conn:
        with mysql_conn.cursor() as cur:
            _diagnostico(cur)

    sql = SQL_LEGADO + (f" LIMIT {int(limite)}" if limite else "")

    # ---------- Passada 1: bss_users ----------
    #
    # As N cópias do mesmo e-mail (o bacalhau) são FUNDIDAS aqui, no Python —
    # não no ON CONFLICT. Motivo: o Postgres recusa `ON CONFLICT DO UPDATE`
    # atingir a mesma chave duas vezes no MESMO comando ("cannot affect row a
    # second time"), e com 5 cópias no mesmo lote o executemany quebraria.
    #
    # Fusão: ativo = basta UMA cópia desbloqueada (o bloqueio no legado é por
    # registro, mas a pessoa é uma só); telefone/nome = o primeiro preenchido.
    prog = Progresso(total=None, nome="contato")
    por_email: dict[str, list] = {}
    copias = 0

    with get_mysql_connection() as mysql_conn:
        for linha in mysql_iter(mysql_conn, sql, batch_size=1000):
            prog.tick()
            tup = _converter(linha)
            if tup is None:
                continue
            email = tup[1]
            if email not in por_email:
                por_email[email] = list(tup)
            else:
                copias += 1
                atual = por_email[email]
                atual[2] = atual[2] or tup[2]              # nome
                atual[4] = atual[4] or tup[4]              # telefone
                atual[5] = bool(atual[5]) or bool(tup[5])  # ativo (OR)
                # criado_em: fica o mais ANTIGO — é quando a pessoa entrou
                if tup[8] and atual[8] and tup[8] < atual[8]:
                    atual[8] = tup[8]
    prog.fim()

    fundidos = [tuple(v) for v in por_email.values()]
    if dry_run:
        for t in fundidos[:3]:
            print(f"    amostra: {t[1]} · {t[2]} · ativo={t[5]} · {t[6]}")
        print(f"\n  (dry-run) {len(fundidos)} pessoa(s) seriam gravadas")
        print(f"  ✓ {copias} cópia(s) do bacalhau FUNDIDAS (não descartadas —")
        print(f"    os vínculos de empresa de todas elas entram na passada 2)")
        return prog.contador

    with get_pg_connection() as pg_conn:
        pg_executemany(pg_conn, SQL_UPSERT_USER, iter(fundidos), batch_size=500)
    print(f"  ✓ {len(fundidos)} pessoa(s) · {copias} cópia(s) do legado fundidas")

    # ---------- Passada 2: vínculos N:N ----------
    print("\n  ligando usuario_empresa (N:N accounts_contacts)...")
    with get_pg_connection() as pg_conn:
        user_map = _carregar_user_map(pg_conn)
        emp_map = _carregar_empresa_map(pg_conn)
    print(f"  ✓ {len(user_map)} usuários, {len(emp_map)} empresas em memória")

    prog2 = Progresso(total=None, nome="usuario_empresa")
    sem_user = sem_emp = 0

    with get_mysql_connection() as mysql_conn:
        def iter_vinculos():
            nonlocal sem_user, sem_emp
            for linha in mysql_iter(mysql_conn, SQL_VINCULOS_LEGADO, batch_size=2000):
                prog2.tick()
                # Mesma resolução do _converter: e-mail é a identidade, e o
                # contato sem e-mail recebe o sintético derivado do uuid.
                email = (linha.get("email") or "").strip().lower()
                if not email or "@" not in email:
                    email = _email_sintetico(linha["uuid_contato"])
                id_user = user_map.get(email)
                if not id_user:
                    # Contato fora do escopo (funerária/sindicato/interno)
                    sem_user += 1
                    continue
                id_emp = emp_map.get(linha.get("uuid_empresa"))
                if not id_emp:
                    sem_emp += 1
                    continue
                yield (id_user, id_emp, True)

        with get_pg_connection() as pg_conn:
            pg_executemany(pg_conn, SQL_UPSERT_VINCULO, iter_vinculos(), batch_size=1000)
    prog2.fim()
    if sem_user:
        print(f"  ⚠ {sem_user} vínculo(s) de contato fora do escopo (funerária/sindicato/sem e-mail)")
    if sem_emp:
        print(f"  ⚠ {sem_emp} vínculo(s) com empresa não encontrada no BSS")
    return prog.contador
