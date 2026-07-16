"""
DEMO: aponta o arquivo_url dos documentos de um processo pros arquivos locais.

Contexto: o sync traz metadado + status, mas o binário fica no servidor do
SuiteCRM (AWS, sem acesso ainda) — então arquivo_url guarda um ponteiro
`legado://...`, que não abre. Pra apresentação ao cliente, baixamos à mão os
documentos de UM processo e apontamos o arquivo_url pra eles.

Os arquivos ficam em backend/frontend/arquivos/, que o main.py já serve em
/app/arquivos/ (StaticFiles). Nada de backend novo.

Isso é ESCADA, não andaime: quando os binários vierem da AWS, o mecanismo de
servir arquivo já existe — muda só a origem e o valor do arquivo_url.

Uso (do diretório backend/, com venv ativa e o tunnel do Postgres no ar):
    python -m scripts.demo_apontar_arquivos --protocolo 260420817
    python -m scripts.demo_apontar_arquivos --cpf 416.672.518-13
    python -m scripts.demo_apontar_arquivos --cpf 41667251813 --dry-run
"""

from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path
from urllib.parse import quote

from app.database import get_pg_connection


DIR_ARQUIVOS = Path(__file__).resolve().parent.parent / "frontend" / "arquivos"
URL_BASE = "/app/arquivos"


def normalizar(nome: str) -> str:
    """
    Normaliza pra casar nome do legado com nome do arquivo baixado:
      - tira acentos, caixa e extensão
      - remove o sufixo ' (1)' que o Chrome põe em download repetido
      - colapsa espaços/underscores
    """
    if not nome:
        return ""
    n = Path(nome).stem                       # tira extensão
    n = re.sub(r"\s*\(\d+\)\s*$", "", n)      # tira " (1)"
    n = unicodedata.normalize("NFKD", n)
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = re.sub(r"[_\s]+", " ", n).strip().lower()
    return n


def indexar_arquivos() -> dict[str, Path]:
    """nome normalizado → caminho do arquivo em frontend/arquivos/."""
    if not DIR_ARQUIVOS.exists():
        raise SystemExit(f"ERRO: pasta não encontrada: {DIR_ARQUIVOS}")
    idx: dict[str, Path] = {}
    for p in sorted(DIR_ARQUIVOS.iterdir()):
        if p.is_file() and not p.name.startswith("."):
            # o primeiro vence: 'CPF LEONARDO.jpeg' antes de 'CPF LEONARDO (1).jpeg'
            idx.setdefault(normalizar(p.name), p)
    return idx


SQL_PROCESSOS = """
    SELECT p.id, p.protocolo, p.numero_processo, p.status,
           t.nome_completo, tb.nome AS tipo,
           (SELECT COUNT(*) FROM bss.processo_documento pd
             WHERE pd.id_processo = p.id) AS qtd_docs
      FROM bss.processo_beneficio p
      LEFT JOIN bss.trabalhador t     ON t.id = p.id_trabalhador
      LEFT JOIN bss.tipo_beneficio tb ON tb.id = p.id_tipo_beneficio
     WHERE {filtro}
     ORDER BY qtd_docs DESC, p.criado_em DESC
"""


def listar_processos(cur, id_processo, protocolo, cpf) -> list[dict]:
    """
    Um trabalhador costuma ter VÁRIOS processos (ex.: Falecimento e Acionamento
    Funeral do mesmo falecido). Por isso listamos em vez de adivinhar.
    """
    if id_processo:
        cur.execute(SQL_PROCESSOS.format(filtro="p.id = %s"), (id_processo,))
    elif protocolo:
        cur.execute(
            SQL_PROCESSOS.format(filtro="p.protocolo = %s OR p.numero_processo::text = %s"),
            (protocolo, protocolo),
        )
    elif cpf:
        digitos = re.sub(r"\D", "", cpf)
        cur.execute(SQL_PROCESSOS.format(filtro="t.cpf = %s"), (digitos,))
    else:
        return []
    return list(cur.fetchall())


def mostrar_processos(procs: list[dict]) -> None:
    print("\nProcessos encontrados (ordenados por qtd de documentos):")
    for p in procs:
        prot = p["protocolo"] or p["numero_processo"] or "—"
        print(f"   id={p['id']:<8} {str(p['tipo'] or '?')[:22]:22s} "
              f"protocolo={str(prot):12s} status={str(p['status'])[:22]:22s} "
              f"docs={p['qtd_docs']}")
    print("\nEscolha um com --id-processo <id>.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id-processo", type=int, help="id do processo no BSS (mais preciso)")
    ap.add_argument("--protocolo", help="protocolo ou numero_processo")
    ap.add_argument("--cpf", help="CPF do trabalhador (lista os processos dele)")
    ap.add_argument("--dry-run", action="store_true", help="não grava, só mostra o que faria")
    args = ap.parse_args()

    if not args.id_processo and not args.protocolo and not args.cpf:
        ap.error("informe --id-processo, --protocolo ou --cpf")

    idx = indexar_arquivos()
    print("=" * 78)
    print(f"Arquivos locais em {DIR_ARQUIVOS.name}/: {len(idx)}")
    for k, p in idx.items():
        print(f"   {k:45s} → {p.name}")
    print("=" * 78)

    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            procs = listar_processos(cur, args.id_processo, args.protocolo, args.cpf)
            if not procs:
                raise SystemExit("ERRO: nenhum processo encontrado no BSS. "
                                 "Rodou o sync de processo?")
            if len(procs) > 1 and not args.id_processo:
                # Não adivinhar: um trabalhador tem vários processos.
                print(f"\n{procs[0]['nome_completo']} tem {len(procs)} processos.")
                mostrar_processos(procs)
                raise SystemExit(0)
            proc = procs[0]
            print(f"\nProcesso: id={proc['id']} · {proc['tipo']} · "
                  f"protocolo={proc['protocolo'] or proc['numero_processo']} · "
                  f"{proc['nome_completo']} · {proc['qtd_docs']} documento(s)")

            cur.execute("""
                SELECT pd.id AS id_pdoc, pd.status, pd.versao,
                       d.id AS id_doc, d.nome_original, d.arquivo_url,
                       tbd.nome AS tipo_documento
                  FROM bss.processo_documento pd
                  JOIN bss.tipo_beneficio_documento tbd ON tbd.id = pd.id_tipo_documento
                  LEFT JOIN bss.documento d ON d.id = pd.id_documento
                 WHERE pd.id_processo = %s
                 ORDER BY tbd.ordem, pd.versao
            """, (proc["id"],))
            docs = cur.fetchall()
            if not docs:
                raise SystemExit("ERRO: processo sem documentos em bss.processo_documento. "
                                 "Rode: sync_legado --tabela documento")

            print(f"Documentos no BSS: {len(docs)}\n")
            casados, orfaos = 0, []
            for d in docs:
                nome = d["nome_original"] or ""
                arq = idx.get(normalizar(nome))
                marca = "OK " if arq else "-- "
                print(f"  {marca}[{str(d['status']):9s}] {str(d['tipo_documento'])[:34]:34s} "
                      f"{nome[:34]:34s} → {arq.name if arq else 'SEM ARQUIVO LOCAL'}")
                if not arq:
                    orfaos.append(nome)
                    continue
                casados += 1
                if not args.dry_run and d["id_doc"]:
                    url = f"{URL_BASE}/{quote(arq.name)}"
                    cur.execute(
                        "UPDATE bss.documento SET arquivo_url = %s, tamanho_bytes = %s WHERE id = %s",
                        (url, arq.stat().st_size, d["id_doc"]),
                    )
            if not args.dry_run:
                conn.commit()

    print(f"\n{'[dry-run] ' if args.dry_run else ''}{casados} de {len(docs)} documento(s) "
          f"apontados pros arquivos locais.")
    if orfaos:
        print(f"{len(orfaos)} sem arquivo local (seguem com ponteiro legado://):")
        for o in orfaos:
            print(f"   - {o}")
    if not args.dry_run and casados:
        print("\nPronto. Abra o benefício no BSS e clique nos arquivos do checklist.")


if __name__ == "__main__":
    main()
