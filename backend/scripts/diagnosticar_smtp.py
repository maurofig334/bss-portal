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


def _nomes_via_openssl(pem: str) -> list[str]:
    """
    Extrai CN + subjectAltName usando o openssl da máquina.

    Existe porque o projeto não tem a lib `cryptography` nas dependências, e
    não vale adicioná-la só pra um script de diagnóstico. O openssl está em
    qualquer Linux — e na OCI é o mesmo binário que emitiu nosso certificado
    do bss.nexussistemas.com.br.
    """
    import subprocess
    nomes: list[str] = []
    try:
        r = subprocess.run(
            ["openssl", "x509", "-noout", "-subject", "-issuer",
             "-enddate", "-ext", "subjectAltName"],
            input=pem, capture_output=True, text=True, timeout=15,
        )
        saida = r.stdout + r.stderr
    except Exception:
        return []

    for linha in saida.splitlines():
        linha = linha.strip()
        if linha.startswith("subject=") and "CN" in linha:
            for parte in linha.split(","):
                if "CN" in parte and "=" in parte:
                    nomes.append(parte.split("=", 1)[1].strip())
        elif linha.startswith("DNS:"):
            for item in linha.split(","):
                item = item.strip()
                if item.startswith("DNS:"):
                    nomes.append(item[4:].strip())
        elif linha.startswith("issuer=") or linha.startswith("notAfter="):
            print(f"  {linha}")

    return sorted(set(n for n in nomes if n))


def _casa(host: str, nome: str) -> bool:
    """Wildcard do certificado cobre o host? (*.provedor.com casa com a.provedor.com)"""
    if nome == host:
        return True
    if nome.startswith("*."):
        sufixo = nome[1:]                       # ".provedor.com"
        # Wildcard cobre UM nível só: *.x.com casa a.x.com, não a.b.x.com
        return host.endswith(sufixo) and host.count(".") == nome.count(".")
    return False


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

    # ATENÇÃO: com verify_mode=CERT_NONE, getpeercert() devolve {} — o Python
    # só monta o dicionário quando VALIDOU o certificado. Mas
    # getpeercert(binary_form=True) devolve o DER mesmo sem validar. Então
    # pegamos os bytes e mandamos o openssl decodificar.
    try:
        if porta == 465:
            with smtplib.SMTP_SSL(host, porta, context=ctx, timeout=20) as s:
                der = s.sock.getpeercert(binary_form=True)
        else:
            with smtplib.SMTP(host, porta, timeout=20) as s:
                s.starttls(context=ctx)
                der = s.sock.getpeercert(binary_form=True)
    except Exception as e:
        print(f"  ✗ falhou ao conectar: {e}")
        return

    if not der:
        print("  ⚠ conectou, mas o servidor não apresentou certificado.")
        return

    nomes = _nomes_via_openssl(ssl.DER_cert_to_PEM_cert(der))
    if not nomes:
        print("  ⚠ não consegui decodificar o certificado (openssl ausente?).")
        print("     Rode à mão:")
        print(f"     openssl s_client -starttls smtp -connect {host}:{porta} "
              f"</dev/null 2>/dev/null | openssl x509 -noout -subject -ext subjectAltName")
        return

    cert = {}   # mantido pra não quebrar os prints de emissor/validade abaixo
    print("\n=== O certificado é válido para ".ljust(56, "="))
    for n in nomes:
        marca = "  ← casa com o seu SMTP_HOST" if _casa(host, n) else ""
        print(f"  {n}{marca}")

    print("\n=== O QUE FAZER ".ljust(56, "="))
    if any(_casa(host, n) for n in nomes):
        print(f"""
  '{host}' ESTÁ na lista. Então o erro de hostname não vem daqui —
  pode ser cadeia incompleta ou CA que o servidor não conhece.
""")
    else:
        # Nome concreto é melhor sugestão que wildcard: o usuário copia e cola.
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
