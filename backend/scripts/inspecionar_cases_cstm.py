"""
Descobre em qual coluna de `cases_cstm` mora o PROTOCOLO do benefício.

Contexto: o protocolo que o cliente conhece (ex.: 260420817 = AA + MM da
criação + 5 sequenciais) existe no legado. Tentamos DERIVAR ele no BSS e deu
errado — derivar é palpite, sincronizar é verdade. Este script acha o campo
de origem.

Estratégia: pega os dois processos conhecidos do LEONARDO SOARES DA SILVA
    case_number 20817 → protocolo 260420817 (Falecimento)
    case_number 20669 → protocolo 260320669 (Acionamento Funeral)
e procura, em TODAS as colunas de cases_cstm, qual contém esses valores.

READ-ONLY. Uso (do diretório backend/, com venv ativa):
    python -m scripts.inspecionar_cases_cstm
"""

from app.database import get_mysql_connection
from app.config import settings


# Casos conhecidos, por UUID do case → protocolo que o portal/analista exibe.
#
# ATENÇÃO: existem (pelo menos) DOIS formatos de protocolo no legado —
#   NOVO:  9 dígitos  = AA + MM da criação + 5 sequenciais (case_number)
#          260420817 = 2026-04 + 20817
#   ANTIGO: 14 dígitos = timestamp completo? (YYYYMMDDHHMMSS)
#          20240322105945 = 2024-03-22 10:59:45 (a confirmar)
#
# Por isso NÃO dá pra derivar: a lógica mudou no meio do caminho e não sabemos
# quando nem se houve outras variações. Este script existe pra achar o campo
# de ORIGEM — se existir.
CONHECIDOS = [
    ("32690c6a-1eaf-c339-e7c2-69d3b384e015", "260420817"),      # novo, Falecimento
    ("681eeb1d-1f2b-ecb3-9a85-69c1495c82cf", "260320669"),      # novo, Acionamento
    ("80b37cdd-2c17-7aa8-b631-67770a115559", "20240322105945"),  # ANTIGO, Natalidade
]


def main() -> None:
    print("=" * 80)
    print(f"Procurando a coluna do PROTOCOLO em cases_cstm ({settings.MYSQL_DB})")
    print("=" * 80)

    with get_mysql_connection() as conn:
        with conn.cursor() as cur:

            # 1. Estrutura de cases_cstm
            cur.execute(
                """
                SELECT COLUMN_NAME, COLUMN_TYPE
                  FROM information_schema.COLUMNS
                 WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'cases_cstm'
                 ORDER BY ORDINAL_POSITION
                """,
                (settings.MYSQL_DB,),
            )
            colunas = cur.fetchall()
            print(f"\n--- cases_cstm: {len(colunas)} colunas ---")
            for c in colunas:
                print(f"    {c['COLUMN_NAME']:42s} {c['COLUMN_TYPE']}")

            # 2. Cada caso conhecido, campo a campo — inclusive `cases` inteira
            for uuid_case, protocolo_esperado in CONHECIDOS:
                print(f"\n{'=' * 76}")
                print(f"case {uuid_case}  (protocolo esperado: {protocolo_esperado})")
                print("=" * 76)
                cur.execute(
                    "SELECT c.*, cc.* FROM cases c "
                    "LEFT JOIN cases_cstm cc ON cc.id_c = c.id "
                    "WHERE c.id = %s",
                    (uuid_case,),
                )
                linhas = cur.fetchall()
                if not linhas:
                    print("    (não encontrado)")
                    continue
                for r in linhas:
                    achou = []
                    for chave, valor in r.items():
                        if valor is None:
                            continue
                        txt = str(valor).strip()
                        if not txt or txt in ("0", "0.00"):
                            continue
                        marca = ""
                        if protocolo_esperado in txt:
                            marca = "   <<<<<< PROTOCOLO AQUI"
                            achou.append(chave)
                        print(f"    {chave:42s} = {txt[:70]}{marca}")

                    print(f"\n    >>> coluna(s) com o protocolo: {achou or 'NENHUMA'}")

                    # Teste decisivo pro formato ANTIGO: o protocolo é o
                    # timestamp de criação? Se date_entered formatado como
                    # YYYYMMDDHHMMSS for igual ao protocolo, a tela CALCULA.
                    de = r.get("date_entered")
                    if de is not None:
                        try:
                            ts = de.strftime("%Y%m%d%H%M%S")
                            bate = "SIM — é o timestamp de criação" if ts == protocolo_esperado \
                                   else "não"
                            print(f"    >>> date_entered como YYYYMMDDHHMMSS = {ts}  → bate? {bate}")
                        except Exception:
                            pass

            # 2b. HIPÓTESE DO MAURO: os protocolos de 14 dígitos vieram de um
            # sistema PHP anterior, e o date_entered deles é a data da MIGRAÇÃO
            # pro SuiteCRM — não da criação real. Se for verdade, milhares de
            # cases compartilham o mesmo date_entered (o lote da migração).
            print("\n--- date_entered: dias com mais cases (pico = lote de migração) ---")
            cur.execute(
                """
                SELECT DATE(date_entered) AS dia, COUNT(*) AS n,
                       MIN(date_entered) AS primeiro, MAX(date_entered) AS ultimo,
                       MIN(case_number) AS menor_case, MAX(case_number) AS maior_case
                  FROM cases
                 WHERE deleted = 0
                 GROUP BY DATE(date_entered)
                 ORDER BY n DESC
                 LIMIT 10
                """
            )
            for r in cur.fetchall():
                print(f"    {str(r['dia'])}  {r['n']:>6,} cases  "
                      f"({r['primeiro']} → {r['ultimo']})  "
                      f"case_number {r['menor_case']}–{r['maior_case']}")

            print("\n--- date_entered: segundos exatos com mais cases ---")
            cur.execute(
                """
                SELECT date_entered, COUNT(*) AS n
                  FROM cases
                 WHERE deleted = 0
                 GROUP BY date_entered
                 ORDER BY n DESC
                 LIMIT 5
                """
            )
            for r in cur.fetchall():
                print(f"    {r['date_entered']}  {r['n']:>6,} cases")
            print("    (se algum segundo tiver milhares de cases, é o lote da")
            print("     migração PHP→SuiteCRM: date_entered NÃO é a criação real)")

            # 3. Varredura ampla: alguma coluna de QUALQUER tabela tem o valor?
            print("\n--- Varredura: colunas de cases/cases_cstm cujo nome sugere protocolo ---")
            cur.execute(
                """
                SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE
                  FROM information_schema.COLUMNS
                 WHERE TABLE_SCHEMA = %s
                   AND TABLE_NAME IN ('cases', 'cases_cstm')
                   AND (COLUMN_NAME LIKE '%%protoc%%'
                        OR COLUMN_NAME LIKE '%%numero%%'
                        OR COLUMN_NAME LIKE '%%codigo%%'
                        OR COLUMN_NAME LIKE '%%ident%%')
                 ORDER BY TABLE_NAME, COLUMN_NAME
                """,
                (settings.MYSQL_DB,),
            )
            for r in cur.fetchall():
                print(f"    {r['TABLE_NAME']}.{r['COLUMN_NAME']:38s} {r['COLUMN_TYPE']}")

    print("\n" + "=" * 80)
    print("Se NENHUMA coluna contiver o protocolo, ele é CALCULADO na tela do")
    print("legado (a partir de date_entered + case_number) e não está gravado.")
    print("Nesse caso, derivar no BSS é legítimo — mas usando date_entered,")
    print("que agora o sync grava corretamente em criado_em.")
    print("=" * 80)


if __name__ == "__main__":
    main()
