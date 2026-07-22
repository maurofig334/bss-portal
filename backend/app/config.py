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

    # DOIS JEITOS DE CRIPTOGRAFAR, QUE NÃO SÃO A MESMA COISA:
    #
    #   STARTTLS (porta 587) — conecta em claro e sobe pra TLS. É o padrão da
    #     maioria dos provedores, inclusive Gmail. Use SMTP_USE_TLS=true.
    #
    #   SSL/TLS direto (porta 465) — já conecta criptografado.
    #     Use SMTP_SSL=true.
    #
    # Ligar o errado dá erro de conexão ou timeout, não erro de senha — e a
    # mensagem do smtplib não ajuda a perceber. Na dúvida: 587 → USE_TLS,
    # 465 → SSL.
    SMTP_USE_TLS:  bool = True    # STARTTLS (587) — o caso comum
    SMTP_SSL:      bool = False   # SSL direto (465)

    # SAÍDA DE EMERGÊNCIA — deixar TRUE sempre que possível.
    #
    # Hospedagem compartilhada costuma apresentar certificado emitido pro
    # hostname real da máquina, não pro apelido do seu domínio, e o Python
    # recusa com "Hostname mismatch". A solução CERTA é usar o hostname pro
    # qual o certificado é válido — rode scripts/diagnosticar_smtp.py pra
    # descobrir qual é.
    #
    # Só use FALSE se nenhum hostname válido funcionar. O tráfego continua
    # criptografado, mas ninguém confere COM QUEM se está falando — abre porta
    # pra man-in-the-middle. Aceitável em homologação com conta provisória;
    # não levar pra produção com dado real de trabalhador.
    SMTP_VERIFICAR_CERT: bool = True

    # Base pública do portal, usada pra montar o link do e-mail. Sem isto o
    # e-mail sairia com link relativo, que não clica.
    APP_BASE_URL:  str = "https://bss.nexussistemas.com.br"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
