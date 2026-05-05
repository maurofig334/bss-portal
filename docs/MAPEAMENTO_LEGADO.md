# Mapeamento SuiteCRM ↔ BSS

> **Atualizado em:** 2026-05-04 (análise inicial baseada no overview da Query 1)
> **Status:** ⏳ aguardando `SHOW CREATE TABLE` das 10 tabelas centrais para detalhar colunas

## Visão geral do legado

- **Total de tabelas no SuiteCRM da GNB:** 293
- **Banco MySQL** rodando em AWS

### Distribuição por categoria

| Categoria | Qtd | Significado |
|---|---:|---|
| NEGOCIO | 181 | Tabelas de módulos (a maioria vazia — vestígios de módulos não usados) |
| AUDITORIA | 54 | `*_audit` — log de mudanças (não migrar; histórico viável só após N meses) |
| CUSTOM | 24 | `*_cstm` — campos customizados de cada módulo (mesclar nos `bss.*` correspondentes) |
| SISTEMA | 13 | Users, roles, sessions do SuiteCRM (criamos do zero no BSS, não migra) |
| WORKFLOW | 5 | Motor de workflow do SuiteCRM (não usaremos) |
| REPORTS | 5 | Reports do SuiteCRM (não usaremos) |
| EMAIL | 4 | Sistema de email integrado (não usaremos) |
| OAUTH | 3 | OAuth do SuiteCRM (não usaremos) |
| KNOWLEDGE | 3 | Base de conhecimento do SuiteCRM (não usaremos) |
| RELACAO N-N | 1 | (categorização incompleta — várias `*_1_c` na verdade são N-N) |

### Tabelas com volume real

| Tabela | Registros | MB |
|---|---:|---:|
| `traba_trabalhadores` | 682.667 | 256 |
| `traba_trabalhadores_cstm` | 676.294 | 682 |
| `bolet_boletos` | 169.673 | 65 |
| `bolet_boletos_cstm` | 165.610 | 89 |
| `documents` | 68.513 | 34 |
| `cases` | 18.204 | 24 |
| `cases_cstm` | 17.923 | 66 |
| `pagar_contas_a_pagar` | 9.378 | 2 |
| `pagar_contas_a_pagar_cstm` | 9.064 | 2 |
| `accounts` | 7.744 | 11 |
| `accounts_cstm` | 7.706 | 6 |
| `base_base_territorial` | 3.534 | 1 |
| `contacts` | 3.106 | 4 |
| `sindi_sindicatos` | 147 | 0 |
| `cbr_parametros_boleto` | 87 | 0 |

### Tabelas N-N gigantes (causa principal da lentidão)

| Tabela N-N | Registros | Vai virar (no BSS) |
|---|---:|---|
| `bolet_boletos_traba_trabalhadores_1_c` | 4.882.174 | tabela `bss.boleto_item` |
| `sindi_sindicatos_traba_trabalhadores_1_c` | 932.730 | FK `trabalhador.id_sindicato` |
| `accounts_traba_trabalhadores_1_c` | 691.770 | FK `trabalhador.id_empresa` |
| `bolet_boletos_contacts_1_c` | 284.377 | FK `boleto.id_contato` (?) |
| `accounts_bolet_boletos_1_c` | 161.878 | FK `boleto.id_empresa` |
| `bolet_boletos_documents_1_c` | 48.253 | tabela `bss.boleto_documento` |
| `traba_trabalhadores_cases_1_c` | 18.665 | FK `processo.id_trabalhador` |
| `sindi_sindicatos_cases_1_c` | 17.940 | FK `processo.id_sindicato` |
| `cases_pagar_contas_a_pagar_1_c` | 9.297 | FK `pagamento.id_processo` |
| `accounts_sindi_sindicatos_1_c` | 8.972 | tabela `bss.empresa_sindicato` (N-N real) |
| `traba_trabalhadores_pagar_contas_a_pagar_1_c` | 5.265 | FK `pagamento.id_trabalhador` |

## Mapa SuiteCRM → BSS (preliminar)

### Entidades principais

| SuiteCRM | BSS | Observação |
|---|---|---|
| `accounts` + `accounts_cstm` | `bss.empresa` | Empresas clientes que pagam taxa |
| `traba_trabalhadores` + `traba_trabalhadores_cstm` | `bss.trabalhador` | Beneficiários (não logam) |
| `sindi_sindicatos` + `sindi_sindicatos_cstm` | `bss.sindicato` | Define taxa e tipos de benefício |
| `cases` + `cases_cstm` | `bss.processo_beneficio` | Solicitações de benefício |
| `bolet_boletos` + `bolet_boletos_cstm` | `bss.boleto` | Cobrança mensal das empresas |
| `pagar_contas_a_pagar` + `_cstm` | `bss.pagamento` | Pagamentos aos trabalhadores |
| `documents` | `bss.documento` | Anexos diversos |
| `base_base_territorial` + `_cstm` | `bss.base_territorial` | Regiões/áreas |
| `cbr_parametros_boleto` + `_cstm` | `bss.config_boleto` | Config para emissão de boletos |
| `contacts` + `contacts_cstm` | `bss.contato_empresa` | Pessoas de contato das empresas |

### O que NÃO migrar

- Todas as `*_audit` (auditoria — histórico do SuiteCRM)
- Todas as `aow_*` (workflow)
- Todas as `aok_*` (knowledge base)
- Todas as `aor_*` (reports)
- Todas as `aos_*` vazias (módulos comerciais não usados)
- `users`, `roles`, `acl_*` (criamos novos no `bss_users`)
- `oauth_*`, `inbound_email_*`, `emails*` (não usaremos)

### Tipos de benefício — discutir

A tabela `cases` (18k registros) provavelmente tem um campo `tipo` ou similar
identificando o tipo de benefício (auxílio maternidade, indenização morte, etc.).
Quando virmos o `SHOW CREATE TABLE cases_cstm`, vamos:

- Criar `bss.tipo_beneficio` (catálogo de tipos)
- `processo.id_tipo_beneficio` (FK)

## Próximo passo

Rodar `SHOW CREATE TABLE` nas 10 tabelas centrais (e suas `_cstm`) e me passar
o resultado para detalhar colunas e modelar o equivalente no BSS.
