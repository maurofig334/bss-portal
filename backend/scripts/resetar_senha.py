"""
Reseta a senha de um usuário BSS sem mexer em outros campos.

Uso (do diretório backend/, com venv ativa):
    python -m scripts.resetar_senha
"""

import getpass

from app.auth import hash_senha
from app.database import get_pg_connection


def main() -> None:
    print("=== Resetar senha BSS ===\n")
    email = input("Email do usuário: ").strip().lower()
    if not email:
        print("Email vazio. Abortando.")
        return

    # Confirma que o usuário existe antes de pedir senha
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, nome, perfil, ativo FROM bss_users WHERE email = %s",
                (email,),
            )
            user = cur.fetchone()

    if not user:
        print(f"\n✗ Usuário com email '{email}' não encontrado.")
        print("  Use criar_usuario.py se quiser criar um novo.")
        return

    print(f"\nEncontrado: id={user['id']} nome={user['nome']!r} "
          f"perfil={user['perfil']!r} ativo={user['ativo']}")

    senha = getpass.getpass("Nova senha (mínimo 6): ")
    if len(senha) < 6:
        print("Senha curta demais.")
        return
    senha2 = getpass.getpass("Confirme a nova senha: ")
    if senha != senha2:
        print("As senhas não conferem.")
        return

    sha = hash_senha(senha)

    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE bss_users SET senha_hash = %s, ativo = TRUE "
                " WHERE email = %s",
                (sha, email),
            )
        conn.commit()

    print(f"\n✓ Senha de {email} resetada com sucesso.")
    if not user["ativo"]:
        print("  (usuário estava inativo — também foi reativado)")


if __name__ == "__main__":
    main()
