"""
Verifica ONDE, geograficamente, está o RDS MySQL do SuiteCRM.

Uso (do diretório backend/, na OCI — é de lá que existe rota pro RDS):
    venv/bin/python -m scripts.verificar_localizacao_rds

POR QUE IMPORTA
---------------
Se o banco está fora do Brasil, os dados pessoais dos trabalhadores
(CPF, nome da mãe, data de nascimento, dependentes menores de idade, certidões
de óbito) estão em **transferência internacional** — o que a LGPD trata em
capítulo próprio (arts. 33 a 36) e exige base legal específica. Não é detalhe
técnico: é jurídico.

Este script NÃO decide nada disso. Ele só estabelece o FATO de onde o servidor
está, com três evidências independentes, pra ninguém precisar confiar em
palpite (nem no meu).

SOMENTE LEITURA. Não escreve no MySQL — que é read-only e blindado.
"""

import socket

from app.config import settings
from app.database import get_mysql_connection


# Regiões da AWS → onde ficam de verdade. Só as que interessam aqui.
REGIOES = {
    "us-east-1":      "Norte da Virgínia, ESTADOS UNIDOS",
    "us-east-2":      "Ohio, ESTADOS UNIDOS",
    "us-west-1":      "Norte da Califórnia, ESTADOS UNIDOS",
    "us-west-2":      "Oregon, ESTADOS UNIDOS",
    "sa-east-1":      "São Paulo, BRASIL",
    "eu-west-1":      "Irlanda",
    "eu-central-1":   "Frankfurt, Alemanha",
}


def main() -> None:
    host = settings.MYSQL_HOST
    if not host:
        print("✗ MYSQL_HOST não configurado neste .env")
        return

    print("\n" + "=" * 66)
    print("ONDE ESTÁ O RDS DO SUITECRM?")
    print("=" * 66)
    print(f"\nHost: {host}")

    # ---------------------------------------------------------------
    # EVIDÊNCIA 1 — a região está cravada no nome do endpoint
    # ---------------------------------------------------------------
    # Endpoint de RDS tem formato fixo:
    #   <instancia>.<hash>.<REGIAO>.rds.amazonaws.com
    # A região não é escolha de quem nomeia: é a AWS que monta o DNS. Uma
    # instância em São Paulo NÃO pode ter "us-east-1" no nome.
    print("\n--- 1. Região no endpoint ---")
    partes = host.split(".")
    regiao = None
    for p in partes:
        if p in REGIOES:
            regiao = p
            break
    if regiao:
        print(f"  região  : {regiao}")
        print(f"  local   : {REGIOES[regiao]}")
    else:
        print("  (não reconheci a região no nome — ver evidências abaixo)")

    # ---------------------------------------------------------------
    # EVIDÊNCIA 2 — pra onde o nome resolve
    # ---------------------------------------------------------------
    print("\n--- 2. Resolução DNS ---")
    try:
        infos = socket.getaddrinfo(host, None, socket.AF_INET)
        ips = sorted({i[4][0] for i in infos})
        for ip in ips:
            print(f"  IP: {ip}")
            try:
                rev = socket.gethostbyaddr(ip)[0]
                print(f"      reverso: {rev}")
            except Exception:
                print("      reverso: (sem PTR — normal em RDS)")
        print("\n  Confira o IP em https://ip-ranges.amazonaws.com/ip-ranges.json")
        print("  (o JSON da AWS diz a região de cada faixa — é a fonte oficial)")
    except Exception as e:
        print(f"  ✗ falhou: {e}")

    # ---------------------------------------------------------------
    # EVIDÊNCIA 3 — o que o próprio servidor diz
    # ---------------------------------------------------------------
    # RDS roda em UTC por padrão. Um servidor configurado pro Brasil
    # normalmente estaria em -03. Não é prova sozinha (dá pra rodar UTC em
    # qualquer lugar), mas soma.
    print("\n--- 3. O que o servidor MySQL responde ---")
    try:
        with get_mysql_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        @@hostname            AS hostname,
                        @@version             AS versao,
                        @@version_comment     AS versao_comment,
                        @@system_time_zone    AS tz_sistema,
                        @@time_zone           AS tz_sessao,
                        NOW()                 AS agora_no_servidor,
                        UTC_TIMESTAMP()       AS agora_utc
                """)
                r = cur.fetchone()
                for k, v in r.items():
                    print(f"  {k:<20} {v}")
    except Exception as e:
        print(f"  ✗ não consegui consultar: {e}")
        print("    (esperado se rodar fora da OCI — só o servidor metabase tem rota)")

    print("\n" + "=" * 66)
    print("LEITURA DAS EVIDÊNCIAS")
    print("=" * 66)
    print("""
  A região no endpoint é a evidência mais forte e mais simples: a AWS monta
  esse DNS, não o cliente. 'us-east-1' significa Norte da Virgínia, EUA — não
  existe instância em 'us-east-1' fisicamente no Brasil. Se fosse São Paulo,
  o endpoint diria 'sa-east-1'.

  O IP confirma pela faixa (ip-ranges.json da AWS), e o timezone soma como
  indício. As três apontando pro mesmo lugar = fato estabelecido.

  ATENÇÃO: isto responde ONDE ESTÁ. NÃO responde se é permitido, nem qual a
  base legal da transferência internacional. Isso é conversa de jurídico, não
  de script — e vale trazer ANTES do Big Bang, porque a decisão de onde o BSS
  vai hospedar os dados em produção depende dela.
""")


if __name__ == "__main__":
    main()
