"""
Testa o SMTP sem depender de mensagem real.

Uso (do diretório backend/):
    venv/bin/python -m scripts.testar_email seu@email.com

POR QUE
-------
O envio roda em BackgroundTask e engole exceções de propósito (notificação
nunca pode derrubar a operação). Ótimo em produção, péssimo pra descobrir que
a senha do SMTP está errada — a falha vai só pro log e o usuário não vê nada.

Este script chama o mesmo caminho de envio, mas mostra o erro na cara.
Rodar UMA VEZ depois de configurar o .env, antes de confiar no canal.
"""

import sys

from app.config import settings
from app.notificacao import _enviar, _habilitado, _remetente


def main() -> None:
    if len(sys.argv) < 2:
        print("uso: python -m scripts.testar_email destino@exemplo.com")
        return
    destino = sys.argv[1].strip()

    print("\n=== CONFIGURAÇÃO SMTP ".ljust(56, "="))
    print(f"  host      : {settings.SMTP_HOST or '(vazio)'}")
    print(f"  porta     : {settings.SMTP_PORT}")
    print(f"  usuário   : {settings.SMTP_USER or '(vazio)'}")
    print(f"  senha     : {'definida' if settings.SMTP_PASSWORD else '(vazia)'}")
    print(f"  SSL direto: {settings.SMTP_SSL}  (False = STARTTLS)")
    print(f"  remetente : {_remetente() or '(vazio)'}")
    print(f"  base URL  : {settings.APP_BASE_URL}")

    if not _habilitado():
        print("\n✗ SMTP desligado: faltam SMTP_HOST e/ou SMTP_USER no .env.")
        print("  Nesse estado o app roda normal — só não manda e-mail.")
        return

    print(f"\nEnviando teste para {destino}…")

    # _enviar engole exceção. Aqui queremos VER o erro, então repetimos o
    # caminho com o log em nível DEBUG e checamos o retorno pelo log.
    import logging
    logging.basicConfig(level=logging.INFO, format="  [%(levelname)s] %(message)s")

    _enviar(
        [destino],
        "BSS — teste de configuração de e-mail",
        "Se você está lendo isto, o SMTP do BSS está funcionando.\n\n"
        "Mensagem de teste gerada por scripts/testar_email.py.",
        "<p>Se você está lendo isto, o SMTP do BSS está funcionando.</p>"
        "<p style='color:#94a3b8;font-size:12px'>Mensagem de teste gerada por "
        "<code>scripts/testar_email.py</code>.</p>",
    )

    print("\n  Se apareceu 'e-mail enviado' acima, deu certo — confira a caixa")
    print("  (e o spam: remetente novo costuma cair lá na primeira vez).")
    print("  Se apareceu 'falha ao enviar', a mensagem do erro está na linha.")
    print()


if __name__ == "__main__":
    main()
