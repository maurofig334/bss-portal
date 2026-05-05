"""
Cria (ou atualiza) a tabela `bss_users` no PostgreSQL do BSS.

Idempotente: pode rodar várias vezes.

Uso (do diretório backend/, com venv ativa):
    python -m scripts.criar_tabela_usuarios
"""

from app.database import get_pg_connection


CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS bss_users (
    id            SERIAL PRIMARY KEY,
    email         VARCHAR(120) UNIQUE NOT NULL,
    nome          VARCHAR(120) NOT NULL,
    senha_hash    VARCHAR(200) NOT NULL,
    ativo         BOOLEAN NOT NULL DEFAULT TRUE,
    -- Perfil determina o que o usuário pode fazer (1 perfil por usuário):
    --   'admin'        = staff GNB com acesso total ao sistema
    --   'interno'      = staff GNB (financeiro, operacional) sem filtro de empresa
    --   'analista'     = staff GNB que avalia processos de benefício
    --   'empresa'      = cliente — opera N empresas via bss.usuario_empresa
    --   'sindicato'    = sindicato — vê N sindicatos via bss.usuario_sindicato
    --   'contabilidade'= contador externo (escopo a detalhar)
    perfil        VARCHAR(20) NOT NULL DEFAULT 'admin',
    telefone      VARCHAR(20),
    ultimo_login  TIMESTAMPTZ,
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bss_users_email ON bss_users (LOWER(email));
CREATE INDEX IF NOT EXISTS idx_bss_users_perfil_ativo ON bss_users (perfil) WHERE ativo;
"""


def main() -> None:
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE)
        conn.commit()
    print("✓ Tabela 'bss_users' pronta.")


if __name__ == "__main__":
    main()
