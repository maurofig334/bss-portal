"""
Descobre se o app do SuiteCRM está LONGE do banco dele.

Uso (do diretório backend/, na OCI):
    venv/bin/python -m scripts.medir_latencia_legado

A HIPÓTESE (Mauro, 17/07/2026)
------------------------------
O portal legado anda caindo "por memória e CPU". Mas se o app PHP estiver
hospedado no Brasil e o RDS MySQL em us-east-1 (Norte da Virgínia), cada query
paga ~120ms de ida e volta. Uma tela de SuiteCRM dispara dezenas de queries —
50 queries × 120ms = 6 segundos só de rede, com CPU ociosa. O sintoma parece
lentidão de servidor; a causa seria distância.

COMO DESCOBRIR SEM ACESSO AO SERVIDOR DELES
-------------------------------------------
Não temos acesso ao app (só ao banco, e read-only). Mas o IP que responde pelo
domínio do portal diz onde ele está — e o IP do RDS diz onde o banco está. Se
os dois estiverem na mesma região da AWS, a distância não é o problema e a
hipótese morre. Se estiverem em continentes diferentes, achamos a causa.

De quebra, mede a latência REAL da nossa sync até o RDS. Esse número é nosso,
não deles, e explica por que a sync leva o tempo que leva.

SOMENTE LEITURA.
"""

import socket
import time

from app.config import settings


# Domínios do legado, pra localizar o APP (o banco vem do .env).
DOMINIOS_LEGADO = [
    "portal.beneficiosocialsindical.com.br",   # portal do cliente final
    "gnb.nexussistemas.com.br",                # interface do analista interno
    "portalbsshom.nexussistemas.com.br",       # homologação
]


def _resolver(host: str) -> list[str]:
    try:
        return sorted({i[4][0] for i in socket.getaddrinfo(host, None, socket.AF_INET)})
    except Exception:
        return []


def _rtt_tcp(host: str, porta: int, tentativas: int = 5) -> float | None:
    """
    Mediana do tempo de handshake TCP. É a medida mais honesta de distância:
    não depende de ICMP (que a AWS costuma bloquear) nem de autenticação.
    """
    tempos = []
    for _ in range(tentativas):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        t0 = time.perf_counter()
        try:
            s.connect((host, porta))
            tempos.append((time.perf_counter() - t0) * 1000)
        except Exception:
            pass
        finally:
            s.close()
    if not tempos:
        return None
    tempos.sort()
    return tempos[len(tempos) // 2]


def main() -> None:
    print("\n" + "=" * 68)
    print("ONDE ESTÁ O APP, ONDE ESTÁ O BANCO, E QUANTO CUSTA A DISTÂNCIA")
    print("=" * 68)

    # --- O banco -----------------------------------------------------
    print("\n--- BANCO (RDS) ---")
    db_host = settings.MYSQL_HOST or "(não configurado)"
    print(f"  host: {db_host}")
    db_ips = _resolver(db_host) if settings.MYSQL_HOST else []
    for ip in db_ips:
        print(f"  IP  : {ip}")
    if settings.MYSQL_HOST:
        rtt = _rtt_tcp(settings.MYSQL_HOST, settings.MYSQL_PORT or 3306)
        if rtt is not None:
            print(f"  RTT desta máquina (OCI) → RDS: {rtt:.1f} ms")
            # ~1ms = mesma rede. ~10ms = mesma cidade. >100ms = outro continente.
            if rtt > 100:
                print("        └─ outro continente (>100ms)")
            elif rtt > 20:
                print("        └─ mesma região, redes diferentes")
            else:
                print("        └─ pertinho")
        else:
            print("  RTT: não respondeu (firewall? sem rota daqui?)")

    # --- O app -------------------------------------------------------
    print("\n--- APP (portal legado) ---")
    for d in DOMINIOS_LEGADO:
        ips = _resolver(d)
        if not ips:
            print(f"  {d:<42} (não resolve)")
            continue
        for ip in ips:
            rtt = _rtt_tcp(ip, 443) or _rtt_tcp(ip, 80)
            extra = f"RTT {rtt:.1f} ms" if rtt else "sem resposta em 443/80"
            print(f"  {d:<42} {ip:<16} {extra}")

    # --- Como ler ----------------------------------------------------
    print("\n" + "=" * 68)
    print("COMO LER")
    print("=" * 68)
    print("""
  1) Pegue o IP do APP e o IP do BANCO e consulte os dois em
     https://ip-ranges.amazonaws.com/ip-ranges.json  (fonte oficial da AWS:
     diz a região de cada faixa de IP).

     - MESMA região  → app e banco vizinhos. A lentidão NÃO é distância;
                       é memória/CPU mesmo, como suspeitavam.
     - Regiões DIFERENTES, ou app fora da AWS (num provedor brasileiro)
                     → cada query do SuiteCRM paga a travessia. Numa tela com
                       50 queries, são segundos de espera com o servidor
                       parado esperando rede. Otimizar CPU não resolveria nada.

  2) O RTT desta máquina até o RDS é MEDIDA NOSSA, não deles. Ele diz quanto
     a nossa sync paga por query — e por que ela é escrita em lotes grandes
     em vez de linha a linha.

  ATENÇÃO: RTT medido daqui (OCI) NÃO é o RTT do app deles. São caminhos
  diferentes. O que localiza o app é o IP + o ip-ranges.json, não o tempo
  que ELE leva pra responder pra nós.
""")


if __name__ == "__main__":
    main()
