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

    # === E-mail (SMTP) ===
    # Tudo opcional: sem SMTP_HOST o envio é desligado e o app roda igual —
    # notificação nunca pode ser pré-requisito pro sistema funcionar.
    SMTP_HOST:     str = ""
    SMTP_PORT:     int = 587
    SMTP_USER:     str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM:     str = ""      # vazio → usa SMTP_USER
    SMTP_FROM_NOME: str = "BSS — Benefício Social Sindical"
    # STARTTLS na 587 (padrão). Para SSL direto na 465, use SMTP_SSL=true.
    SMTP_SSL:      bool = False

    # Base pública do portal, usada pra montar o link do e-mail. Sem isto o
    # e-mail sairia com link relativo, que não clica.
    APP_BASE_URL:  str = "https://bss.nexussistemas.com.br"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
