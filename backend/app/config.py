"""
Configurações da aplicação BSS.

Lê variáveis de ambiente do arquivo .env (não commitado no Git).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # === PostgreSQL do BSS (banco novo, fonte da verdade) ===
    PG_HOST:     str = "localhost"
    PG_PORT:     int = 5432
    PG_DB:       str
    PG_USER:     str
    PG_PASSWORD: str

    # === MySQL do SuiteCRM legado (somente leitura) ===
    # Opcional: deixa vazio enquanto não for usar.
    MYSQL_HOST:     str = ""
    MYSQL_PORT:     int = 3306
    MYSQL_DB:       str = ""
    MYSQL_USER:     str = ""
    MYSQL_PASSWORD: str = ""

    # === JWT ===
    JWT_SECRET:         str
    JWT_ALGORITHM:      str = "HS256"
    JWT_EXPIRE_MINUTES: int = 480  # 8h

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
