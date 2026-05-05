# Arquitetura — BSS (Benefício Social Sindical)

## Visão geral

```
                            ┌──────────────────┐
                            │  Frontend (HTML  │
                            │  + Tailwind +    │
                            │  vanilla JS)     │
                            └────────┬─────────┘
                                     │ HTTPS
                            ┌────────▼─────────┐
                            │  FastAPI         │
                            │  (Python 3.11+)  │
                            └────────┬─────────┘
                                     │
                       ┌─────────────┴─────────────┐
                       │                           │
              ┌────────▼─────────┐       ┌─────────▼──────────┐
              │  PostgreSQL BSS  │       │  MySQL SuiteCRM    │
              │  (fonte da       │ ←sync │  (legado, leitura) │
              │   verdade)       │       │                    │
              └──────────────────┘       └────────────────────┘
```

## Perfis de usuário

| Perfil | Quem | Acessa | Ações principais |
|---|---|---|---|
| `admin` | Staff GNB | Tudo | Cadastros, configurações, gestão geral |
| `analista` | Staff GNB | Processos | Avaliar processos, conciliar boletos |
| `empresa` | Cliente | Portal próprio | Upload mensal, ver boletos, abrir processos |
| `sindicato` | Sindicato | Dashboard | Consultar trabalhadores e benefícios |

Trabalhadores **não logam** — são apenas beneficiários.

## Módulos principais (a construir)

### Cadastros
- **Sindicatos** — definem taxas e tipos de benefício
- **Tipos de Benefício** — auxílio maternidade, doença, indenizações etc., vinculados a um sindicato
- **Empresas** — clientes que pagam taxa mensal
- **Trabalhadores** — beneficiários (cadastro vem do upload mensal)
- **Usuários do portal** — quem loga e em qual perfil

### Operação
- **Upload mensal de planilha** (Empresa) — Excel padronizado com CPFs ativos
- **Geração de boleto** (automática) — qtd de trabalhadores × taxa por sindicato
- **Conciliação de boleto** (Admin/automática via webhook)
- **Processo de benefício** (Empresa abre, Analista avalia, Pagamento)
- **Gestão de documentos** (anexos do processo)

### Gestão
- **Dashboards** por perfil (Empresa, Sindicato, Analista, Admin)
- **Relatórios financeiros** (boletos, indenizações, sinistralidade)

## Estratégia de migração do SuiteCRM

Ver [`MIGRACAO.md`](MIGRACAO.md). Em resumo:
1. Construir BSS em paralelo (sem tocar no SuiteCRM)
2. Sincronizar dados continuamente (legado → BSS, unidirecional)
3. Migrar módulo por módulo — cada módulo migrado vira fonte da verdade
4. Quando todos migrados, desligar SuiteCRM

## Stack técnica

| Camada | Tecnologia | Por quê |
|---|---|---|
| Backend | FastAPI + psycopg | Validado no Nexus Web, rápido, async-friendly |
| Banco | PostgreSQL | Performance superior ao MySQL pro caso, JSONB e CTEs poderosas |
| Frontend | Tailwind + vanilla JS | Sem build step, manutenção simples |
| Auth | JWT + bcrypt | Padrão da indústria, sem sessão server-side |
| Storage | Cloudflare R2 (futuro) | Documentos de processos — barato e simples |
| Boletos | Asaas / Cobre.me / banco direto | A definir |
| Hosting | Render ou AWS do cliente | A definir |

## Princípios de modelagem

- **Tabelas normalizadas** — sem campo `_cstm` espalhado, sem JOINs gratuitos
- **Índices certeiros** — em todo `id_*` e em colunas filtradas (status, datas)
- **Soft delete via `ativo BOOLEAN`** ou `data_inativacao`
- **Auditoria via colunas `criado_em`/`atualizado_em`/`atualizado_por`** ou tabela de log paralela quando histórico crítico
- **Views como adapter** — cada módulo expõe uma view pra leitura (igual fizemos no Nexus Web)
- **Tipos enum** quando possível (status, perfil) — em vez de string livre
