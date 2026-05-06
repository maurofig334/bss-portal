"""
Pacote de sincronização do legado SuiteCRM (MySQL) para o BSS (Postgres).

Cada submódulo trata de UMA entidade. Todos seguem o mesmo padrão:
  - função `sync(...)` que busca do MySQL e UPSERT no Postgres
  - idempotente (pode rodar várias vezes sem duplicar)
  - chave de match: id_legado_uuid (UUID original do SuiteCRM)

Ordem recomendada de execução (dependências):
  1. sindicato          — base de tudo
  2. empresa
  3. trabalhador        — depende de empresa + sindicato (com fallback N-N)
  4. boleto             — depende de empresa
  5. boleto_item        — depende de boleto + trabalhador (a "killer table" 4.9M)
  6. processo           — depende de tudo + N-Ns case→trab/sind
  7. processo_mensagem  — depende de processo (33k mensagens AOP)

Status (2026-05-05): sync completo, ~6.1M linhas em 6 minutos.

Uso via CLI:
    python -m scripts.sync_legado --tabela sindicato
    python -m scripts.sync_legado --tabela todas
"""
