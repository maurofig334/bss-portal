"""
Pacote de sincronização do legado SuiteCRM (MySQL) para o BSS (Postgres).

Cada submódulo trata de UMA entidade. Todos seguem o mesmo padrão:
  - função `sync(...)` que busca do MySQL e UPSERT no Postgres
  - idempotente (pode rodar várias vezes sem duplicar)
  - chave de match: id_legado_uuid (UUID original do SuiteCRM)

Ordem recomendada de execução (dependências):
  1. sindicato         — base de tudo
  2. empresa
  3. trabalhador       — depende de empresa + sindicato
  4. lista_mensal_item — depende de trabalhador (volume alto)
  5. boleto + item     — depende de empresa + sindicato + trabalhador
  6. processo          — depende de tudo

Uso via CLI:
    python -m scripts.sync_legado --tabela sindicato
    python -m scripts.sync_legado --tabela todas
"""
