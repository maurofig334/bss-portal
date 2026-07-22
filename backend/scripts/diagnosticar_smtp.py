"""
Mostra pra QUAIS hostnames o certificado do servidor SMTP é válido.

Uso (do diretório backend/):
    venv/bin/python -m scripts.diagnosticar_smtp
    venv/bin/python -m scripts.diagnosticar_smtp mail.outrohost.com.br 587

POR QUE
-------
Erro típico de hospedagem compartilhada:

    [SSL: CERTIFICATE_VERIFY_FAILED] Hostname mismatch, certificate is not
    valid for 'smtp.seudominio.com.br'

O servidor existe e responde — só que o certificado TLS dele foi emitido pro
hostname REAL da máquina (algo como mail.provedor.com ou srv42.host.com.br),
e não pro apelido do seu domínio. O Python valida o nome e recusa, com razão.

A tentação é desligar a verificação. A saída certa é usar o hostname pro qual
o certificado É válido: continua criptografado E continua verificado. Este
script descobre qual é.
"""

import socket
import smtplib
import ssl
import sys

from app.config import settings


def _nomes_do_certificado(cert: dict) -> list[str]:
    """Extrai CN + todos os subjectAltName DNS do certificado."""
    nomes = []
    for campo in cert.get("subject", ()):
        for chave, valor in campo:
            if chave == "commonName":
                nomes.append(valor)
    for tipo, valor in cert.get("subjectAltName", ()):
        if tipo == "DNS":
            nomes.append(valor)
    return sorted(set(nomes))


def main() -> None:
    host = sys.argv[1] if len(sys.argv) > 1 else settings.SMTP_HOST
    porta = int(sys.argv[2]) if len(sys.argv) > 2 else settings.SMTP_PORT

    if not host:
        print("✗ Sem SMTP_HOST no .env e nenhum host passado por argumento.")
        return

    print(f"\nConectando em {host}:{porta}…")

    try:
        ips = sorted({i[4][0] for i in socket.getaddrinfo(host, None, socket.AF_INET)})
        print(f"  IP: {', '.join(ips)}")
    except Exception as e:
        print(f"  ✗ o nome não resolve: {e}")
        return

    # Contexto SEM verificação — de propósito: queremos LER o certificado que
    # está sendo apresentado, justamente porque a verificação falhou. Isto é
    # diagnóstico, não é o caminho de envio.
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        if porta == 465:
            with smtplib.SMTP_SSL(host, porta, context=ctx, timeout=20) as s:
                cert = s.sock.getpeercert()
        else:
            with smtplib.SMTP(host, porta, timeout=20) as s:
                s.starttls(context=ctx)
                cert = s.sock.getpeercert()
    except Exception as e:
        print(f"  ✗ falhou ao conectar: {e}")
        return

    if not cert:
        print("  ⚠ conectou, mas não consegui ler o certificado.")
        return

    nomes = _nomes_do_certificado(cert)
    print("\n=== O certificado é válido para ".ljust(56, "="))
    for n in nomes:
        marca = "  ← é o que você está usando" if n == host else ""
        print(f"  {n}{marca}")

    emissor = ", ".join(
        v for campo in cert.get("issuer", ()) for k, v in campo if k == "organizationName"
    )
    if emissor:
        print(f"\n  emissor: {emissor}")
    if cert.get("notAfter"):
        print(f"  expira : {cert['notAfter']}")

    print("\n=== O QUE FAZER ".ljust(56, "="))
    if host in nomes:
        print(f"""
  '{host}' ESTÁ na lista. Então o erro de hostname não vem daqui —
  pode ser cadeia incompleta ou CA que o servidor não conhece.
""")
    else:
        # Wildcards do tipo *.provedor.com também valem — o Python resolve.
        candidatos = [n for n in nomes if not n.startswith("*")] or nomes
        sugestao = candidatos[0] if candidatos else "(nenhum)"
        print(f"""
  '{host}' NÃO está na lista — é exatamente o erro que você viu.

  Troque no .env da OCI:

      SMTP_HOST={sugestao}

  e rode o teste de novo. O envio continua criptografado E verificado.

  Se nenhum desses nomes funcionar (o provedor pode recusar autenticação
  por outro hostname), aí sim existe a saída de emergência:

      SMTP_VERIFICAR_CERT=false

  Ela mantém a criptografia mas para de conferir a identidade do servidor —
  ou seja, fica vulnerável a man-in-the-middle. Aceitável numa conta
  provisória de homologação; NÃO levar pra produção com dado real.
""")


if __name__ == "__main__":
    main()
