"""
CLI de sincronização do legado SuiteCRM (MySQL) → BSS (Postgres).

Uso (do diretório backend/, com venv ativa):

    # Listar tabelas suportadas
    python -m scripts.sync_legado --listar

    # Dry-run de sindicato (lê e mostra amostra, não grava)
    python -m scripts.sync_legado --tabela sindicato --dry-run

    # Sync de sindicato (grava)
    python -m scripts.sync_legado --tabela sindicato

    # Limitar a N linhas (útil pra primeiro teste)
    python -m scripts.sync_legado --tabela sindicato --limite 5

    # Sync de TODAS as entidades na ordem correta
    python -m scripts.sync_legado --tabela todas
"""

from __future__ import annotations

import argparse
import sys
import time

from app.sync import sindicato as sync_sindicato
from app.sync import empresa as sync_empresa
from app.sync import trabalhador as sync_trabalhador
from app.sync import boleto as sync_boleto
from app.sync import boleto_item as sync_boleto_item
from app.sync import processo as sync_processo
from app.sync import processo_mensagem as sync_processo_mensagem


# Mapa: nome CLI → função sync()
TABELAS = {
    "sindicato":          sync_sindicato.sync,
    "empresa":            sync_empresa.sync,
    "trabalhador":        sync_trabalhador.sync,
    "boleto":             sync_boleto.sync,
    "boleto_item":        sync_boleto_item.sync,
    "processo":           sync_processo.sync,
    "processo_mensagem":  sync_processo_mensagem.sync,
}

# Ordem recomendada quando rodar "todas"
ORDEM_TODAS = [
    "sindicato",
    "empresa",
    "trabalhador",
    "boleto",
    "boleto_item",
    "processo",
    "processo_mensagem",
]


def _executar(nome: str, dry_run: bool, limite: int | None) -> None:
    fn = TABELAS.get(nome)
    if not fn:
        print(f"❌ Tabela '{nome}' não suportada. Veja --listar.")
        sys.exit(2)
    inicio = time.time()
    qtd = fn(dry_run=dry_run, limite=limite)
    dur = time.time() - inicio
    print(f"\n→ {nome}: {qtd} linhas em {dur:.1f}s")


def main() -> None:
    p = argparse.ArgumentParser(description="Sync SuiteCRM → BSS")
    p.add_argument("--tabela", help="nome da tabela (ou 'todas')")
    p.add_argument("--listar", action="store_true", help="lista tabelas suportadas")
    p.add_argument("--dry-run", action="store_true", help="só lê e mostra amostra")
    p.add_argument("--limite", type=int, help="limita linhas (teste)")
    args = p.parse_args()

    if args.listar:
        print("Tabelas suportadas:")
        for n in TABELAS:
            print(f"  - {n}")
        print("  - todas (executa na ordem correta)")
        return

    if not args.tabela:
        p.error("informe --tabela ou --listar")

    if args.tabela == "todas":
        for nome in ORDEM_TODAS:
            _executar(nome, args.dry_run, args.limite)
    else:
        _executar(args.tabela, args.dry_run, args.limite)


if __name__ == "__main__":
    main()
