# Plano de Big Bang — BSS substituindo SuiteCRM/MySQL

Este doc é a referência da estratégia de transição. Confirmado com cliente em
2026-05-09. Big Bang previsto pra **30-60 dias** após esta data.

## Conceitos

- **Legado**: SuiteCRM/MySQL (`gnb_crm` em `suitecrmbd.c08lydj0oykz.us-east-1.rds.amazonaws.com`).
  É a **fonte da verdade até o Big Bang**. READ-ONLY pelo BSS — qualquer escrita
  tem que ser via app legado.
- **BSS**: PostgreSQL na OCI (`140.238.178.43`). Hoje funciona como espelho
  enriquecido + sandbox de novas features. Vira a fonte da verdade após o Big Bang.
- **Sync diário**: rotina que copia o estado do legado pro BSS, **sem destruir
  metadados criados no BSS**.

## Categorização das tabelas

### A. Tabelas espelhadas (vêm do legado — TRUNCATE no Big Bang)

Todas têm `id_legado_uuid` e são reconstruídas a partir do legado.

- `bss.empresa` (ex: 5.105 linhas)
- `bss.sindicato` (ex: 132 linhas)
- `bss.trabalhador` (~6.1M linhas)
- `bss.boleto` (~162k linhas)
- `bss.boleto_item` (~4.9M linhas)
- `bss.parametros_boleto` (~132 linhas)
- `bss.processo_beneficio` (~18k linhas)
- `bss.processo_andamento` / `bss.processo_mensagem`

Em cada uma dessas, **registros sem `id_legado_uuid`** são "BSS-only" — criados
pela operação interna do BSS (ex: usuário gerou boleto pela tela nova). Esses
serão **descartados no Big Bang** (TRUNCATE pega tudo). Documente isso pros
usuários de teste.

### B. Tabelas de meta-dados do BSS (sobrevivem ao Big Bang)

Não existem no legado. Devem ser preservadas.

- `bss_users` — login do portal
- `bss.usuario_empresa` / `bss.usuario_sindicato` — vínculos N:N
- `bss.dropdown` — catálogos (tipo de benefício, etc)
- `bss.tipo_beneficio`, `bss.status_processo`, `bss.base_territorial` —
  catálogos populados manualmente

### C. Tabelas operacionais novas do BSS (decidir caso a caso)

Hoje o BSS tem features que o legado não tem. Avaliar uma a uma:

- `bss.lista_mensal` / `bss.lista_mensal_item` — uploads de planilha mensal
  via tela do BSS. **Decisão**: descartar no Big Bang (TRUNCATE) — a partir do
  BB, esses uploads passam a ser feitos pelo BSS de produção, e os de teste
  não importam.
- `bss.trabalhador_lacunas` — derivada de lista_mensal_item. Idem.

## Sync diário (configuração)

Cron na OCI rodando todo dia às **03:00 GMT (00:00 BRT)**:

```cron
0 3 * * * cd /home/opc/bss-portal/backend && \
    ./venv/bin/python -m scripts.sync_legado --tabela todas \
    >> /home/opc/bss-portal/logs/cron-sync.log 2>&1
```

Depois de rodar, conferir o log:

```bash
tail -50 /home/opc/bss-portal/logs/cron-sync.log
```

### Garantias de idempotência

Todas as `app/sync/*.py` usam `INSERT ... ON CONFLICT (id_legado_uuid) DO UPDATE`,
então rodar 2x não duplica e não corrompe.

### Soft-delete

A partir de 2026-05-09 (versão atualizada do `app/sync/boleto.py`), boletos com
`deleted=1` no legado vêm pro BSS com `status='cancelado'` (não removemos pra
preservar histórico). Mesma lógica deve ser aplicada nos outros syncs conforme
necessário.

## Procedimento do Big Bang

Quando chegar o dia D (em 30-60 dias):

1. **D-1**: comunicar usuários — "amanhã 02:00, sistema indisponível 30min, BSS assume"
2. **D 02:00**: parar o legado (ou colocar em modo read-only)
3. **D 02:05**: rodar último sync completo:
   ```bash
   python -m scripts.sync_legado --tabela todas
   ```
4. **D 02:15**: TRUNCATE seletivo das tabelas C (operacionais novas) que devem
   começar limpas. Por enquanto, lista candidata:
   ```sql
   TRUNCATE bss.lista_mensal_item RESTART IDENTITY CASCADE;
   TRUNCATE bss.lista_mensal      RESTART IDENTITY CASCADE;
   ```
5. **D 02:20**: descartar boletos BSS-only se houver (decisão a tomar):
   ```sql
   DELETE FROM bss.boleto_item bi
    USING bss.boleto b
    WHERE bi.id_boleto = b.id AND b.id_legado_uuid IS NULL AND b.tipo = 'Sistema';
   DELETE FROM bss.boleto WHERE id_legado_uuid IS NULL AND tipo = 'Sistema';
   ```
6. **D 02:25**: desativar cron de sync (`crontab -e` e comentar a linha)
7. **D 02:30**: BSS assume — apontar usuários pro novo portal
8. **D+1**: monitorar erros, dúvidas

## Riscos conhecidos

- **Schema drift**: se o legado adicionar coluna nova entre hoje e o BB, o sync
  não pega — precisa mexer em `app/sync/<tabela>.py` antes do BB.
- **IDs autogerados**: `bss.<tabela>.id` (BIGSERIAL) são independentes do
  legado. Se algum sistema externo apontar pra esses IDs, vai precisar de
  remap. Pra essa fase de transição não se aplica.
- **Boletos gerados por usuários reais via BSS** (não testes): se algum
  cliente real gerar boleto pelo BSS antes do BB e cobrar a empresa, o registro
  é "BSS-only". No BB, esse boleto **será apagado** do BSS — então o cliente
  precisa ter o PDF salvo localmente. Comunicar isso pros betas.

## Status atual

- ✅ Sync de boleto ajustado pra usar `cnpj_empresa_c` + tratar `deleted=1` (2026-05-09)
- ⏳ Cron diário ainda não configurado na OCI (task #33)
- ⏳ Validar que todos os outros syncs (empresa, sindicato, trabalhador, processo)
  tratam `deleted=1` corretamente
