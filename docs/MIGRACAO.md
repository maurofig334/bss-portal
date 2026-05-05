# Estratégia de Migração SuiteCRM → BSS

## Princípio: **construir em paralelo, migrar por módulo, sem big bang**

```
   FASE 1                    FASE 2                  FASE 3
   ──────                    ──────                  ──────

 ┌─────────┐              ┌─────────┐             ┌─────────┐
 │ SuiteCRM│              │ SuiteCRM│             │ SuiteCRM│
 │ (100%)  │   ──sync──▶  │ (-N mod)│             │ legado  │
 └─────────┘              └─────────┘             │ (off)   │
                          ┌─────────┐             └─────────┘
                          │   BSS   │             ┌─────────┐
                          │ (alguns │   ▶▶▶▶      │   BSS   │
                          │ módulos)│             │ (100%)  │
                          └─────────┘             └─────────┘
```

## Fase 1 — Sync continuo (legado → BSS)

**Objetivo:** ter todos os dados do SuiteCRM espelhados no Postgres do BSS,
atualizados automaticamente.

### Abordagens (escolher uma — começar simples)

| Abordagem | Latência | Complexidade | Recomendado quando |
|---|---|---|---|
| Script Python (cron a cada N min) | Minutos | Baixa | **Início** — começa com isso |
| Airbyte (selfhosted) | Minutos | Média | Quando tiver muitas tabelas |
| Debezium (CDC nativo) | Quase real-time | Alta | Sync crítico de baixa latência |
| Foreign Data Wrapper (FDW) | Real-time (lê ao vivo) | Baixa | **Leitura on-demand** sem replicar |

**Recomendação inicial:** começar com **script Python** + **FDW como atalho** pra
queries pontuais que ainda não foram migradas.

### Mapa de tabelas

Ver [`MAPEAMENTO_LEGADO.md`](MAPEAMENTO_LEGADO.md) para o mapa completo.
A ideia é:

```
SuiteCRM                         BSS (Postgres)
──────────────                   ─────────────
suitecrm.companies +             bss.empresas
  companies_cstm                 (1 tabela limpa)

suitecrm.workers +               bss.trabalhadores
  workers_cstm

suitecrm.unions                  bss.sindicatos
suitecrm.benefit_types           bss.tipos_beneficio
suitecrm.benefit_processes +     bss.processos_beneficio
  bp_cstm
```

## Fase 2 — Migração por módulo (cutover)

Pra cada módulo, o ciclo é:

1. **Construir** o módulo no BSS (telas + API + tabelas)
2. **Validar** com dados reais (sincronizados via Fase 1)
3. **Anunciar** a virada para os usuários (data específica)
4. **Cutover**: a partir desse dia, o módulo só funciona no BSS
   - SuiteCRM passa a ser **somente leitura** desse módulo
   - Sync inverte: BSS é fonte da verdade, mas nada escreve no SuiteCRM
5. **Monitorar** por 1-2 semanas antes de migrar o próximo módulo

### Ordem sugerida (a confirmar com a equipe GNB)

1. **Trabalhadores** (mais consultado, mais leve, baixo risco)
2. **Empresas** (cadastro estável, poucos updates)
3. **Sindicatos + Tipos de Benefício** (cadastros raros)
4. **Upload mensal + cálculo de boleto** (fluxo central — alto valor de quick win)
5. **Processos de benefício** (mais complexo — última prioridade)

### Cutover: o que muda no dia X

| Item | Antes | Depois |
|---|---|---|
| Tela de cadastro de Empresa | SuiteCRM | BSS |
| Sync de Empresa | legado → BSS | parado |
| Outros módulos do SuiteCRM (não migrados) | continuam | continuam |
| Backup do legado | sim | sim |

## Fase 3 — Desligar o SuiteCRM

Quando todos os módulos foram migrados e operam no BSS sem incidentes por
N meses:

1. SuiteCRM vira **read-only** (segurança — pra consultas históricas)
2. Após mais 3-6 meses sem acesso, **desligar** servidor
3. **Manter dump do banco** num cofre (S3 Glacier, etc.) por anos

## Rollback — plano de contingência

Pra cada módulo migrado, definir:

- **Janela de cutover** (ex: terça à 1h da manhã)
- **Como reverter rápido** (apontar URL pro SuiteCRM, pausar sync, etc.)
- **Critério de "não voltar atrás"** (ex: 7 dias sem incidente crítico)

Antes do cutover, **dump completo** do MySQL do SuiteCRM e do Postgres do BSS.
