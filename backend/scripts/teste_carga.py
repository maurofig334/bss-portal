"""
Teste de carga — simula N clientes simultâneos batendo nas telas.

Uso (na OCI, é de lá que vale medir):
    venv/bin/python -m scripts.teste_carga EMAIL SENHA
    venv/bin/python -m scripts.teste_carga EMAIL SENHA --url http://127.0.0.1:8000
    venv/bin/python -m scripts.teste_carga EMAIL SENHA --niveis 1,10,25,50,100

O QUE FAZ
---------
Loga UMA vez e reusa o token entre todos os "clientes virtuais". (Logar por
cliente mediria o bcrypt do login — que é caro de propósito — em vez do
desempenho das telas.) Depois dispara uma rotação de endpoints SÓ DE LEITURA em
concorrência crescente, e mostra latência p50/p95/p99, vazão e erros por nível.

READ-ONLY: só GETs de listagem/dashboard. Não liquida, não envia e-mail, não
cria nada. Seguro rodar em produção.

DUAS FORMAS DE MEDIR
--------------------
  --url https://bss.nexussistemas.com.br  (padrão)
      Caminho completo: DNS + nginx + TLS + app + banco. É a experiência real
      do cliente.
  --url http://127.0.0.1:8000
      Bypassa nginx/TLS. Isola app + banco — útil pra saber se o gargalo é a
      aplicação ou a borda.

CAVEAT: rodar o gerador de carga NA MESMA máquina do servidor faz os dois
disputarem CPU, o que piora um pouco os números. Pra medida limpa, rodar de
outra máquina. Como aproximação, serve — e o padrão (p95 disparando com a
concorrência) aparece de qualquer jeito.

O QUE PROCURAR
--------------
- p95/p99 ESTÁVEL conforme a concorrência sobe = aguenta.
- p95 DISPARANDO a partir de certo nível = teto atingido (provável: 1 worker
  do uvicorn e/ou conexão nova por request sem pool). Aí a recomendação é
  --workers N no systemd + pool de conexões.
- Erros > 0 = ou timeout, ou o Postgres recusou conexão (max_connections).
"""

import argparse
import json
import ssl
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlencode


# Rotação de uma "sessão típica": o que um usuário abre ao navegar.
# Só leitura. Cada tupla é (rótulo, caminho).
ENDPOINTS = [
    ("dashboard_kpis",   "/dashboard/kpis"),
    ("empresas_p1",      "/empresas?por_pagina=50&ordem=razao_social"),
    ("trabalhadores_p1", "/trabalhadores?por_pagina=50&situacao=ativo"),
    ("beneficios_p1",    "/processos?por_pagina=50"),
    ("boletos_p1",       "/boletos?por_pagina=50"),
    ("contas_pagar_p1",  "/contas-pagar?por_pagina=50&status=pendente"),
    ("sino_beneficios",  "/processos/aguardando-resposta/contagem"),
]


def _ctx():
    # O cert é válido; mas se apontarem pro IP/localhost via https daria
    # mismatch. Só relaxa a verificação (isto é medição, não tráfego real).
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE
    return c


def login(base: str, email: str, senha: str) -> str:
    body = urlencode({"username": email, "password": senha}).encode()
    req = urllib.request.Request(
        f"{base}/auth/login", data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, context=_ctx(), timeout=30) as r:
        return json.loads(r.read())["access_token"]


def _uma_req(base: str, token: str, caminho: str) -> tuple[float, int]:
    """Retorna (latência_ms, status). status -1 = exceção/timeout."""
    req = urllib.request.Request(
        f"{base}{caminho}", headers={"Authorization": f"Bearer {token}"}
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, context=_ctx(), timeout=30) as r:
            r.read()
            return (time.perf_counter() - t0) * 1000, r.status
    except urllib.error.HTTPError as e:
        return (time.perf_counter() - t0) * 1000, e.code
    except Exception:
        return (time.perf_counter() - t0) * 1000, -1


def rodar_nivel(base: str, token: str, concorrencia: int,
                reqs_por_cliente: int) -> dict:
    """Cada cliente virtual faz `reqs_por_cliente` requests, girando a rotação."""
    latencias: list[float] = []
    erros = 0
    lock = threading.Lock()

    def cliente(cid: int):
        nonlocal erros
        locais = []
        e = 0
        for i in range(reqs_por_cliente):
            _, caminho = ENDPOINTS[(cid + i) % len(ENDPOINTS)]
            ms, status = _uma_req(base, token, caminho)
            locais.append(ms)
            if status < 200 or status >= 400:
                e += 1
        with lock:
            latencias.extend(locais)
            erros += e

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concorrencia) as ex:
        futs = [ex.submit(cliente, c) for c in range(concorrencia)]
        for f in as_completed(futs):
            f.result()
    dur = time.perf_counter() - t0

    latencias.sort()
    n = len(latencias)
    def pct(p):
        return latencias[min(n - 1, int(n * p / 100))] if n else 0
    return {
        "concorrencia": concorrencia,
        "total_reqs": n,
        "duracao_s": dur,
        "vazao": n / dur if dur else 0,
        "p50": pct(50), "p95": pct(95), "p99": pct(99),
        "media": statistics.mean(latencias) if latencias else 0,
        "max": latencias[-1] if latencias else 0,
        "erros": erros,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("email")
    ap.add_argument("senha")
    ap.add_argument("--url", default="https://bss.nexussistemas.com.br")
    ap.add_argument("--niveis", default="1,5,10,25,50",
                    help="níveis de concorrência, vírgula-separados")
    ap.add_argument("--reqs", type=int, default=20,
                    help="requests por cliente virtual em cada nível")
    args = ap.parse_args()
    base = args.url.rstrip("/")
    niveis = [int(x) for x in args.niveis.split(",")]

    print(f"\nAlvo: {base}")
    print("Logando (uma vez, token reutilizado)…")
    try:
        token = login(base, args.email, args.senha)
    except Exception as e:
        print(f"✗ login falhou: {e}")
        sys.exit(1)
    print("ok.\n")

    print(f"{'conc':>5} {'reqs':>6} {'vazão/s':>9} "
          f"{'p50':>7} {'p95':>7} {'p99':>7} {'máx':>8} {'erros':>6}")
    print("-" * 60)
    for c in niveis:
        r = rodar_nivel(base, token, c, args.reqs)
        marca = "  ⚠" if r["p95"] > 1000 or r["erros"] else ""
        print(f"{r['concorrencia']:>5} {r['total_reqs']:>6} {r['vazao']:>9.1f} "
              f"{r['p50']:>6.0f}m {r['p95']:>6.0f}m {r['p99']:>6.0f}m "
              f"{r['max']:>7.0f}m {r['erros']:>6}{marca}")

    print("""
Leitura:
  - p95 estável conforme a concorrência sobe = aguenta o volume testado.
  - p95 crescendo muito a partir de um nível = teto (provável 1 worker uvicorn
    + conexão nova por request). Fix: --workers N no systemd + pool de conexões.
  - erros > 0 = timeout ou Postgres recusando conexão (max_connections).
  - 'm' = milissegundos.
""")


if __name__ == "__main__":
    main()
