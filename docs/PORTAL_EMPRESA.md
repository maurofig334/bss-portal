# Portal da Empresa — levantamento do legado

> **Origem:** telas do portal legado (`portal.beneficiosocialsindical.com.br`),
> capturadas em 17/07/2026 com o login `maurofig334@gmail.com` (perfil empresa,
> 11 CNPJs vinculados).
>
> **Por que este documento existe:** o servidor do portal legado na AWS anda
> caindo por memória e CPU — caiu no meio deste próprio levantamento. Não temos
> acesso àquele servidor (só ao banco, e read-only), então não controlamos
> quando ele volta. O que está aqui foi lido das telas; o que não está, não foi
> visto. **Nada aqui é dedução.**
>
> Marcações usadas:
> - ✅ observado na tela
> - ❓ **pendente de confirmação com a BSS** — não implementar por conta própria

---

## 1. O que o portal é

Três perfis usam o BSS hoje: a equipe interna (analistas), a empresa cliente e
a funerária. Este documento trata **só da empresa**.

O dashboard da empresa **não é o dashboard interno filtrado** — é outra tela.
Não tem KPI, não tem faturamento, não tem série mensal. Tem três listas de
*recentes* e os botões de ação à mão:

| Bloco | Botões |
|---|---|
| RECENTE Benefícios | `Adicionar` |
| RECENTE Boletos | `Gerar Boleto por CNPJ`, `Reemitir` (por linha) |
| RECENTE Trabalhadores / Dependentes | `Carregar Trabalhadores`, `Inativar Trabalhadores`, `Carregar Dependentes`, `Adicionar Trab./Dep.` |

Menu lateral do portal legado (7 itens): Dashboard, Benefícios, Boletos,
~~Documentos~~, Empresas, Sindicatos, Trabalhadores/Dependentes.

- **Documentos — NÃO REPLICAR.** ✅ Decisão da BSS (17/07/2026): o módulo é
  bugado no legado, não mostra nada, e ninguém deve usar. Morre na virada.
  No BSS o documento continua vivendo pendurado no processo, que é onde ele
  tem contexto — o checklist do `processo-detalhe` já cobre isso.
- **Empresas** e **Sindicatos** aparecem no portal da empresa. Faz sentido no
  N:N (um gestor com 11 CNPJs precisa da lista). ❓ Falta ver o que a tela de
  Sindicatos mostra pra empresa — no BSS ela hoje entrega `parametros_boleto`
  (tarifas, banco), que é dado comercial da BSS. Por isso está **bloqueada**
  pro perfil empresa (ver `sindicato_router.py`).

### Alerta de inadimplência ✅

Modal **bloqueante**, no login, quando existe empresa inadimplente ou irregular
sob gestão do usuário. Texto do legado, na íntegra:

> **ATENÇÃO!**
> Existe empresa INADIMPLENTE ou IRREGULAR com as contribuições registrada em
> seu acesso. Informamos que:
> 1. Não será emitido o certificado de regularidade para esta empresa;
> 2. Os Sindicatos possuem acesso a esta informação e podem tomar as medidas cabíveis.
> Entre em contato e regularize a situação: financeiro@bssindical.com.br /
> 0800 580 3816 opção 2, depois 5.

❓ **O que define "INADIMPLENTE" e "IRREGULAR"?** São coisas diferentes (a tela
de Empresas tem as duas como colunas separadas). Boleto vencido e não pago? Tem
carência de quantos dias? O texto é fixo ou parametrizado por sindicato?

Implementado em `dashboard-empresa.js` usando `adimplencia` e `regularidade` da
`v_empresa` — ou seja, **reportando o que o banco já calcula**, sem inventar
regra nova. Se a regra do legado for outra, é aqui que muda.

---

## 2. Abertura de benefício (`Adicionar`)

**Não existe no BSS.** `processo_router.py` tem 6 rotas e todas são `@router.get`.
Não há `POST /processos`, não há upload de anexo, não existe tela de benefício
novo. Hoje o benefício nasce no legado e o BSS espelha via `sync/processo.py` e
`sync/documento.py`.

O `renderChecklist()` do `processo-detalhe.js` já desenha o estado de cada
documento (`nao_enviado`/`pendente`/`aprovado`/`rejeitado`), o cadeado 🔒 e o
resumo "3 de 5 obrigatórios aprovados" — **é a metade de leitura deste fluxo**.
Falta a metade de escrita.

### 2.1 Fluxo da tela ✅

**Bloco 1 — Trabalhadores / Dependentes**

1. Campo inicial: **CPF do Trab./Dep.** + botão `Buscar`.
   Convenção do negócio: **busca por CPF, com ou sem pontos e traços**. Não
   existe busca por nome. O CPF valida se o trabalhador está cadastrado e com
   cobertura válida (boleto pago na competência correta).
2. Encontrado → carrega **somente leitura**: Nome, CPF, Empresa, Sindicato.
3. Campos editáveis, **obrigatórios pro benefício**: Gênero, Nascimento*,
   Nome da Mãe*, Admissão*.

> **A regra que explica esses 4 campos:** eles NÃO são obrigatórios pro
> trabalhador existir. A carga mensal sobe por planilha com basicamente CPF,
> nome e sindicato. Mas **para o benefício tornam-se obrigatórios**.
>
> E o mais importante: **gravam no cadastro do trabalhador e são reaproveitados
> no próximo benefício**. A planilha sobe o mínimo e o cadastro engorda conforme
> a empresa usa o portal. O formulário é o que completa a base.

❓ Existe regra de permissão de abertura de benefícios (quem pode abrir o quê).
Não aprofundada ainda — Mauro sinalizou que fica pra depois.

**Bloco 2 — Benefício**: Tipo de Benefício (dropdown) + Data de Evento*.
Trocar o tipo **muda os campos e os documentos**. Ver §2.2.

**Bloco 3 — Beneficiário**: pode ser diferente do trabalhador. Ver §2.2 — o
bloco varia por tipo, e num deles não existe.

**Bloco 4 — Documentos Obrigatórios**: um `input file` por tipo de documento,
com `*` nos obrigatórios.

### 2.2 O que muda por tipo ✅

Levantado das telas, um tipo por vez:

| Tipo | Campo próprio | Beneficiário | Dados bancários | Documentos (⭑ = obrigatório) |
|---|---|---|---|---|
| **NATALIDADE** | Quantidade de Bebês | completo | — | Certidão de Nascimento ⭑ · CTPS · Outros |
| **ACIDENTE** | — | completo | — | CAT (Comunicação de Acidente do Trabalho) ⭑ · Atestado assinado pelo médico ⭑ · CTPS · Outros |
| **INCAPACITAÇÃO** | — | completo | **sim** | Laudo médico INSS (carta de concessão) informando aposentadoria por invalidez ⭑ · Comprovante de endereço ⭑ · Comprovante bancário ⭑ · CTPS · Outros · Termo de responsabilidade incapacitação · Autorização de crédito incapacitação |
| **FALECIMENTO** | — | completo | **sim** | Certidão de Óbito ⭑ · Certidão de casamento ou de união estável ⭑ · Documento que comprove o vínculo do trabalhador falecido com o beneficiário ⭑ · Comprovante de Endereço ⭑ · Comprovante de Sepultamento ⭑ · Comprovante de conta bancária ⭑ · CTPS · Outros · Termo de Responsabilidade Falecimento · Autorização de crédito |
| **REEMBOLSO RESCISÃO** | — | **NÃO EXISTE** | **sim (conta da EMPRESA)** | TRCT Termo de Rescisão do Contrato de Trabalho Completo ⭑ · Comprovante de Depósito do Valor da Rescisão ⭑ · Outros |
| **AUXÍLIO CRECHE** | — | reduzido | — | **nenhum** ✅ confirmado pela BSS |
| **CONSULTA MÉDICA** | — | reduzido | — | **nenhum** |
| **EXAME** | — | reduzido | — | **nenhum** |
| **BRINDE SINDICATO** | — | reduzido | — | **nenhum** |
| **ACIONAMENTO FUNERAL** | ❓ | ❓ | ❓ | **sem obrigatórios** — a funerária abre sem documento e sobe depois |

### Conferência contra `bss.tipo_beneficio_documento` (migração 10) ✅

Cada tipo acima foi comparado, documento a documento, com o seed da migração 10:

| Tipo | Seed | Portal | Resultado |
|---|---|---|---|
| NATALIDADE | 3 docs, 1 obrigatório | idem | ✅ |
| FALECIMENTO | 10 docs, 6 obrigatórios | idem | ✅ |
| ACIDENTE | 4 docs, 2 obrigatórios | idem | ✅ |
| INCAPACITAÇÃO | 7 docs, 3 obrigatórios | idem | ✅ |
| REEMBOLSO RESCISÃO | 3 docs, 2 obrigatórios | idem | ✅ |
| CONSULTA MÉDICA · EXAME · BRINDE SINDICATO · AUXÍLIO CRECHE | sem regra | sem bloco de documentos | ✅ |
| ACIONAMENTO FUNERAL | 1 doc, **opcional** | ❓ tela não vista | — |

**Nomes, obrigatoriedade e ordem batem em 100% do que foi visto.** A migração
10 foi extraída deste mesmo formulário e continua fiel — não há nada a corrigir
no seed. `Outros` aparece com `ordem = 99` no seed e por último na tela: mesmo
efeito.

Isso também valida o desenho: **o formulário pode ser gerado a partir da
tabela**, sem `if` por tipo. Os documentos, pelo menos — os *campos* ainda não
têm tabela (ver §4).

**Três achados estruturais:**

1. **REEMBOLSO RESCISÃO não tem beneficiário.** É reembolso: o dinheiro volta
   pra empresa. O campo é "Tipo conta **empresa**", não "conta do beneficiário".
   É o único tipo assim, e quebra a suposição de que todo processo tem uma
   pessoa beneficiária.

2. **Dados bancários** só aparecem em INCAPACITAÇÃO, FALECIMENTO e REEMBOLSO
   RESCISÃO. Nos dois primeiros o rótulo diz **"Chave PIX (obrigatório ser CPF
   do beneficiário)"** — regra de validação explícita. No terceiro, a conta é
   da empresa. Campos: Código do Banco, Agência, Número da Conta, Dígito, Tipo
   de conta (CORRENTE/…), Detalhe da conta (INDIVIDUAL/…), Chave PIX.
   Encaixa em `bss.processo_dados_bancarios` (seção 13 do schema).

3. **"Beneficiário reduzido" — É BUG DO LEGADO. NÃO REPLICAR.** ✅ Confirmado
   pela BSS (17/07/2026).

   Nos tipos simples (CONSULTA MÉDICA, EXAME, BRINDE SINDICATO, AUXÍLIO CRECHE)
   a tela mostra **só** Nome da Mãe do Beneficiário ⭑, Nascimento ⭑ e Bairro ⭑
   — sem nome, sem CPF, sem CEP. São três campos `required` órfãos: o resto do
   bloco foi escondido pra esses tipos e os asteriscos ficaram para trás.

   O sintoma denuncia a causa: pedir a mãe do beneficiário sem pedir o nome
   dele, e exigir Bairro sem CEP nem cidade, não fecha em nenhuma leitura de
   negócio.

   ❓ **O que fica no lugar?** Duas saídas possíveis, e não dá pra deduzir:
   - **bloco completo** — se esses benefícios têm beneficiário de verdade
     (AUXÍLIO CRECHE, por exemplo: o beneficiário é a criança); ou
   - **nenhum bloco** — se o beneficiário É o próprio trabalhador (o mais
     provável pra CONSULTA MÉDICA, EXAME e BRINDE SINDICATO), como já acontece
     em REEMBOLSO RESCISÃO, que não tem beneficiário nenhum.

   Provavelmente a resposta é diferente por tipo — o que reforça a tabela
   `tipo_beneficio_campo` (§4) em vez de `if` no código.

**Beneficiário completo:** Nome, CPF, Telefone, Grau de parentesco (dropdown,
default "Pai / Mãe"), Nome da Mãe ⭑, Nascimento ⭑, CEP, Endereço (readonly),
número, Complemento, Bairro ⭑, Cidade (readonly), Estado (readonly).
CEP preenche Endereço/Cidade/Estado — mesmo padrão do autocadastro (ViaCEP via
`urllib`, sem dependência nova).

❓ **Divergência entre prints:** numa captura Nome/CPF/Telefone do beneficiário
apareceram com `*`; noutra, do mesmo tipo (NATALIDADE), sem. Não sei qual é o
estado real — confirmar.

### 2.3 Regra de gravação ✅

> **"Não é permitido salvar um benefício sem todos os obrigatórios."**

O `POST` é **atômico**: processo + documentos numa transação só. Não existe
criar o processo e anexar depois — ou entra inteiro, ou não entra. Isso evita
processo órfão se o upload falhar no meio.

A validação **já está codificada** e não precisa de `if` por tipo: "todo
documento com `obrigatorio = TRUE` em `bss.tipo_beneficio_documento` precisa de
arquivo". O **Acionamento Funeral** cai fora sozinho, porque a migração 10
gravou `obrigatorio = FALSE` nele de propósito.

---

## 3. Gaps concretos

### 3.1 Schema — faltam 3 colunas

| Campo do formulário | Onde deveria estar | Situação |
|---|---|---|
| Gênero do Trab./Dep. | `bss.trabalhador` | **não existe** |
| Nome da Mãe do Trab./Dep. | `bss.trabalhador` | **não existe** |
| Nome da Mãe do Beneficiário | `bss.processo_beneficio` | **não existe** |

Vão em `bss.trabalhador` (e não no processo) porque **gravam e são
reaproveitados** — é dado do trabalhador, não do benefício.

O resto encaixa: `qtd_bebes` (com o comentário "gêmeos, trigêmeos"),
`data_evento`, `data_obito`, `causa_mortis`, e o bloco `beneficiario_*` inteiro
com endereço.

### 3.2 Schema canônico está mentindo

`backend/scripts/01_schema_inicial.sql` — a fonte da verdade segundo as
instruções do projeto — ainda diz:

```sql
protocolo VARCHAR(9) UNIQUE,
-- protocolo = ID que o cliente vê (formato AAMMDD + 3 dígitos sequenciais por dia).
```

**Está errado, e é um erro que já foi corrigido em produção.** As migrações
13/14/15 mudaram pra `VARCHAR(20)` sem UNIQUE, com o número **copiado de
`cases.name`** — porque os protocolos antigos têm 14 dígitos, vieram de um
sistema PHP anterior, e não podem ser calculados. O comentário acima descreve
uma máscara que foi inventada e derrubada.

Drifts conhecidos entre o schema canônico e o banco real:

1. `protocolo` — tipo, UNIQUE e comentário (acima)
2. `uq_processo_protocolo` — existia no banco sem script correspondente
3. `empresa.cnpj NOT NULL` — adicionado direto no banco; **derrubou o cron
   noturno por semanas e escondeu 44.704 trabalhadores**

### 3.3 Storage dos arquivos — decisão pendente ❓

Os documentos sincronizados apontam pra `legado://document_revision/{id}` —
ponteiro, não arquivo. **Upload novo precisa de storage de verdade.** Disco da
OCI? Object Storage da Oracle? S3?

Não é decisão técnica minha: define custo, backup e LGPD. **Trava a
implementação do bloco 4 do formulário.**

---

## 4. Estimativa

| Item | Esforço | Situação |
|---|---|---|
| Migração das 3 colunas | ~30min | pronto pra fazer |
| Busca por CPF + carga dos dados | ~2h | endpoint novo |
| Campos dinâmicos por tipo | ~4h | `tipo_beneficio` sabe os documentos, **não sabe os campos** |
| CEP → endereço | ~1h | mesmo padrão do autocadastro |
| Upload + `POST` atômico | ~4h | **bloqueado pela decisão de storage** |
| **Total `Adicionar`** | **2–3 dias** | |

> **`bss.tipo_beneficio_documento` resolve os documentos, mas não os campos.**
> Não existe hoje nenhuma tabela dizendo "NATALIDADE tem qtd_bebes",
> "FALECIMENTO tem dados bancários", "REEMBOLSO RESCISÃO não tem beneficiário".
> Ou isso vira tabela (`tipo_beneficio_campo`), ou vira `if` no código. A
> primeira opção é coerente com o que já fizemos pros documentos — e o legado
> mostra que essas regras mudam.

---

## 5. Portal da Funerária — não é este portal

Registrado aqui porque saiu na mesma conversa, mas **é um terceiro portal**, não
uma variação do da empresa. ✅ Definição da BSS (17/07/2026):

> A funerária **não vê empresas, boletos, dashboard, trabalhadores — nada**.
> Acessa e vê **só os benefícios próprios**. Ao criar, **só aparece Acionamento
> Funeral**. O formulário é simples. ❓ Definição dos campos: pendente.

Por que isso não cabe no modelo atual:

1. **O perfil não existe.** Hoje são admin/interno/analista/empresa/sindicato/
   contabilidade. Falta `funeraria`.
2. **O escopo é de outra natureza.** Empresa filtra por `usuario_empresa`,
   sindicato por `usuario_sindicato`. A funerária não se prende a nenhum dos
   dois: ela **abre e acompanha benefícios de trabalhador de qualquer
   empresa/sindicato**, desde que tenha um Acionamento Funeral aberto. Muitas
   vezes ela sabe do falecimento antes da BSS — acessa o portal com o CPF do
   trabalhador e abre o processo pra ser reembolsada pelos serviços prestados.
3. **Falta a coluna que define "próprios".** O escopo é "processo que EU abri",
   e `bss.processo_beneficio` não tem `criado_por_id`. Sem isso não há como
   filtrar.
4. **Precisa de busca global por CPF**, sem escopo de empresa — o oposto do que
   o `trabalhador_router` faz hoje.

Ou seja: é uma **terceira dimensão de RLS**, mais coluna, mais perfil, mais
tela. Não é "o portal da empresa com menos itens no menu".

---

## 6. O que já foi feito (17/07/2026)

- ✅ `dashboard-empresa.html` — 3 listas **reais** (RLS já existia em
  `processo_router`, `boleto_router`, `trabalhador_router`) + modal de
  inadimplência. Só o `Adicionar` está desabilitado.
- ✅ `js/empresa-atual.js` — seletor de empresa. Antes, o backend caía em
  `usuario.empresas[0]` e o usuário via **1 das 11** empresas, sem saber qual.
- ✅ `sidebar.js` filtra por perfil — Contatos e Sindicatos somem pra empresa.
- ✅ Vazamentos fechados: `dashboard_router` (expunha o faturamento da BSS na
  primeira tela pós-login), `sindicato_router` (parâmetros comerciais),
  `/trabalhadores/dependentes/{cpf}` (dependentes de qualquer CPF — o dado mais
  sensível que temos).
- ✅ `empresa_repo.listar(ids=...)` — filtro em SQL. Antes filtrava **depois**
  de paginar: usuário com 11 empresas via "1 empresas encontradas / Página 1 de
  105".

**Não feito:** `Adicionar` benefício, Sindicatos pra empresa, `Adicionar
Trab./Dep.` individual (só o upload em massa existe).

**Fora de escopo por decisão:** módulo Documentos (§1).
