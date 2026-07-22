# Modelos de E-mail em massa

Textos institucionais que a BSS dispara em lote: inadimplência, irregularidade,
lembrete de boleto, etc. Editáveis em **Modelos de E-mail** (menu, só equipe
interna). O corpo usa variáveis `{{nome}}` que o sistema preenche por
empresa/contato na hora do envio.

> **Fase atual:** criar, ajustar e pré-visualizar os textos. O **disparo em
> massa e o cronograma** são fase seguinte — dependem do conteúdo final e do
> calendário que a BSS vai passar.

---

## Variáveis disponíveis

Nomes limpos, no lugar dos `$contact_..._c` do SuiteCRM. Cada variável só vale
em certo **destinatário** — um modelo que vai pro e-mail da empresa não conhece
o nome do contato gestor.

### Escopo CONTATO (modelos "Contatos - …")

| Variável | O que vira |
|---|---|
| `{{contato_nome}}` | Nome da pessoa que administra os CNPJs |
| `{{contato_email}}` | E-mail do contato |
| `{{contato_telefone}}` | Telefone do contato |
| `{{lista_empresas_inadimplentes}}` | Tabela das empresas dele que estão inadimplentes |
| `{{lista_empresas_irregulares}}` | Tabela das empresas dele que estão irregulares |

### Escopo EMPRESA (modelos "Empresas - …")

| Variável | O que vira |
|---|---|
| `{{empresa}}` | Razão social |
| `{{cnpj}}` | CNPJ formatado |
| `{{empresa_cidade}}` | Cidade |
| `{{empresa_uf}}` | UF |

### Valem nos dois

| Variável | O que vira |
|---|---|
| `{{lista_boletos_vencidos}}` | Tabela Empresa \| CNPJ \| Número \| Vencimento \| Valor. Num modelo de contato, lista os vencidos de **todas** as empresas dele; num de empresa, só os daquela. |
| `{{bss_telefone}}` | `0800 580 3816, opção 2, depois 5` |
| `{{bss_email}}` | `financeiro@bssindical.com.br` |
| `{{data_hoje}}` | Data do envio (dd/mm/aaaa) |

As de **lista** (marcadas com ▤ na paleta) expandem numa tabela inteira, então
ficam numa linha sozinha no texto, não no meio de uma frase.

---

## De-para: nomes do legado → nomes novos

Para adaptar os modelos que a BSS já tem no SuiteCRM. Troque o da esquerda pelo
da direita ao colar o texto:

| Legado (SuiteCRM) | Novo | Observação |
|---|---|---|
| `$contact_name` | `{{contato_nome}}` | |
| `$contact_empresa_inadimplente_c` | `{{lista_empresas_inadimplentes}}` | O legado tinha um campo por empresa; o novo lista todas de uma vez |
| `$contact_cnpj_inadimplente_c` | *(idem — já vem na tabela acima)* | CNPJ agora faz parte da lista, não é campo solto |
| `$contact_lista_boletos_vencidos_c` | `{{lista_boletos_vencidos}}` | Mesma tabela Empresa\|CNPJ\|Número\|Vencto\|Valor |
| *(telefone/e-mail fixos no texto)* | `{{bss_telefone}}` / `{{bss_email}}` | Deixe de digitar à mão — muda num lugar só |

❓ **Variáveis do legado ainda não mapeadas:** conforme a BSS colar os outros
modelos, novas `$contact_..._c` vão aparecer. Cada uma precisa de uma linha
aqui + uma entrada no catálogo (`app/modelo_variaveis.py`). Mandar a lista
completa dos campos custom do SuiteCRM aceleraria isso.

---

## Exemplo convertido

O modelo "Empresa Inadimplente" que a BSS passou, já em nomes novos
(destinatário = **contato**):

```
Assunto: Empresa Inadimplente

{{contato_nome}},

Esperamos que esta mensagem o(a) encontre bem. Estamos entrando em contato para
informar que as empresas abaixo estão INADIMPLENTES com as contribuições à
BSS - Benefício Social Sindical:

{{lista_empresas_inadimplentes}}

O(s) boleto(s) em aberto prejudicam a todos os trabalhadores no direito de
usufruir de benefícios para amparo social. Confira o que temos em aberto:

{{lista_boletos_vencidos}}

Informamos também que o descumprimento da cláusula da CCT [...] implicará em
responsabilidade civil [...] conforme artigos 186, 927, 932, III e 933 do
Código Civil Brasileiro.

Em caso de dúvidas, nossa Equipe está pronta para ajudar das 8h00 às 17h00, de
segunda a sexta-feira via {{bss_telefone}} ou pelo e-mail {{bss_email}}.

Atenciosamente,
Financeiro BSS
```

> Diferença de modelagem: o legado repetia o nome/CNPJ da empresa em campos
> soltos (`$contact_empresa_inadimplente_c`) **e** listava os boletos. No novo,
> `{{lista_empresas_inadimplentes}}` já traz empresa + CNPJ numa tabela, e
> `{{lista_boletos_vencidos}}` detalha os boletos. Se a BSS preferir manter a
> frase no singular ("a empresa X"), dá pra criar uma variável de empresa única
> — é só pedir.

---

## Como funciona por dentro

- **Tabela:** `bss.modelo_email` (migração 21). `codigo` é a chave estável que
  o disparo automático vai procurar — **não renomear** depois de ligado a um
  gatilho. `destinatario` define o conjunto de variáveis e **não** é editável
  pela tela (mudá-lo tornaria variáveis órfãs em massa).
- **Catálogo + resolvedor:** `app/modelo_variaveis.py`. Cada variável declara
  escopo e tipo, e sabe se resolver contra um contexto real montado uma vez por
  envio (não uma query por variável).
- **Órfãs:** `{{xyz}}` que não existe, ou existe em escopo errado, aparece
  destacada no preview e **impede ativar** o modelo — pra nunca sair `{{xyz}}`
  cru num disparo real.
- **Preview:** resolve contra uma empresa/contato de verdade. Para o
  `maurofig334@gmail.com` (11 empresas, algumas inadimplentes), a lista de
  boletos vencidos vem preenchida.
