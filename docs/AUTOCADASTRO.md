# Autocadastro de Empresas e Usuários

> **Status:** desenho para implementação no BSS.
> **Levantado em:** 01/07/2026, a partir da tela em produção
> (`portal.beneficiosocialsindical.com.br/cadastro/`) + confirmações do Mauro.
>
> ⚠️ **Este documento substitui a documentação da época da virada PHP→SuiteCRM.**
> Aquela era uma carta de intenções; boa parte nunca foi implementada. As
> divergências estão listadas no fim — leia antes de usar a doc antiga como spec.

## Por que existe

Quando a BSS adota um **novo sindicato**, as empresas daquela base precisam
entrar na plataforma. Não dá pra cadastrar tudo internamente: são os próprios
administradores das empresas que fazem o cadastro — criando a empresa e o seu
usuário (o "contato", na linguagem do legado).

O autocadastro é, portanto, a **porta de entrada dos usuários externos** — os
mesmos que depois fazem upload da planilha mensal, abrem benefícios e
conversam com o analista.

## O modelo em uma frase

> Um CNPJ tem N gestores. Um gestor administra N CNPJs.

Um gerente de RH costuma administrar 4 ou 5 CNPJs do mesmo grupo. É um N:N
puro, e o cadastro é essencialmente uma frase: **"me dê acesso a este CNPJ"**.

## Fluxo real (as-is)

O formulário é **progressivo**: começa só com o CNPJ e revela o resto conforme
valida. A checagem do CNPJ roda ao sair do campo (`blur`), antes de qualquer
envio.

```
CNPJ digitado
 │
 ├── EXISTE na base do BSS
 │     alerta: "Este CNPJ já existe. Prossiga para cadastrar novo
 │              usuário para administrar este CNPJ!"
 │     → revela: Nome Completo, Telefone, Senha, Repetir Senha
 │     → cria Contato + vínculo com a Empresa
 │
 └── NÃO existe
       → consulta automática à RFB
       → exibe os dados principais, SEM permitir edição
         (a Receita é a fonte da verdade; o usuário não corrige)
       → revela o campo de e-mail
             ├── e-mail corresponde a um Contato existente
             │     → grava a nova Empresa vinculada ao Contato que já existe
             │       (não repede nome/senha — ele já tem)
             └── e-mail novo
                   → cadastra Empresa + Contato
 │
 ├──> 🔒 TODO CONTATO NOVO é aprovado por um ANALISTA INTERNO
 │      (regra confirmada com o Mauro — vale nos dois ramos, sem exceção)
 │
 └──> após gravar, vai para a tela de login
```

### A aprovação é universal

**Todo contato novo passa por um analista interno** — não importa se o CNPJ já
existia ou se veio da RFB. Não há caminho que conceda acesso sem alguém olhar.

Isso responde a dúvida de segurança que o desenho levantava: o termo de
responsabilidade civil e criminal **não é o único controle**. Ele é o
complemento jurídico de um controle humano que existe de fato.

Consequência prática: o usuário é mandado pra tela de login logo após gravar,
mas **o acesso só funciona depois da aprovação**. A tela de login precisa
tratar esse estado com uma mensagem clara ("cadastro em análise"), senão o
sujeito vai achar que errou a senha.

### Campos coletados

| Campo | Quando aparece | Observação |
|---|---|---|
| CNPJ | sempre | valida no blur; decide o ramo do fluxo |
| E-mail | sempre | **é o login** |
| Nome Completo | ramo "CNPJ existe" / contato novo | digitado, não vem de fonte externa |
| Telefone | idem | |
| Senha + Repetir | idem | **o usuário escolhe a própria senha** |
| Aceite do termo | sempre | checkbox obrigatório (texto abaixo) |

### O termo

> "Ao prosseguir com este cadastro, estou ciente da minha responsabilidade civil
> e criminal quanto à exatidão dos dados e quanto à segurança dos dados que irei
> incluir, considerando ser a principal finalidade o atendimento ao preconizado
> pela CCT - Convenção Coletiva de Trabalho, no tocante às contribuições mensais
> das empresas e a concessão de benefícios de CCT aos seus trabalhadores"

### A assimetria de risco (e por que ela é acertada)

Os dois ramos têm tratamentos diferentes, e o motivo é bom:

- **Empresa existente** → alguém está reivindicando acesso a dados que já estão
  lá (trabalhadores, CPFs, boletos, benefícios). É o caso arriscado: pode ser
  impostor. Por isso **a OP aprova**.
- **Empresa nova** → a Receita validou os dados e o cadastrante é naturalmente
  quem está trazendo o cliente. Risco baixo.

## Modelo de dados no BSS

### O que JÁ existe e serve (sem migration)

O schema antecipou este cenário. O comentário em `bss_users.perfil` diz, textualmente:
`'empresa' = cliente — opera N empresas via bss.usuario_empresa`.

| Campo do formulário | Destino no BSS |
|---|---|
| E-mail (login) | `bss_users.email` (UNIQUE) |
| Nome Completo | `bss_users.nome` |
| Telefone | `bss_users.telefone` |
| Senha | `bss_users.senha_hash` |
| — | `bss_users.perfil = 'empresa'` |
| CNPJ administrado | `bss.usuario_empresa` (id_usuario × id_empresa) |
| Pendente de aprovação | `bss_users.ativo` / `usuario_empresa.ativo` = `false` |

**O lado do usuário não precisa de coluna nova.** O "Contato" do legado é o
`bss_users` com perfil `empresa` — não é entidade separada.

### O que FALTA

**1. `bss.empresa` não tem e-mail.** Nenhum. E o autocadastro é movido a e-mail.
Faltam também os campos que só existem quando a empresa nasce de um cadastro
(e não do sync do legado):

| Campo | Para quê |
|---|---|
| `email` | contato da empresa (o da RFB) |
| `email_cobranca` | previsto na doc antiga; confirmar se ainda vale |
| `tipo_cadastro` | `'auto'` vs `'interno'` — o legado distingue |
| `situacao_cadastral` + `data_situacao_cadastral` | vêm da RFB |
| `cnae` / atividades econômicas | a doc previa reprovar CNAE não atendido |
| `status_cadastro` | pendente / aprovado / reprovado. **Não confundir com `status`** (ativa/suspensa/cancelada), que é outra dimensão |

**2. Registro do aceite do termo.** Hoje não existe em lugar nenhum. Um termo de
responsabilidade civil e criminal que não guarda **quem aceitou, quando, de qual
IP e qual versão do texto** tem valor jurídico frágil. É barato fazer certo agora.

**3. Auditoria da aprovação.** `ativo` guarda o *estado*, mas não **quem aprovou,
quando, e se foi reprovado ou só ainda não olharam**. Sugestão: tabela de
solicitação de acesso, com `usuario_empresa` sendo o *resultado* dela.

## Tela de Contatos (não existe ainda)

O BSS tem tela pra Empresas, Trabalhadores, Sindicatos, Benefícios e Boletos.
**Contato é a única entidade do modelo sem tela** — e é exatamente a que o
autocadastro cria. Sem ela, a operação não tem onde ver, buscar ou gerenciar os
usuários externos.

Precisa de:

- **Listagem** no padrão OCSP (mesmo grid reutilizável de Trabalhadores):
  nome, e-mail, telefone, quantos CNPJs administra, situação (ativo /
  pendente / reprovado), data do cadastro, tipo (auto x interno).
  Filtro por situação é o mais usado — a fila de pendentes sai daqui.
- **Detalhe** no padrão OCSP (cabeçalho + abas inferiores):
  - cabeçalho: dados **do próprio contato** — nome, e-mail/login, telefone,
    tipo de contato, origem do cadastro, autorização, bloqueio, preferências,
    aceite do termo (quando, versão, IP)
  - aba **Empresas**: os CNPJs que ele administra, com a data de cada vínculo
    e quem aprovou — é o coração do N:N
  - aba **Histórico**: solicitações, aprovações, reprovações

> **Empresas fica em aba, nunca no cabeçalho.** O legado erra nisso: exibe
> *"Nome da Empresa: SEVERAL WAYS SERVIÇOS TERCEIRIZADOS LTDA."* como campo
> único do cabeçalho — sugerindo um 1:1 que não existe. Os dados mostram
> contato administrando **54 empresas**: a tela mostra 1 e esconde 53. Quem
> abre aquele registro não faz ideia do alcance real daquele acesso — o que é
> grave justamente numa tela onde alguém decide se aprova ou não.
>
> Cabeçalho é para o que o registro **é**; aba é para o que ele **se relaciona**.
- **Ações**: aprovar / reprovar, ativar / desativar, e (a definir) desvincular
  de um CNPJ específico sem apagar o contato.

Ligações com o que já existe: o detalhe da **Empresa** tem a aba "Usuários com
acesso", hoje em **mockup** — ela passa a consumir esse mesmo modelo, fechando
o ciclo dos dois lados.

## Idempotência — não repetir o bug do portal legado

O portal atual **cria um contato por clique**. Evidência real, encontrada na
migração (`scripts/inspecionar_email_duplicado.py`):

```
RENATA CRISTINA TAMANAHA GARCIA   12/03/2025 19:50:46
RENATA CRISTINA TAMANAHA GARCIA   12/03/2025 19:51:30   ← 44s depois
RENATA CRISTINA TAMANAHA GARCIA   12/03/2025 19:51:40   ← 10s depois
Ana Paula Brito                   13/03/2025 10:59:38
Ana Paula Brito                   13/03/2025 11:01:06   ← 88s depois
```

Três cadastros em 54 segundos, mesmo login, mesma empresa. A pessoa clica em
"Finalizar", nada parece acontecer, clica de novo. Resultado: **94 e-mails
duplicados na base**, e ninguém sabe qual registro é o bom.

O autocadastro do BSS precisa de:

- **Botão desabilitado no submit** (o mínimo, e o legado nem isso tem)
- **Idempotência no backend**: mesmo (CNPJ, e-mail) chegando duas vezes em
  segundos → uma solicitação só
- ✅ **Já resolvido no schema**: `uq_solic_pendente_por_par` na migration 17
  (`UNIQUE (id_usuario, id_empresa) WHERE status = 'pendente'`) impede dois
  pedidos pendentes do mesmo par. Metade do problema já está travada no banco.

## Fila de aprovação (lado interno)

Como toda aprovação é humana, a fila **precisa ser vista** — senão o cadastro
morre esperando e o cliente liga reclamando que não consegue entrar.

**Requisito (Mauro):** um **sininho 🔔** alertando que há contatos novos
aguardando aprovação.

Componentes:

- **Indicador** no cabeçalho/sidebar com a contagem de contatos pendentes,
  visível pros perfis `analista`, `interno` e `admin`. Já existe precedente
  visual no projeto: a listagem de Benefícios usa 🔔 pra marcar processo com
  interação do cliente sem resposta.
- **Tela da fila**: quem pediu (nome, e-mail, telefone), qual CNPJ, quando,
  se é contato novo ou já existente pedindo mais um CNPJ, e o aceite do termo.
  Ações: aprovar / reprovar (com motivo).
- **Contexto pra decidir**: o analista precisa de elementos pra julgar se
  aquele e-mail deve mesmo administrar aquele CNPJ. Mostrar quem já é gestor
  do CNPJ ajuda: se a empresa já tem gestores, o natural é confirmar com eles.
  E mostrar **quantos CNPJs o solicitante já administra** — alguém pedindo o
  55º acesso é um caso bem diferente de quem está pedindo o primeiro.

> **Ponto que vale levar pra BSS:** o analista consegue julgar, sozinho, se
> `fulano@gmail.com` deve administrar o CNPJ de uma empresa que ele não conhece?
> A notificação ao e-mail da RFB (que a doc antiga previa e sumiu) resolveria
> isso sem depender de julgamento — a empresa fica sabendo, num endereço que o
> impostor não controla.

## Os três grupos de portal — e por que só migramos um

O legado tem três grupos externos (campo **Portal User Group**, que controla a
visibilidade dos módulos): **Empresas, Funerárias e Sindicatos**. O BSS tem
perfis `empresa` e `sindicato` — **falta `funeraria`**.

Mas não é só o perfil que falta: **falta o modelo de escopo**. Os três acessam
por lógicas diferentes:

| Perfil | Escopo do acesso | Como o BSS resolve |
|---|---|---|
| `empresa` | lista de CNPJs que administra | `bss.usuario_empresa` (N:N) ✅ |
| `sindicato` | lista de sindicatos | `bss.usuario_sindicato` (N:N) ✅ |
| **`funeraria`** | **processos de Acionamento Funeral, em qualquer CNPJ** | ❌ não existe |

### A funerária não é cliente — é prestador buscando reembolso

Confirmado com o Mauro (01/07/2026), e o fluxo explica tudo:

1. A funerária **sabe do falecimento antes da BSS**
2. Entra no portal e busca o trabalhador **pelo CPF** — não por empresa
3. Abre o **Acionamento Funeral** pra ser reembolsada pelo serviço já prestado
4. Acompanha **os processos que ela abriu**

Ou seja: ela **não administra empresa nenhuma**. O escopo dela é *"meus
processos"* — em trabalhador de qualquer empresa e qualquer sindicato.

Isso amarra com a regra de documentos: o **Acionamento Funeral** é o único tipo
que pode ser aberto **sem documentação**, com upload posterior
(`10_tipo_beneficio_documento_seed.sql`). O motivo é óbvio agora — quando a
funerária abre o benefício, o serviço já aconteceu e o papel ainda não existe.
O tipo de usuário e a regra de documento sempre foram a mesma coisa.

### O que falta no BSS pra suportar funerária

Não é "só adicionar o perfil". Faltam três coisas, e nenhuma é o perfil:

| Falta | Por quê |
|---|---|
| `processo_beneficio.criado_por_id` | Sem saber **quem abriu**, "meus processos" é inexprimível. A tabela tem `criado_em` mas não `criado_por`. O legado tem `cases.created_by` — nosso sync nem traz |
| Busca de trabalhador **por CPF, global** | Ela precisa achar qualquer trabalhador sem ter vínculo com a empresa dele. Nenhum perfil externo faz isso hoje — `empresa` e `sindicato` são escopados por lista |
| **RLS por processo** no `auth.py` | Hoje só existem `empresas: list[int]` e `sindicatos: list[int]`. Falta a terceira dimensão |

**Nota de segurança:** a busca global por CPF é uma capacidade ampla. O controle
é *saber o CPF* — fraco isoladamente, mas razoável pra quem já está com a
certidão de óbito na mão. Vale decidir conscientemente: a funerária pode
consultar qualquer CPF, ou só confirmar um que ela já digitou (sem listar,
sem navegar)?

## Integração com a RFB

É a **primeira integração externa do projeto**. Decisões em aberto:

- **Qual provedor?** BrasilAPI (grátis, sem contrato), ReceitaWS (freemium),
  Serpro (oficial, pago). O legado já consulta alguém — descobrir quem antes de
  escolher.
- **E quando a Receita cai?** O cadastro trava, ou grava o CNPJ e completa depois?
- **Reconsulta:** situação cadastral muda (empresa é baixada, suspensa). Uma vez
  no cadastro e nunca mais, ou revalidação periódica?

## Divergências da documentação antiga

A doc da virada PHP→SuiteCRM descreve um sistema bem mais ambicioso do que o que
existe. Registrado aqui pra ninguém tratá-la como spec:

| A doc previa | A realidade |
|---|---|
| Cadastro do usuário por **CPF**, com nome/nascimento vindos da RFB | Não pede CPF. Nome é digitado |
| "Enviar login e senha cadastrados ao e-mail do usuário" | O usuário escolhe a própria senha |
| "Validar o cadastro com link enviado ao e-mail" | Não existe — após gravar, vai direto pro login |
| "Reportar o cadastro para o e-mail cadastrado na RFB" | Não existe |
| Estado de acesso via IP; Sindicato Majoritário; e-mail de cobrança; CNAE reprovando cadastro | Nenhum aparece na tela |

### Duas que vale reconsiderar

**A notificação ao e-mail da RFB.** Era o contrapeso do risco: a empresa **fica
sabendo** que alguém reivindicou acesso a ela, num e-mail que o impostor não
controla. Com a aprovação da OP no meio, o risco cai — mas a OP consegue julgar
se um e-mail pessoal qualquer deve mesmo administrar o CNPJ de uma empresa que
ela não conhece? A notificação resolve isso sem depender de julgamento.

**"Sindicato Majoritário".** Não existe no BSS, e é conceitualmente diferente do
que temos: `bss.empresa_sindicato_ativo` é uma **view derivada dos trabalhadores**
(a empresa "tem" os sindicatos que seus trabalhadores têm). O autocadastro
precisaria do contrário — a empresa **declara** seu sindicato no cadastro, antes
de existir qualquer trabalhador. É dado de entrada, não de saída. Se entrar no
escopo, é campo novo, não view.

## Questões em aberto

1. ~~O usuário loga antes da aprovação?~~ **Resolvido:** todo contato novo é
   aprovado por analista interno. O login existe, mas o acesso só vale depois.
   Falta definir a **mensagem** que a tela de login mostra nesse estado.
2. ~~Empresa nova também passa por aprovação?~~ **Resolvido:** sim, a regra é
   universal — vale nos dois ramos.
3. Qual provedor de RFB o legado usa hoje? (decide o nosso)
4. `email_cobranca` e CNAE ainda fazem parte do escopo, ou morreram com a doc?
5. O termo tem versionamento? Se o texto mudar, os aceites antigos valem?
6. Reprovação: o cadastrante é avisado? Com motivo? Pode tentar de novo?
7. Existe SLA pra fila? (o sininho avisa que há pendência, mas não que ela está
   velha — vale destacar as que passaram de X dias?)
