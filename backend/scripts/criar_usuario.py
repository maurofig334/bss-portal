"""
Cria um usuário admin (ou qualquer perfil) no BSS.

Uso interativo (do diretório backend/, com venv ativa):
    python -m scripts.criar_usuario
"""

import getpass

from app.auth import hash_senha
from app.database import get_pg_connection


PERFIS = {"admin", "interno", "analista", "empresa", "sindicato", "contabilidade"}


def _parse_ids(raw: str) -> list[int]:
    """Aceita lista de IDs separados por vírgula ou espaço."""
    if not raw:
        return []
    parts = raw.replace(",", " ").split()
    return [int(p) for p in parts if p.isdigit()]


def main() -> None:
    print("=== Criar usuário BSS ===\n")
    email = input("Email: ").strip().lower()
    nome  = input("Nome: ").strip()

    while True:
        perfil = input(f"Perfil ({'/'.join(sorted(PERFIS))}) [admin]: ").strip() or "admin"
        if perfil in PERFIS:
            break
        print(f"  ! Perfil inválido. Escolha entre: {', '.join(sorted(PERFIS))}")

    empresas: list[int] = []
    sindicatos: list[int] = []
    if perfil == "empresa":
        empresas = _parse_ids(input("IDs das empresas (separados por vírgula): "))
        if not empresas:
            print("  ! Aviso: usuário 'empresa' sem nenhum vínculo — não verá nada.")
    elif perfil == "sindicato":
        sindicatos = _parse_ids(input("IDs dos sindicatos (separados por vírgula): "))
        if not sindicatos:
            print("  ! Aviso: usuário 'sindicato' sem nenhum vínculo — não verá nada.")

    senha = getpass.getpass("Senha (mínimo 6): ")
    if len(senha) < 6:
        print("Senha curta demais.")
        return

    sha = hash_senha(senha)

    sql_user = """
        INSERT INTO bss_users (email, nome, senha_hash, ativo, perfil)
        VALUES (%s, %s, %s, TRUE, %s)
        ON CONFLICT (email) DO UPDATE
            SET nome = EXCLUDED.nome,
                senha_hash = EXCLUDED.senha_hash,
                perfil = EXCLUDED.perfil,
                ativo = TRUE
        RETURNING id
    """
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_user, (email, nome, sha, perfil))
            user_id = cur.fetchone()["id"]

            # Limpa vínculos antigos e regrava (UPSERT do conjunto)
            cur.execute("DELETE FROM bss.usuario_empresa   WHERE id_usuario = %s", (user_id,))
            cur.execute("DELETE FROM bss.usuario_sindicato WHERE id_usuario = %s", (user_id,))
            for id_emp in empresas:
                cur.execute(
                    "INSERT INTO bss.usuario_empresa (id_usuario, id_empresa) VALUES (%s, %s)",
                    (user_id, id_emp),
                )
            for id_sind in sindicatos:
                cur.execute(
                    "INSERT INTO bss.usuario_sindicato (id_usuario, id_sindicato) VALUES (%s, %s)",
                    (user_id, id_sind),
                )
        conn.commit()

    extras = ""
    if empresas:
        extras = f" — vinculado a {len(empresas)} empresa(s): {empresas}"
    elif sindicatos:
        extras = f" — vinculado a {len(sindicatos)} sindicato(s): {sindicatos}"
    print(f"\n✓ Usuário {email} (id={user_id}) salvo como {perfil!r}{extras}.")


if __name__ == "__main__":
    main()
