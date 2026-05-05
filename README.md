# BSS — Benefício Social Sindical

Sistema de gestão de benefícios sociais para trabalhadores sindicalizados.
Substituirá gradualmente o SuiteCRM legado da GNB, mantendo os bancos
sincronizados durante a transição.

## Sobre o projeto

O BSS é o portal SaaS B2B/B2B2C da GNB que serve 4 perfis de usuário:

- **Empresas** — fazem upload mensal de trabalhadores ativos, recebem boletos,
  abrem processos de benefícios
- **Sindicatos** — definem taxas e tipos de benefício, consultam dashboards
- **Analistas GNB** — analisam processos, conciliam pagamentos
- **Administradores GNB** — gerenciam cadastros e operação

Trabalhadores **não logam** — são apenas beneficiários nos processos.

## Volumetria atual (do legado)

- ~5.000 empresas
- ~300.000 trabalhadores ativos
- ~130 sindicatos
- ~5.000 boletos gerados por mês

## Stack

- **Backend:** FastAPI (Python 3.11+)
- **Banco:** PostgreSQL
- **Frontend:** HTML + Tailwind + JS vanilla (sem framework)
- **Auth:** JWT + bcrypt
- **Hosting:** decisão pendente (Render ou AWS do cliente)

## Estrutura de pastas

```
BSS/
├── backend/
│   ├── app/             ← código Python (FastAPI)
│   ├── frontend/        ← HTML + CSS + JS estáticos
│   ├── scripts/         ← scripts utilitários (extrair schema, sync, ...)
│   ├── requirements.txt
│   ├── .env.example
│   └── run.ps1
├── docs/                ← documentação técnica
│   ├── ARQUITETURA.md
│   ├── MAPEAMENTO_LEGADO.md
│   └── MIGRACAO.md
└── README.md
```

## Como rodar localmente

```powershell
cd backend

# 1. Criar venv
python -m venv venv
.\venv\Scripts\Activate.ps1

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Configurar credenciais
copy .env.example .env
notepad .env

# 4. Rodar
.\run.ps1
```

Depois abre <http://localhost:8000>.

## Documentação

- [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md) — visão geral, perfis, módulos
- [`docs/MAPEAMENTO_LEGADO.md`](docs/MAPEAMENTO_LEGADO.md) — equivalência SuiteCRM ↔ BSS
- [`docs/MIGRACAO.md`](docs/MIGRACAO.md) — estratégia de sync e cutover por módulo
