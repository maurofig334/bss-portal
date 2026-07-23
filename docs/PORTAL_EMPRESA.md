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

3. **O QUE É UM BENEFICIÁRIO** ✅ Definição da BSS (17/07/2026):

   > "Beneficiário é quem recebe uma indenização e que **não seja o próprio
   > trabalhador**. Por exemplo, quando o evento é um acidente grave, o
   > trabalhador pode estar incapacitado para receber o dinheiro. No caso de
   > falecimento é óbvio que o dinheiro vai para a viúva ou o filho. Ou seja,
   > beneficiário é alguém que recebe o benefício **no lugar** do trabalhador."

   Isso explica os três formatos do bloco: **completo** onde pode haver outra
   pessoa, **inexistente** no REEMBOLSO RESCISÃO, e o "reduzido" sendo lixo de
   formulário nos tipos em que quem recebe é o próprio trabalhador.

   **Casos já confirmados pela BSS:**

   | Tipo | Beneficiário | Porquê |
   |---|---|---|
   | REEMBOLSO RESCISÃO | **não existe** | "o trabalhador é demitido, ele mesmo receberá a indenização" — está vivo e capaz |
   | CONSULTA MÉDICA | **não existe** | "significa que o trabalhador está ativo, ele mesmo é o beneficiário" |
   | EXAME | **não existe** | idem |
   | FALECIMENTO | sempre | "é óbvio que o dinheiro vai para a viúva ou o filho" |
   | ACIDENTE / INCAPACITAÇÃO | pode haver | o trabalhador pode estar incapacitado para receber |
   | BRINDE SINDICATO | ❓ | provavelmente igual a consulta/exame — confirmar |
   | AUXÍLIO CRECHE | ❓ | o beneficiado é a criança, mas quem RECEBE é o pai/mãe trabalhador — confirmar |
   | NATALIDADE | ❓ | os dados mostram os dois casos (ver abaixo) |

   O teste é sempre o mesmo: **o trabalhador pode receber o dinheiro?** Se sim,
   não há beneficiário. Não é sobre quem o benefício ajuda — é sobre quem
   assina o recibo.

   **Três destinatários possíveis**, e o schema já previu dois deles em
   `bss.dados_bancarios.titular_tipo` ('empresa' | 'beneficiario'):

   | Recebe | Tipos |
   |---|---|
   | o trabalhador | consulta médica, exame, brinde |
   | um beneficiário | falecimento, acidente, incapacitação |
   | a **empresa** | reembolso rescisão — ✅ confirmado: "o reembolso é para a empresa" |

   ⚠️ **TEORIA DESCARTADA — não remontar.** Reparei que NATALIDADE e ACIDENTE
   têm bloco Beneficiário com endereço completo mas NENHUM dado bancário, e
   deduzi que o endereço servia pra enviar o cartão (`codigo_rastreio_cartao`
   está comentado como "código dos correios pra entrega"). **Está errado.**
   Correção da BSS: em quase todos os sindicatos o pagamento é por cartão de
   benefícios, e **o plástico é emitido e enviado para a SEDE DO SINDICATO** —
   é o sindicato que entrega o cartão físico ao trabalhador. O endereço do
   beneficiário não é logística.

   ❓ Fica em aberto pra que serve o endereço no bloco Beneficiário.

   **Pagamentos são capítulo futuro** — ainda não encostamos. Não desenhar o
   formulário assumindo forma de pagamento. O pouco que já foi dito pela BSS,
   pra não se perder:

   - **Regra geral:** em quase todos os sindicatos o pagamento é por **cartão
     de benefícios**. O plástico é emitido e enviado à **sede do sindicato**,
     que entrega em mãos ao trabalhador.
   - **FALECIMENTO é a exceção:** pago **em parcelas**, **depositadas na conta
     do beneficiário**. Explica por que é o único tipo com beneficiário
     obrigatório *e* dados bancários — e por que o rótulo do PIX diz
     "obrigatório ser CPF do beneficiário".
   - **As parcelas viram contas a pagar, que depois são liquidadas.** Ou seja,
     `bss.pagamento` **é** o contas a pagar — o próprio schema entrega a
     ligação: `numero_pagamento BIGINT, -- = id_cpagar_c (sequencial)`.
     *cpagar* = contas a pagar do legado. Liquidar = `status` virar `'pago'`
     com `data_pagamento` preenchida.
   - O schema já suporta: `processo_beneficio.qtd_parcelas`, `bss.pagamento`
     com `parcela`/`data_prevista`/`data_vencimento`/`data_pagamento`/`status`,
     e `bss.dados_bancarios.titular_tipo`. O comentário de
     `pagamento.beneficiario_nome` inclusive avisa que "beneficiário pode mudar
     entre parcelas (ex: pensão alimentícia)".
   - Consequência pro backlog: o **"módulo de contas a pagar"** do épico #22
     não é módulo novo. É a tela que falta pra uma tabela que já existe, já
     está sincronizada, e já tem endpoint (`processo_repo.listar_pagamentos`).

   ❓ **Mas a regra pode não ser por tipo.** Na tela do analista, dois processos
   de NATALIDADE aparecem lado a lado: num, "Nome do Trab." e "Nome
   Beneficiário" são a MESMA pessoa (ELIS AGUIAR DO NASCIMENTO); no outro, são
   DIFERENTES (PAULO GOMES DA SILVA AGUIAR → DENISE GOMES DE AGUIAR SILVA).
   Se o mesmo tipo tem os dois casos, o bloco é **condicional ao caso**, não ao
   tipo — e o formulário deveria perguntar ("outra pessoa vai receber?") em vez
   de decidir sozinho pelo tipo escolhido.

   Os 19 mil processos do legado já têm a resposta gravada. Rodar
   `scripts/analisar_beneficiario.py`: ele compara `beneficiario_cpf` com o CPF
   do trabalhador em cada tipo e classifica em SEM bloco / bloco OBRIGATÓRIO /
   bloco OPCIONAL. Decidir depois disso, não antes.

3b. **"Beneficiário reduzido" — É BUG DO LEGADO. NÃO REPLICAR.** ✅ Confirmado
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

## 5b. Mensageria nos benefícios ✅ (22/07/2026)

Canal empresa ↔ analista dentro de cada benefício. Metade já existia (tabela,
sync de 37.630 mensagens, aba de leitura); construído agora o que faltava:

- **Escrita** — `POST /processos/{id}/mensagens`. Chat livre (só corpo; a
  coluna `titulo` continua nas migradas, mas as novas nascem sem).
- **Autor resolvido** — JOIN com bss_users traz nome/perfil e deriva
  `eh_externo`. Balões: "meu lado" à direita, selo Cliente/BSS.
- **Nota interna** — só a equipe marca; empresa/sindicato/contabilidade não
  veem. **Corrigido um vazamento no caminho:** o GET usava lista negra
  (`!= "empresa"`), então sindicato e contabilidade liam as notas internas.
  Agora é lista branca (`in PERFIS_INTERNOS`).
- **Mudança de status ao responder** — decisão da BSS ("analista escolhe ao
  responder"). Grava em `processo_andamento` com a mensagem como comentário,
  então o audit trail explica POR QUE o status mudou.
- **Dois sinos, duas perguntas:**
  - analista → "cliente falou por último?" (derivado; apaga ao responder)
  - cliente → "tem mensagem que eu não li?" (precisa marca d'água —
    `bss.processo_mensagem_leitura`, migração 20 — porque o cliente lê e não
    responde, e "a última é da BSS" ficaria aceso pra sempre)
- **E-mail** — quando a BSS responde, aviso imediato aos contatos da empresa
  (BCC), **só protocolo + link, sem o texto** (LGPD: benefício lida com óbito,
  acidente, incapacitação — não trafega por e-mail). Respeita
  `preferencias_notificacao->'beneficio'` e pula `@contato.invalid`. Em
  BackgroundTask: o SMTP não segura a resposta. Nota interna NÃO notifica.

**Pendência do e-mail:** roda com SMTP provisório e `SMTP_VERIFICAR_CERT=false`
— o certificado de `smtp.nexuserp.com.br` não casa com o hostname (erro que só
apareceu porque o Python confere e outros projetos não conferiam). Antes de
produção: usar hostname com certificado válido (ver
`scripts/diagnosticar_smtp.py`) e religar a verificação.

---

## 6. O portal legado mostra trabalhadores que não existem

Descoberto em 17/07/2026 auditando o login `maurofig334@gmail.com`, e
**verificado por Mauro direto no SuiteCRM**:

| RCOND GESTAO E TECNOLOGIA LTDA | trabalhadores ativos |
|---|---|
| portal legado | **22** |
| SuiteCRM (a verdade) | **0** |
| BSS, contando de verdade | **0** |

Não é caso isolado: no login de teste, **6 das 11 empresas** divergiam. A
5 ESTRELAS exibia **476** trabalhadores ativos e não tinha **nenhuma** linha.
Somando as 11: o campo dizia 1.447, a realidade era 908.

**Causa provável (hipótese de Mauro, que conhece o SuiteCRM):** é um *campo
calculado* — recurso do SuiteCRM que totaliza via workflow. Ou ele roda no fim
do dia e não pegou as inativações, ou o workflow travou em algum momento e o
número congelou.

**O BSS não errou: ele copiou.** A sync trouxe `qtd_trabalhadores_ativos` fiel
ao legado, e a tela de Empresas passou a exibir o mesmo número fantasma —
enquanto a tela de Trabalhadores, que filtra por `id_empresa_atual` de verdade,
mostrava vazio. Dois números, duas fontes, um sistema.

**Reviravolta durante a própria auditoria:** entre duas execuções do script, o
campo foi recalculado e passou a bater com a realidade (1.447 → 908).

✅ **Mistério resolvido (22/07/2026): o "job" é nosso.** É
`scripts/reconciliar_qtd_trabalhadores.py`, escrito numa sessão anterior, que
recalcula os caches a partir de `bss.trabalhador`. Alguém o rodou. Nunca houve
processo desconhecido — estava no repositório.

### ⚠️ CABO DE GUERRA — bug em aberto

Duas coisas escrevem no MESMO campo, com valores DIFERENTES:

| Quem | O que grava |
|---|---|
| `sync/empresa.py` | copia `accounts_cstm.trabalhadores_ativos_c` do legado (`ON CONFLICT … = EXCLUDED`) |
| `reconciliar_qtd_trabalhadores.py` | recontagem real de `bss.trabalhador` |

**Quem rodou por último ganha.** O valor do campo depende da ordem de execução,
não da realidade. A auditoria de 22/07 mediu 99,6% de concordância — mas só
porque o reconciliar tinha rodado depois da sync. **A próxima sync traz o
número errado de volta.**

Correção pendente (independe do cliente): decidir quem manda. Ou a sync para de
copiar esse campo (e ele passa a ser sempre nosso, recontado), ou a coluna vira
espelho explícito do legado e a tela deixa de usá-la. Ver
`scripts/medir_contagem_trabalhadores.py` — o índice parcial
`idx_trab_emp_sind` já existe pra contar na hora.

**Efeito colateral já ocorrido:** o RCOND mostrava 22 (valor do legado) e agora
mostra 0 (nossa recontagem). **A evidência do bug do legado foi sobrescrita no
nosso banco** — pra levar números à BSS, buscar direto no MySQL (temos leitura).

### Auditoria com o cliente — decidido em 22/07/2026

Mauro: *"vamos deixar esta auditoria pra fazer junto com o cliente, eles vão
saber por que existem trabalhadores sem empresa e vão nos dar uma posição
definitiva do que manter ou ignorar."*

Dados medidos em 22/07 pra levar à reunião:

- **25.694 trabalhadores sem `id_empresa_atual`** (3,7% de 689.795) — ❓ causa
  desconhecida: nunca tiveram empresa no legado, ou a sync não vinculou?
- 689.795 trabalhadores no total · 343.679 ativos · 346.116 não-ativos
- 19 empresas com cache MENOR que a realidade (soma −153) — resíduo do cabo de
  guerra acima
- ⚠️ A tabela "15 MAIORES DIVERGÊNCIAS" do `auditar_cache_trabalhadores.py`
  saiu **enganosa**: todas as linhas mostram `cache == real`, porque não havia
  divergência positiva e o `ORDER BY` devolveu linhas arbitrárias. Deveria ter
  vindo vazia — corrigir antes de mostrar a alguém.

### A lição de arquitetura

Cache ou campo calculado, é a mesma classe: **número derivado, gravado, que
descola da fonte**. A correção não é ter um job melhor — é não precisar de job.

`bss.trabalhador` já tem o índice exato pra contar na hora:

```sql
CREATE INDEX idx_trab_emp_sind ON bss.trabalhador (id_empresa_atual, id_sindicato_atual)
  WHERE situacao = 'ativo';
```

Índice **parcial**, filtrado em `situacao='ativo'` — feito pra esta pergunta.
É o mesmo raciocínio que o schema já usou pra recusar a tabela física de
empresa×sindicato ("no Postgres com índices certeiros, calcular on-the-fly
roda em milissegundos").

**Proposta:** `v_empresa` conta na hora; a coluna vira só espelho do legado
pra reconciliação. Medir antes com `scripts/medir_contagem_trabalhadores.py`
(cronometra as duas formas e mostra o EXPLAIN) — se o plano usar o índice
parcial e ficar abaixo de 100ms por página, o cache não se justifica.

### Ferramentas

- `scripts/auditar_cache_trabalhadores.py` — cache × realidade na base inteira,
  15 maiores divergências, e o contador de `id_empresa_atual IS NULL` (que
  separa "cache do legado errado" de "nossa sync não vinculou").
- `scripts/inspecionar_escopo_empresa.py` — por usuário: o que cada empresa
  vinculada tem, e o que os repos devolvem quando chamados como o router chama.

---

## 7. O que já foi feito (17/07/2026)

- ✅ `dashboard-empresa.html` — 3 listas **reais** (RLS já existia em
  `processo_router`, `boleto_router`, `trabalhador_router`) + modal de
  inadimplência. Só o `Adicionar` está desabilitado.
- ✅ **`empresas[0]` morto.** Descoberta central do dia: **não existe "empresa
  atual"** — o portal legado lista as 11 empresas juntas, e as listas de
  Boletos e Benefícios têm coluna "Empresa" justamente porque misturam. Os
  routers agora separam **ESCOPO** (`ids_empresa`, do JWT, sempre aplicado) de
  **FILTRO** (`id_empresa`, da tela, opcional). O filtro estreita dentro do
  escopo, nunca alarga. `js/empresa-atual.js` virou filtro com "Todas" por
  padrão — antes era uma prisão que escondia 10 empresas em silêncio.
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
