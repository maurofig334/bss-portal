-- ============================================================================
-- BSS - Schema inicial do PostgreSQL
-- ============================================================================
-- Modelo limpo derivado do SuiteCRM legado, mas eliminando:
--   - Tabelas _cstm separadas (mescladas em cada entidade)
--   - Tabelas _audit (vamos usar gatilhos quando precisar de histórico)
--   - Tabelas N-N "burras" (viraram FKs simples quando 1:N)
--   - Campos do CRM nunca usados (industry, ticker_symbol, etc.)
--   - Duplicidades (cpf_c + cpf_unformat_c, dados bancários repetidos)
--
-- Convenções:
--   - PK: bigserial (id) — mais leve que UUID
--   - id_legado_uuid: char(36) — guarda o UUID original do SuiteCRM (sync)
--   - Datas de auditoria: criado_em, atualizado_em (timestamptz)
--   - Soft-delete: ativo BOOLEAN (em vez de deleted=0/1)
--   - CPF/CNPJ: varchar(14)/varchar(18) sem máscara
-- ============================================================================

-- Limpar (cuidado em produção!)
-- DROP SCHEMA IF EXISTS bss CASCADE;
-- CREATE SCHEMA bss;
-- SET search_path = bss;


-- ============================================================================
-- 1. SINDICATO
-- ============================================================================
CREATE TABLE bss.sindicato (
    id                      BIGSERIAL PRIMARY KEY,
    id_legado_uuid          CHAR(36) UNIQUE,
    razao_social            VARCHAR(255) NOT NULL,
    nome_fantasia           VARCHAR(255),
    -- CNPJ NÃO é UNIQUE: legado da GNB tem casos de mesmo CNPJ em sindicatos
    -- diferentes (provavelmente duplicação de cadastro). Limpar manualmente
    -- depois da migração e adicionar UNIQUE quando data estiver consistente.
    cnpj                    VARCHAR(14),
    federacao               VARCHAR(255),
    categoria               VARCHAR(100),
    presidente              VARCHAR(255),
    vice_presidente         VARCHAR(255),
    uf_abrangencia          VARCHAR(2),
    contrato_bss            VARCHAR(255),
    em_atendimento          BOOLEAN NOT NULL DEFAULT TRUE,
    ativo                   BOOLEAN NOT NULL DEFAULT TRUE,
    -- Cache de contagem (atualizado por trigger ou job — performance):
    qtd_trabalhadores_ativos    INT NOT NULL DEFAULT 0,
    qtd_trabalhadores_inativos  INT NOT NULL DEFAULT 0,
    criado_em               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_sindicato_cnpj ON bss.sindicato (cnpj);
CREATE INDEX idx_sindicato_ativo ON bss.sindicato (ativo) WHERE ativo;


-- ============================================================================
-- 2. PARÂMETROS DE BOLETO (1 por sindicato — taxa, banco, vencimentos por mês)
-- ============================================================================
CREATE TABLE bss.parametros_boleto (
    id                      BIGSERIAL PRIMARY KEY,
    id_legado_uuid          CHAR(36) UNIQUE,
    id_sindicato            BIGINT NOT NULL REFERENCES bss.sindicato(id),
    tarifa_titular          NUMERIC(10,2) NOT NULL,
    aceita_dependentes      BOOLEAN NOT NULL DEFAULT FALSE,
    tarifa_dependente       NUMERIC(10,2),
    carencia_dependente_dias INT,
    -- Vencimento por mês (dia do mês — int 1..28):
    vencimento_jan          SMALLINT,
    vencimento_fev          SMALLINT,
    vencimento_mar          SMALLINT,
    vencimento_abr          SMALLINT,
    vencimento_mai          SMALLINT,
    vencimento_jun          SMALLINT,
    vencimento_jul          SMALLINT,
    vencimento_ago          SMALLINT,
    vencimento_set          SMALLINT,
    vencimento_out          SMALLINT,
    vencimento_nov          SMALLINT,
    vencimento_dez          SMALLINT,
    -- Banco/conta pra emissão:
    banco_geracao_boleto    VARCHAR(100),
    banco_boleto_dependente VARCHAR(100),
    -- Tipo (mensal? trimestral? — precisa esclarecer)
    tipo                    VARCHAR(50),
    ativo                   BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_param_boleto_sindicato ON bss.parametros_boleto (id_sindicato);


-- ============================================================================
-- 3. TIPO DE BENEFÍCIO (catálogo — populado com base na análise do legado)
-- ============================================================================
-- Distribuição real (18.178 processos, 2024-2026): NATALIDADE 81%, FALECIMENTO 13%,
-- CONSULTA MEDICA 3%, ACIDENTE 1%, ACIONAMENTO FUNERAL ~1%, demais <1%.
CREATE TABLE bss.tipo_beneficio (
    id                      SMALLSERIAL PRIMARY KEY,
    codigo                  VARCHAR(50) UNIQUE NOT NULL,
    nome                    VARCHAR(150) NOT NULL,
    descricao               TEXT,
    ordem                   SMALLINT NOT NULL DEFAULT 0,
    ativo                   BOOLEAN NOT NULL DEFAULT TRUE
);
INSERT INTO bss.tipo_beneficio (codigo, nome, ordem) VALUES
    ('natalidade',         'Natalidade',         1),
    ('falecimento',        'Falecimento',        2),
    ('consulta_medica',    'Consulta Médica',    3),
    ('acidente',           'Acidente',           4),
    ('acionamento_funeral','Acionamento Funeral',5),
    ('exame',              'Exame',              6),
    ('reembolso_rescisao', 'Reembolso Rescisão', 7),
    ('incapacitacao',      'Incapacitação',      8),
    ('brinde_sindicato',   'Brinde Sindicato',   9),
    ('auxilio_creche',     'Auxílio Creche',     10);


-- ============================================================================
-- 3b. STATUS DE PROCESSO (catálogo — populado com base no legado)
-- ============================================================================
-- Os 12 status vivos no legado (de 18k processos, 2024-2026).
-- 'Em Análise' do legado morreu (8 registros, sem uso desde abr/2026) — fica ativo=false.
-- 'contribuicao_pendente' é aplicado pelo job diário motivo_bloqueio_processo().
CREATE TABLE bss.status_processo (
    id              SMALLSERIAL PRIMARY KEY,
    codigo          VARCHAR(40) UNIQUE NOT NULL,
    nome            VARCHAR(80) NOT NULL,
    categoria       VARCHAR(20) NOT NULL,
                    -- analise / aprovacao / bloqueio / autorizacao / execucao / terminal
    eh_terminal     BOOLEAN NOT NULL DEFAULT FALSE,
    cor_hex         VARCHAR(7),
    ordem           SMALLINT NOT NULL DEFAULT 0,
    ativo           BOOLEAN NOT NULL DEFAULT TRUE
);
INSERT INTO bss.status_processo (codigo, nome, categoria, eh_terminal, cor_hex, ordem, ativo) VALUES
    ('andamento_inicial',     'Andamento Inicial',      'analise',     FALSE, '#94A3B8',  1, TRUE),
    ('em_aprovacao',          'Em Aprovação',           'aprovacao',   FALSE, '#3B82F6',  2, TRUE),
    ('documentacao_conforme', 'Documentação Conforme',  'analise',     FALSE, '#06B6D4',  3, TRUE),
    ('documentacao_pendente', 'Documentação Pendente',  'bloqueio',    FALSE, '#F59E0B',  4, TRUE),
    ('confirmacao_dados',     'Confirmação de Dados',   'bloqueio',    FALSE, '#F59E0B',  5, TRUE),
    ('irregularidade_dados',  'Irregularidade de Dados','bloqueio',    FALSE, '#EF4444',  6, TRUE),
    ('contribuicao_pendente', 'Contribuição Pendente',  'bloqueio',    FALSE, '#EF4444',  7, TRUE),
    ('aguardando_informacao', 'Aguardando Informação',  'bloqueio',    FALSE, '#F59E0B',  8, TRUE),
    ('autorizado_financeiro', 'Autorizado Financeiro',  'autorizacao', FALSE, '#10B981',  9, TRUE),
    ('cartao_solicitado',     'Cartão Solicitado',      'execucao',    FALSE, '#8B5CF6', 10, TRUE),
    ('cartao_em_transporte',  'Cartão em Transporte',   'execucao',    FALSE, '#8B5CF6', 11, TRUE),
    ('em_andamento',          'Em Andamento',           'execucao',    FALSE, '#10B981', 12, TRUE),
    ('beneficio_finalizado',  'Benefício Finalizado',   'terminal',    TRUE,  '#22C55E', 13, TRUE),
    ('solicitacao_cancelada', 'Solicitação Cancelada',  'terminal',    TRUE,  '#6B7280', 14, TRUE),
    -- Status morto no legado (mantido só pra histórico, novos processos não usam):
    ('em_analise',            'Em Análise',             'analise',     FALSE, '#94A3B8', 99, FALSE);


-- ============================================================================
-- 4. VALORES DE BENEFÍCIO POR SINDICATO
-- ============================================================================
-- Cada sindicato configura, pra cada tipo de benefício:
--   - Quanto paga (1º pagamento + parcelas mensais)
--   - Em quanto tempo (prazo_dias)
--   - Como paga (PIX/cartão/depósito) — define se entra no fluxo de cartão
-- Ex (do screenshot do legado):
--   FALECIMENTO   → 1º=0,    6 parcelas × R$ 144,65, prazo=30, forma=cartao
--   NATALIDADE    → 1º=642,  0 parcelas,             prazo=30, forma=pix
CREATE TABLE bss.valor_beneficio_sindicato (
    id                      BIGSERIAL PRIMARY KEY,
    id_sindicato            BIGINT NOT NULL REFERENCES bss.sindicato(id),
    id_tipo_beneficio       SMALLINT NOT NULL REFERENCES bss.tipo_beneficio(id),
    primeiro_pagamento      NUMERIC(18,2) NOT NULL DEFAULT 0,
    qtd_parcelas            INT           NOT NULL DEFAULT 0,
    valor_parcela           NUMERIC(18,2) NOT NULL DEFAULT 0,
    -- Total calculado automaticamente — sempre consistente:
    valor_total             NUMERIC(18,2) GENERATED ALWAYS AS
                                (primeiro_pagamento + qtd_parcelas * valor_parcela) STORED,
    prazo_dias              INT,            -- 30 = paga em até 30 dias após aprovado_financeiro
    -- Forma de pagamento padrão — define se workflow entra em fluxo de cartão:
    forma_pagamento_padrao  VARCHAR(20),    -- 'pix', 'ted', 'cartao', 'deposito', 'cheque'
    prazo_descricao         VARCHAR(255),   -- texto livre p/ casos especiais
    ativo                   BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id_sindicato, id_tipo_beneficio)
);
CREATE INDEX idx_valor_benef_sindicato ON bss.valor_beneficio_sindicato (id_sindicato);
CREATE INDEX idx_valor_benef_tipo ON bss.valor_beneficio_sindicato (id_tipo_beneficio);


-- ============================================================================
-- 5. EMPRESA (clientes)
-- ============================================================================
CREATE TABLE bss.empresa (
    id                      BIGSERIAL PRIMARY KEY,
    id_legado_uuid          CHAR(36) UNIQUE,
    razao_social            VARCHAR(255) NOT NULL,
    nome_fantasia           VARCHAR(255),
    -- CNPJ NÃO é UNIQUE: legado tem dupes (cadastros duplicados, filiais com mesmo CNPJ).
    -- Limpar manualmente depois e adicionar UNIQUE quando data estiver consistente.
    cnpj                    VARCHAR(14),
    -- Endereço:
    logradouro              VARCHAR(150),
    numero                  VARCHAR(20),
    complemento             VARCHAR(100),
    bairro                  VARCHAR(100),
    cidade                  VARCHAR(100),
    uf                      VARCHAR(2),
    cep                     VARCHAR(8),
    -- Contato/telefone:
    telefone                VARCHAR(20),
    -- Status operacional:
    status                  VARCHAR(50) NOT NULL DEFAULT 'ativa',  -- ativa, suspensa, cancelada, inativa
    -- Adimplência financeira (boletos pagos):
    --   'adimplente'  = nenhum boleto vencido em aberto
    --   'inadimplente'= 1+ boleto vencido sem pagamento
    -- Calculável on-demand via VIEW bss.empresa_inadimplencia; campo aqui é
    -- snapshot do legado / cache pra UIs rápidas.
    adimplencia             VARCHAR(20),
    -- Regularidade de submissão de planilhas mensais:
    --   'regular'   = entregou todos os meses sem gap
    --   'irregular' = falhou em algum mês passado
    -- Calculável on-demand via VIEW bss.empresa_meses_faltantes; campo aqui é
    -- snapshot do legado / cache pra UIs rápidas.
    regularidade            VARCHAR(20),
    recebe_email_financeiro BOOLEAN NOT NULL DEFAULT TRUE,
    -- Cache de contagem (atualizado por job):
    qtd_trabalhadores_ativos    INT NOT NULL DEFAULT 0,
    qtd_trabalhadores_inativos  INT NOT NULL DEFAULT 0,
    qtd_dependentes_ativos      INT NOT NULL DEFAULT 0,
    -- Datas operacionais:
    ultimo_boleto_em        DATE,
    ultima_notificacao_em   DATE,
    criado_em               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_empresa_cnpj ON bss.empresa (cnpj);
CREATE INDEX idx_empresa_status ON bss.empresa (status);


-- ============================================================================
-- 6. EMPRESA × SINDICATO — relação DERIVADA (não é tabela física!)
-- ============================================================================
-- DECISÃO DE MODELAGEM (2026-05-04):
-- A relação empresa↔sindicato é INDIRETA: empresa não escolhe sindicato,
-- ela só tem trabalhadores que estão filiados a sindicatos diferentes.
--
-- O legado tinha tabela física `accounts_sindi_sindicatos_1_c` (8.972 linhas)
-- como CACHE pra performance, porque a query original (4 JOINs sem índices
-- certeiros) era inviável. No Postgres com índices certeiros, calcular essa
-- agregação on-the-fly em ~300k trabalhadores roda em milissegundos.
--
-- A relação fica como VIEW abaixo (definida após bss.trabalhador). Se o volume
-- crescer muito (acima de 5M trabalhadores), promover pra MATERIALIZED VIEW.
-- ============================================================================


-- ============================================================================
-- 7. BASE TERRITORIAL
-- ============================================================================
CREATE TABLE bss.base_territorial (
    id                      BIGSERIAL PRIMARY KEY,
    id_legado_uuid          CHAR(36) UNIQUE,
    nome                    VARCHAR(150) NOT NULL,
    estado                  VARCHAR(2),
    cidade                  VARCHAR(100),
    categoria               VARCHAR(50),
    ativo                   BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX idx_base_estado ON bss.base_territorial (estado);


-- ============================================================================
-- 8. TRABALHADOR (beneficiário — não loga)
-- ============================================================================
-- ORIGEM DOS DADOS (importante pra entender o modelo):
--
-- Vem do UPLOAD MENSAL DE ATIVOS (planilha 4 colunas):
--   cpf, nome_completo, id_empresa_atual (via CNPJ), id_sindicato_atual (via nome)
--
-- Vem do UPLOAD DE DEPENDENTES:
--   cpf, nome_completo, titularidade='dependente', cpf_titular
--
-- Preenchido na ABERTURA DO PROCESSO DE BENEFÍCIO:
--   data_nascimento, telefone, email, endereço completo
--   (cliente NÃO informa essas datas no upload mensal)
--
-- Preenchido na PRIMEIRA INTERAÇÃO COM BOT WHATSAPP (quando rolar #42):
--   telefone (se ainda não tiver)
--
-- DERIVADO automaticamente:
--   situacao, mes_ultimo_vinculo, ultimo_pagamento_em, qtd_dependentes_ativos
-- ============================================================================
CREATE TABLE bss.trabalhador (
    id                      BIGSERIAL PRIMARY KEY,
    id_legado_uuid          CHAR(36) UNIQUE,
    cpf                     VARCHAR(11) NOT NULL,
    nome_completo           VARCHAR(200) NOT NULL,
    data_nascimento         DATE,
    -- data_admissao / data_demissao existem mas NÃO são preenchidas pelo upload
    -- mensal — clientes nunca informam essas datas no Excel. Ficam disponíveis
    -- pra preenchimento manual na abertura do benefício, se a empresa souber.
    -- ATENÇÃO: NÃO usar essas colunas pra detectar lacuna de contribuição —
    -- a regra correta usa bss.trabalhador_lacunas (MIN/MAX da lista_mensal_item).
    data_admissao           DATE,
    data_demissao           DATE,
    --
    -- Vínculos ATUAIS (snapshot — o histórico fica em bss.lista_mensal_item):
    -- Trabalhador pode mudar de empresa/sindicato ao longo do tempo;
    -- estes campos refletem o ÚLTIMO upload em que ele apareceu.
    id_empresa_atual        BIGINT REFERENCES bss.empresa(id),
    id_sindicato_atual      BIGINT REFERENCES bss.sindicato(id),
    mes_ultimo_vinculo      DATE,        -- mês_referencia do último upload em que apareceu
    -- Titularidade (titular vs dependente):
    titularidade            VARCHAR(15) NOT NULL DEFAULT 'titular',  -- 'titular' ou 'dependente'
    cpf_titular             VARCHAR(11),       -- preenchido se titularidade='dependente'
    qtd_dependentes_ativos  INT NOT NULL DEFAULT 0,
    -- Estado:
    situacao                VARCHAR(50) NOT NULL DEFAULT 'ativo',    -- ativo, inativo, carência
    data_fim_carencia       DATE,
    ultimo_pagamento_em     DATE,
    -- Contato:
    telefone                VARCHAR(20),
    email                   VARCHAR(150),
    -- Endereço:
    logradouro              VARCHAR(150),
    numero                  VARCHAR(20),
    complemento             VARCHAR(100),
    bairro                  VARCHAR(100),
    cidade                  VARCHAR(100),
    uf                      VARCHAR(2),
    cep                     VARCHAR(8),
    -- Auditoria:
    criado_em               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- CPF deveria ser único, mas legado da GNB tem dupes. Manter como índice
-- (não-único) e limpar depois da migração.
CREATE INDEX idx_trab_cpf ON bss.trabalhador (cpf);
CREATE INDEX idx_trab_empresa ON bss.trabalhador (id_empresa_atual);
CREATE INDEX idx_trab_sindicato ON bss.trabalhador (id_sindicato_atual);
CREATE INDEX idx_trab_emp_sind ON bss.trabalhador (id_empresa_atual, id_sindicato_atual) WHERE situacao = 'ativo';
CREATE INDEX idx_trab_situacao ON bss.trabalhador (situacao);
CREATE INDEX idx_trab_cpf_titular ON bss.trabalhador (cpf_titular) WHERE titularidade = 'dependente';


-- ============================================================================
-- 9. LISTA MENSAL (upload de planilha pela empresa — 3 tipos)
-- ============================================================================
-- O portal oferece 3 botões de upload, cada um com planilha de formato próprio:
--
--   tipo_upload='ativos'     — planilha mensal obrigatória (4 colunas):
--                               CNPJ_EMPRESA, CPF, NOME_COMPLETO, SINDICATO_LABORAL
--                              Cria/atualiza lista_mensal_item; quem não vier
--                              fica inativo (regra de desativação automática).
--
--   tipo_upload='inativacao' — desliga CPFs explicitamente (CNPJ + lista de CPF).
--                              Usado quando empresa quer marcar saída no meio do
--                              mês sem esperar o ciclo do upload de ativos.
--
--   tipo_upload='dependentes'— adiciona dependentes (CNPJ + CPF_TITULAR +
--                              CPF_DEPENDENTE + NOME_DEPENDENTE).
--                              Cria trabalhador com titularidade='dependente'
--                              e cpf_titular preenchido.
CREATE TABLE bss.lista_mensal (
    id                      BIGSERIAL PRIMARY KEY,
    id_empresa              BIGINT NOT NULL REFERENCES bss.empresa(id),
    tipo_upload             VARCHAR(20) NOT NULL DEFAULT 'ativos',
                            -- 'ativos', 'inativacao', 'dependentes'
    mes_referencia          DATE NOT NULL,    -- sempre dia 1 (ex: 2026-05-01)
    data_upload             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    arquivo_original_nome   VARCHAR(255),
    arquivo_url             VARCHAR(500),     -- S3/R2 do Excel original
    qtd_linhas_processadas  INT NOT NULL DEFAULT 0,
    qtd_linhas_erro         INT NOT NULL DEFAULT 0,
    status                  VARCHAR(20) NOT NULL DEFAULT 'processando',
                            -- 'processando', 'concluido', 'erro', 'parcial'
    erro_mensagem           TEXT,
    criado_em               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_lista_empresa_mes ON bss.lista_mensal (id_empresa, mes_referencia DESC, tipo_upload);

-- REGRA DE DESATIVAÇÃO AUTOMÁTICA (confirmada com cliente 2026-05-04):
-- Cada upload de lista_mensal pela empresa é a fonte da verdade do mês.
-- Algoritmo após processar o arquivo:
--   1. Insere/atualiza um lista_mensal_item por CPF da planilha (ativo).
--   2. Para todo trabalhador onde id_empresa_atual = empresa_X e
--      situacao = 'ativo' E que NÃO apareceu nesta lista_mensal,
--      desativa: situacao='inativo' (perde benefícios e sai do boleto).
--   3. Atualiza trabalhador.id_empresa_atual / id_sindicato_atual /
--      mes_ultimo_vinculo conforme o arquivo.
-- Esta lógica deve ficar em bss.processar_lista_mensal(id_lista) — função/job.


-- ============================================================================
-- 9b. LISTA MENSAL ITEM — fonte da verdade do vínculo histórico
-- ============================================================================
-- Cada linha = "trabalhador X, no upload da empresa Y do mês M, estava
-- filiado ao sindicato Z". É O HISTÓRICO CHAPADO. Tudo derivado (vinculo
-- atual, contagens por mês, mudanças de empresa/sindicato) sai daqui.
CREATE TABLE bss.lista_mensal_item (
    id                      BIGSERIAL PRIMARY KEY,
    id_lista_mensal         BIGINT NOT NULL REFERENCES bss.lista_mensal(id) ON DELETE CASCADE,
    id_trabalhador          BIGINT NOT NULL REFERENCES bss.trabalhador(id),
    -- Snapshot dos vínculos no momento do upload:
    id_empresa              BIGINT NOT NULL REFERENCES bss.empresa(id),
    id_sindicato            BIGINT NOT NULL REFERENCES bss.sindicato(id),
    mes_referencia          DATE NOT NULL,        -- redundante (= lista_mensal.mes_referencia) mas crítico p/ índice
    -- Snapshot da pessoa (caso muda nome entre meses):
    nome_completo           VARCHAR(200),
    titularidade            VARCHAR(15) NOT NULL DEFAULT 'titular',
    -- Status no upload (ativo, demitido, em afastamento):
    situacao_no_upload      VARCHAR(50) NOT NULL DEFAULT 'ativo',
    criado_em               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id_lista_mensal, id_trabalhador),
    -- REGRA DE NEGÓCIO (confirmada com cliente 2026-05-04):
    -- Trabalhador NÃO pode estar em 2 empresas no mesmo mês de referência.
    -- Tecnicamente possível na vida real, mas descartado pelo cliente p/
    -- descomplicar a operação. Banco bloqueia por design:
    UNIQUE (id_trabalhador, mes_referencia)
);
CREATE INDEX idx_lmi_trab_mes ON bss.lista_mensal_item (id_trabalhador, mes_referencia DESC);
CREATE INDEX idx_lmi_emp_mes ON bss.lista_mensal_item (id_empresa, mes_referencia);
CREATE INDEX idx_lmi_sind_mes ON bss.lista_mensal_item (id_sindicato, mes_referencia);


-- ============================================================================
-- 10. BOLETO (1 boleto por sindicato envolvido em uma lista mensal)
-- ============================================================================
CREATE TABLE bss.boleto (
    id                      BIGSERIAL PRIMARY KEY,
    id_legado_uuid          CHAR(36) UNIQUE,
    -- numero_boleto: deveria ser único (sequencial), mas legado tem dupes.
    numero_boleto           BIGINT,
    id_lista_mensal         BIGINT REFERENCES bss.lista_mensal(id),
    -- FKs nullable durante migração (legado tem registros órfãos).
    -- Em produção, novos boletos devem sempre preencher.
    id_empresa              BIGINT REFERENCES bss.empresa(id),
    id_sindicato            BIGINT REFERENCES bss.sindicato(id),
    mes_referencia          DATE NOT NULL,        -- dia 1 do mês de referência
    -- Valores:
    qtd_trabalhadores       INT NOT NULL DEFAULT 0,
    qtd_dependentes         INT NOT NULL DEFAULT 0,
    valor_total             NUMERIC(18,2) NOT NULL,
    -- Bancário:
    banco                   VARCHAR(100),
    nosso_numero            VARCHAR(50),
    linha_digitavel         VARCHAR(60),
    codigo_barras           VARCHAR(50),
    link_pdf                VARCHAR(500),
    -- Status / fluxo:
    status                  VARCHAR(20) NOT NULL DEFAULT 'gerado',
                            -- 'gerado', 'enviado', 'pago', 'vencido', 'cancelado'
    tipo                    VARCHAR(50),
    -- data_emissao: na migração legado tem alguns nulls; em produção sempre preenche.
    data_emissao            TIMESTAMPTZ DEFAULT NOW(),
    data_vencimento         DATE,
    data_pagamento          DATE,
    -- Auditoria:
    criado_em               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_boleto_empresa_mes ON bss.boleto (id_empresa, mes_referencia DESC);
CREATE INDEX idx_boleto_sindicato_mes ON bss.boleto (id_sindicato, mes_referencia DESC);
CREATE INDEX idx_boleto_status ON bss.boleto (status) WHERE status IN ('gerado', 'enviado', 'vencido');


-- ============================================================================
-- 11. BOLETO_ITEM (a "killer table" — 1 linha por trabalhador no boleto)
-- ============================================================================
-- Equivalente ao bolet_boletos_traba_trabalhadores_1_c (4.9M linhas no legado)
-- AQUI fica a auditoria: "trabalhador X estava coberto em maio/2026 → boleto Y"
CREATE TABLE bss.boleto_item (
    id                      BIGSERIAL PRIMARY KEY,
    id_boleto               BIGINT NOT NULL REFERENCES bss.boleto(id) ON DELETE CASCADE,
    id_trabalhador          BIGINT NOT NULL REFERENCES bss.trabalhador(id),
    -- id_sindicato: nullable durante migração (trabalhadores órfãos no legado).
    -- Em produção sempre preenche (= boleto.id_sindicato).
    id_sindicato            BIGINT REFERENCES bss.sindicato(id),
    mes_referencia          DATE NOT NULL,        -- redundante mas crítico pra performance
    -- Snapshot de valor (se sindicato mudar taxa, esse fica imutável).
    -- Default 0: na migração não temos histórico, novos itens preenchem corretamente.
    taxa_aplicada           NUMERIC(10,2) NOT NULL DEFAULT 0,
    eh_dependente           BOOLEAN NOT NULL DEFAULT FALSE,
    criado_em               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Índices estratégicos pras queries mais comuns:
CREATE INDEX idx_bolitem_boleto ON bss.boleto_item (id_boleto);
CREATE INDEX idx_bolitem_trab_mes ON bss.boleto_item (id_trabalhador, mes_referencia DESC);
CREATE INDEX idx_bolitem_sind_mes ON bss.boleto_item (id_sindicato, mes_referencia);
-- (Particionar por mes_referencia quando passar de 50M linhas)


-- ============================================================================
-- 12. PROCESSO DE BENEFÍCIO (= cases — solicitação de benefício)
-- ============================================================================
CREATE TABLE bss.processo_beneficio (
    id                      BIGSERIAL PRIMARY KEY,
    id_legado_uuid          CHAR(36) UNIQUE,
    -- numero_processo = case_number do SuiteCRM (sequencial, INTERNO — não exibido ao cliente).
    -- Mantido só pra rastreabilidade da migração; novos processos não precisam preencher.
    numero_processo         BIGINT,
    -- protocolo = ID que o cliente vê (formato AAMMDD + 3 dígitos sequenciais por dia).
    -- NULL durante migração — gerar via bss.gerar_protocolo() pra novos processos.
    protocolo               VARCHAR(9) UNIQUE,
    -- FKs nullable durante migração de legado (registros órfãos esperados);
    -- novos processos no BSS sempre preenchem:
    id_trabalhador          BIGINT REFERENCES bss.trabalhador(id),
    id_sindicato            BIGINT REFERENCES bss.sindicato(id),
    id_empresa              BIGINT REFERENCES bss.empresa(id),
    id_tipo_beneficio       SMALLINT REFERENCES bss.tipo_beneficio(id),
    id_base_territorial     BIGINT REFERENCES bss.base_territorial(id),
    -- Status do processo (workflow — ver bss.processo_andamento p/ histórico):
    status                  VARCHAR(30) NOT NULL DEFAULT 'andamento_inicial',
                            -- 'andamento_inicial'    — entrou na fila
                            -- 'em_analise'           — analista pegou; revisando docs
                            -- 'documentacao_pendente'— 1+ doc rejeitado; empresa reanexa
                            -- 'contribuicao_pendente'— bloqueio de regularidade (3 condições)
                            -- 'aprovado_analise'     — todos docs OK
                            -- 'aprovado_financeiro'  — financeiro liberou (avisa empresa)
                            -- 'pago' / 'finalizado' / 'rejeitado' / 'cancelado'
    -- Controle do job de reavaliação automática:
    bloqueio_motivo         TEXT,           -- snapshot do retorno de motivo_bloqueio_processo()
    bloqueio_verificado_em  TIMESTAMPTZ,    -- última vez que o job rodou nesse processo
    situacao_acionamento    VARCHAR(50),
    causa_mortis            VARCHAR(100),     -- só pra benefícios de falecimento
    -- liberalidade: regra de pagamento aplicada (3 valores fixos, escolha manual):
    --   'regular'           — caso padrão (~97% dos processos no legado)
    --   'por_inadimplencia' — empresa estava inadimplente quando evento ocorreu (~2.7%)
    --   'por_prazo'         — concedido fora do prazo regular (~0.6%)
    liberalidade            VARCHAR(20),
    -- Valores:
    valor_solicitado        NUMERIC(18,2),
    valor_aprovado          NUMERIC(18,2),
    qtd_parcelas            INT,
    -- Beneficiário (pode ser diferente do trabalhador — ex: dependente, viúva):
    beneficiario_nome       VARCHAR(255),
    beneficiario_cpf        VARCHAR(11),
    beneficiario_telefone   VARCHAR(20),
    beneficiario_data_nasc  DATE,
    beneficiario_grau_parentesco VARCHAR(50),
    beneficiario_endereco_logradouro    VARCHAR(150),
    beneficiario_endereco_numero        VARCHAR(20),
    beneficiario_endereco_complemento   VARCHAR(100),
    beneficiario_endereco_bairro        VARCHAR(100),
    beneficiario_endereco_cidade        VARCHAR(100),
    beneficiario_endereco_uf            VARCHAR(2),
    beneficiario_endereco_cep           VARCHAR(8),
    -- Casos específicos:
    qtd_bebes               INT,              -- benefício natalidade (gêmeos, trigêmeos)
    data_obito              DATE,             -- benefício falecimento
    data_evento             DATE,             -- data do fato gerador
    data_finalizacao        DATE,
    -- Forma de pagamento (escolha do beneficiário):
    forma_pagamento         VARCHAR(30),       -- 'pix', 'ted', 'doc', 'boleto', 'cartao'
    -- Cartão (se forma_pagamento='cartao' — preenchido em ~62% dos processos no legado):
    codigo_rastreio_cartao  VARCHAR(50),       -- código dos correios pra entrega
    vencimento_cartao_em    DATE,              -- data de vencimento do cartão emitido
    -- Auditoria:
    chat_descricao          TEXT,
    dados_revisados         BOOLEAN NOT NULL DEFAULT FALSE,
    criado_em               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_proc_status ON bss.processo_beneficio (status);
CREATE INDEX idx_proc_trabalhador ON bss.processo_beneficio (id_trabalhador);
CREATE INDEX idx_proc_sindicato ON bss.processo_beneficio (id_sindicato);
CREATE INDEX idx_proc_empresa ON bss.processo_beneficio (id_empresa);
CREATE INDEX idx_proc_tipo ON bss.processo_beneficio (id_tipo_beneficio);
CREATE INDEX idx_proc_data_evento ON bss.processo_beneficio (data_evento);


-- ============================================================================
-- 13. DADOS BANCÁRIOS (extraído — antes ficava duplicado em cases)
-- ============================================================================
-- Cada processo pode ter múltiplas contas (a da empresa pra reembolso e
-- a do beneficiário pra pagamento).
CREATE TABLE bss.dados_bancarios (
    id                      BIGSERIAL PRIMARY KEY,
    id_processo             BIGINT NOT NULL REFERENCES bss.processo_beneficio(id) ON DELETE CASCADE,
    titular_tipo            VARCHAR(20) NOT NULL,    -- 'empresa' ou 'beneficiario'
    cnpj_cpf_titular        VARCHAR(14),
    banco_codigo            VARCHAR(3),
    agencia                 VARCHAR(10),
    conta                   VARCHAR(20),
    digito                  VARCHAR(2),
    tipo_conta              VARCHAR(20),     -- 'corrente', 'poupanca'
    chave_pix               VARCHAR(140),
    criado_em               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_dadosbanc_processo ON bss.dados_bancarios (id_processo);


-- ============================================================================
-- 14. PAGAMENTO (1+ por processo — pode ser parcelado)
-- ============================================================================
CREATE TABLE bss.pagamento (
    id                      BIGSERIAL PRIMARY KEY,
    id_legado_uuid          CHAR(36) UNIQUE,
    numero_pagamento        BIGINT,            -- = id_cpagar_c (sequencial)
    id_processo             BIGINT NOT NULL REFERENCES bss.processo_beneficio(id),
    parcela                 INT NOT NULL DEFAULT 1,
    documento               VARCHAR(255),
    valor                   NUMERIC(18,2) NOT NULL,
    forma_pagamento         VARCHAR(30),
    status                  VARCHAR(20) NOT NULL DEFAULT 'pendente',
                            -- 'pendente', 'pago', 'cancelado'
    data_prevista           DATE,
    data_vencimento         DATE,
    data_pagamento          DATE,
    -- Beneficiário pode mudar entre parcelas (ex: pensão alimentícia)
    beneficiario_nome       VARCHAR(255),
    beneficiario_cpf        VARCHAR(11),
    -- Dados bancários da parcela específica:
    id_dados_bancarios      BIGINT REFERENCES bss.dados_bancarios(id),
    criado_em               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_pgto_processo ON bss.pagamento (id_processo);
CREATE INDEX idx_pgto_status ON bss.pagamento (status);
CREATE INDEX idx_pgto_data_prev ON bss.pagamento (data_prevista) WHERE status = 'pendente';


-- ============================================================================
-- 15. DOCUMENTO (anexos polimórficos)
-- ============================================================================
CREATE TABLE bss.documento (
    id                      BIGSERIAL PRIMARY KEY,
    id_legado_uuid          CHAR(36) UNIQUE,
    nome_original           VARCHAR(255) NOT NULL,
    arquivo_url             VARCHAR(500) NOT NULL,    -- S3/R2/local
    mime_type               VARCHAR(100),
    tamanho_bytes           BIGINT,
    -- Polimorfismo: documento pode pertencer a processo, boleto, empresa, etc.
    entidade_tipo           VARCHAR(30) NOT NULL,    -- 'processo', 'boleto', 'empresa'
    entidade_id             BIGINT NOT NULL,
    -- Categoria opcional ('rg', 'comprovante_residencia', 'atestado', etc.):
    categoria               VARCHAR(50),
    descricao               TEXT,
    enviado_por_id          BIGINT,         -- referência a bss_users
    criado_em               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_doc_entidade ON bss.documento (entidade_tipo, entidade_id);


-- ============================================================================
-- 16. MOTIVO_REJEICAO_DOCUMENTO (catálogo de motivos)
-- ============================================================================
CREATE TABLE bss.motivo_rejeicao_documento (
    id          SMALLSERIAL PRIMARY KEY,
    codigo      VARCHAR(30) UNIQUE NOT NULL,
    nome        VARCHAR(100) NOT NULL,
    descricao   TEXT,
    ativo       BOOLEAN NOT NULL DEFAULT TRUE,
    ordem       SMALLINT NOT NULL DEFAULT 0
);
INSERT INTO bss.motivo_rejeicao_documento (codigo, nome, ordem) VALUES
    ('rasura',       'Documento com rasura',                1),
    ('ilegivel',     'Documento ilegível',                  2),
    ('impertinente', 'Documento impertinente ao processo',  3),
    ('vencido',      'Documento vencido / fora da validade',4),
    ('incompleto',   'Documento incompleto / faltam folhas',5),
    ('invalido',     'Documento inválido (não confere)',    6),
    ('outro',        'Outro motivo (ver observação)',       99);


-- ============================================================================
-- 17. TIPO_BENEFICIO_DOCUMENTO (regra: quais docs cada tipo exige)
-- ============================================================================
-- Ex: tipo 'falecimento' exige certidão_obito, vinculo_familiar, certidao_casamento;
--     tipo 'natalidade'  exige certidao_nascimento + 2 docs.
-- A empresa só consegue gravar o processo se todos os obrigatórios forem anexados.
CREATE TABLE bss.tipo_beneficio_documento (
    id                  SERIAL PRIMARY KEY,
    id_tipo_beneficio   SMALLINT NOT NULL REFERENCES bss.tipo_beneficio(id),
    codigo              VARCHAR(50) NOT NULL,           -- 'certidao_obito', 'rg', etc.
    nome                VARCHAR(150) NOT NULL,          -- "Certidão de Óbito"
    descricao           TEXT,
    obrigatorio         BOOLEAN NOT NULL DEFAULT TRUE,
    ordem               SMALLINT NOT NULL DEFAULT 0,
    ativo               BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (id_tipo_beneficio, codigo)
);
CREATE INDEX idx_tbd_tipo ON bss.tipo_beneficio_documento (id_tipo_beneficio);


-- ============================================================================
-- 18. PROCESSO_DOCUMENTO (instância: cada doc anexado tem ciclo próprio)
-- ============================================================================
-- Ciclo de vida do DOCUMENTO (independente do status do PROCESSO):
--   pendente   → recém-anexado pela empresa, aguardando avaliação
--   aprovado   → analista validou; UI trava a "caixinha de upload" (✓ documento conforme)
--   rejeitado  → analista recusou; UI mostra motivo e libera reupload
--                (reupload cria nova versão deste registro com status='pendente')
--
-- Status do PROCESSO é DERIVADO do conjunto:
--   1+ doc 'rejeitado'  →  processo fica em 'documentacao_pendente' até resolver
--   1+ doc 'pendente'   →  processo segue 'em_analise'
--   todos 'aprovados'   →  processo pode ir pra 'aprovado_analise'
CREATE TABLE bss.processo_documento (
    id                  BIGSERIAL PRIMARY KEY,
    id_processo         BIGINT NOT NULL REFERENCES bss.processo_beneficio(id) ON DELETE CASCADE,
    id_tipo_documento   INT NOT NULL REFERENCES bss.tipo_beneficio_documento(id),
    id_documento        BIGINT REFERENCES bss.documento(id),  -- arquivo físico (S3/R2)
    versao              SMALLINT NOT NULL DEFAULT 1,          -- a cada reupload incrementa
    status              VARCHAR(20) NOT NULL DEFAULT 'pendente',
                        -- 'pendente', 'aprovado', 'rejeitado'
    id_motivo_rejeicao  SMALLINT REFERENCES bss.motivo_rejeicao_documento(id),
    observacao          TEXT,                                 -- texto livre (motivo='outro' ou nota do analista)
    avaliado_por_id     INT,                                  -- bss_users.id
    avaliado_em         TIMESTAMPTZ,
    criado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_pdoc_processo ON bss.processo_documento (id_processo);
CREATE INDEX idx_pdoc_status   ON bss.processo_documento (status);
-- Apenas 1 versão "ativa" por (processo, tipo_documento) — versões antigas ficam histórico
CREATE UNIQUE INDEX uq_pdoc_proc_tipo_versao ON bss.processo_documento (id_processo, id_tipo_documento, versao);


-- ============================================================================
-- 19. PROCESSO_ANDAMENTO (audit trail das transições de status)
-- ============================================================================
-- Cada mudança no status do processo gera 1 linha aqui — quem, quando, comentário.
-- Permite reconstituir o histórico completo do processo pra auditoria/relatórios.
CREATE TABLE bss.processo_andamento (
    id                  BIGSERIAL PRIMARY KEY,
    id_processo         BIGINT NOT NULL REFERENCES bss.processo_beneficio(id) ON DELETE CASCADE,
    status_anterior     VARCHAR(30),
    status_novo         VARCHAR(30) NOT NULL,
    usuario_id          INT,                            -- bss_users.id (NULL se mudança automática)
    automatico          BOOLEAN NOT NULL DEFAULT FALSE, -- true = trigger / job; false = ação humana
    comentario          TEXT,
    criado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_pand_processo ON bss.processo_andamento (id_processo, criado_em DESC);

-- Estados do processo (atualizar comentário em bss.processo_beneficio.status):
--   andamento_inicial      — entrou na fila, aguardando analista
--   em_analise             — analista pegou; revisando docs
--   documentacao_pendente  — algum doc rejeitado; empresa precisa reanexar
--   aprovado_analise       — todos docs OK, aguarda financeiro
--   aprovado_financeiro    — financeiro liberou; 🔔 dispara mensagem (email + whatsapp futuro)
--   pago                   — pagamento efetuado
--   finalizado             — encerrado
--   rejeitado              — recusado em análise (motivo registrado em andamento)
--   cancelado              — cancelado pela empresa


-- ============================================================================
-- 20. AUTENTICAÇÃO — usuario × empresa (perfil 'empresa' opera N empresas)
-- ============================================================================
-- A tabela `bss_users` (root, fora do schema bss) é criada por
--   scripts/criar_tabela_usuarios.py — ela contém: id, email, nome, senha_hash,
--   ativo, perfil ∈ {admin, interno, analista, empresa, sindicato, contabilidade},
--   criado_em.
--
-- 1 perfil por usuário (confirmado com cliente). Quando perfil='empresa', o
-- vínculo com as empresas que ele opera é N:N via tabela abaixo.
-- (Permissões dentro da empresa são iguais pra todos os usuários — sem hierarquia.)
CREATE TABLE bss.usuario_empresa (
    id_usuario      INT    NOT NULL,                                 -- FK lógica → bss_users.id
    id_empresa      BIGINT NOT NULL REFERENCES bss.empresa(id) ON DELETE CASCADE,
    ativo           BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id_usuario, id_empresa)
);
CREATE INDEX idx_ue_usuario ON bss.usuario_empresa (id_usuario);
CREATE INDEX idx_ue_empresa ON bss.usuario_empresa (id_empresa) WHERE ativo;


-- ============================================================================
-- 21. AUTENTICAÇÃO — usuario × sindicato (perfil 'sindicato' vê N sindicatos)
-- ============================================================================
CREATE TABLE bss.usuario_sindicato (
    id_usuario      INT    NOT NULL,                                 -- FK lógica → bss_users.id
    id_sindicato    BIGINT NOT NULL REFERENCES bss.sindicato(id) ON DELETE CASCADE,
    ativo           BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id_usuario, id_sindicato)
);
CREATE INDEX idx_us_usuario   ON bss.usuario_sindicato (id_usuario);
CREATE INDEX idx_us_sindicato ON bss.usuario_sindicato (id_sindicato) WHERE ativo;


-- ============================================================================
-- VIEWS — relações derivadas (não armazenadas)
-- ============================================================================

-- VIEW: empresa × sindicato ATIVO
-- Substitui a antiga tabela física `accounts_sindi_sindicatos_1_c` do legado.
-- Sempre fresca, calculada on-the-fly. Se virar gargalo, promover a MATERIALIZED.
CREATE OR REPLACE VIEW bss.empresa_sindicato_ativo AS
SELECT
    t.id_empresa_atual                 AS id_empresa,
    t.id_sindicato_atual               AS id_sindicato,
    COUNT(*)                           AS qtd_trabalhadores,
    COUNT(*) FILTER (WHERE t.titularidade = 'titular')     AS qtd_titulares,
    COUNT(*) FILTER (WHERE t.titularidade = 'dependente')  AS qtd_dependentes,
    MAX(t.mes_ultimo_vinculo)          AS ultimo_vinculo
FROM bss.trabalhador t
WHERE t.situacao = 'ativo'
  AND t.id_empresa_atual IS NOT NULL
  AND t.id_sindicato_atual IS NOT NULL
GROUP BY t.id_empresa_atual, t.id_sindicato_atual;

-- Para o sindicato saber "quantas empresas pagam pra mim":
--   SELECT COUNT(*) FROM bss.empresa_sindicato_ativo WHERE id_sindicato = ?
-- Para a empresa saber "em quais sindicatos meus trabalhadores estão":
--   SELECT * FROM bss.empresa_sindicato_ativo WHERE id_empresa = ?

-- VIEW: histórico do trabalhador (todas as empresas/sindicatos por onde passou)
CREATE OR REPLACE VIEW bss.trabalhador_historico AS
SELECT
    lmi.id_trabalhador,
    lmi.id_empresa,
    lmi.id_sindicato,
    MIN(lmi.mes_referencia)            AS mes_inicio,
    MAX(lmi.mes_referencia)            AS mes_fim,
    COUNT(DISTINCT lmi.mes_referencia) AS qtd_meses
FROM bss.lista_mensal_item lmi
GROUP BY lmi.id_trabalhador, lmi.id_empresa, lmi.id_sindicato;


-- ============================================================================
-- REGULARIDADE — bloqueios de benefício (3 condições)
-- ============================================================================
-- Regra de negócio confirmada com cliente (2026-05-04):
-- Benefício é BLOQUEADO se qualquer uma das 3 condições ocorrer:
--   (1) Empresa inadimplente — algum boleto vencido sem pagamento
--   (2) Empresa irregular   — gap de mês na submissão de planilhas
--   (3) Trabalhador com lacuna — falhou alguma contribuição entre admissão e hoje
-- ============================================================================

-- VIEW (1): Empresa inadimplente — boletos vencidos não pagos
CREATE OR REPLACE VIEW bss.empresa_inadimplencia AS
SELECT
    b.id_empresa,
    COUNT(*)                AS qtd_boletos_vencidos,
    SUM(b.valor_total)      AS valor_em_atraso,
    MIN(b.data_vencimento)  AS vencido_desde
FROM bss.boleto b
WHERE b.status IN ('gerado', 'enviado', 'vencido')
  AND b.data_vencimento < CURRENT_DATE
  AND b.data_pagamento IS NULL
GROUP BY b.id_empresa;

-- VIEW (2): Empresa irregular — meses sem submissão de planilha
-- (Compara meses esperados [primeira lista até mês atual] vs meses entregues)
CREATE OR REPLACE VIEW bss.empresa_meses_faltantes AS
WITH primeira_lista AS (
    SELECT id_empresa, MIN(mes_referencia) AS desde
    FROM bss.lista_mensal
    WHERE status IN ('concluido', 'parcial')
    GROUP BY id_empresa
),
meses_esperados AS (
    SELECT
        pl.id_empresa,
        gs::DATE AS mes_esperado
    FROM primeira_lista pl
    CROSS JOIN LATERAL generate_series(
        pl.desde,
        DATE_TRUNC('month', CURRENT_DATE)::DATE,
        INTERVAL '1 month'
    ) AS gs
),
meses_entregues AS (
    SELECT id_empresa, mes_referencia
    FROM bss.lista_mensal
    WHERE status IN ('concluido', 'parcial')
)
SELECT
    me.id_empresa,
    me.mes_esperado AS mes_faltante
FROM meses_esperados me
LEFT JOIN meses_entregues ent
       ON ent.id_empresa = me.id_empresa
      AND ent.mes_referencia = me.mes_esperado
WHERE ent.mes_referencia IS NULL;

-- VIEW (3): Trabalhador com lacuna de contribuição
-- Regra: se o trabalhador contribuiu em jan e em mar, MAS NÃO em fev → fev é lacuna.
-- Período observado = [primeira contribuição, última contribuição] do próprio histórico
-- (data de admissão/demissão NÃO é informada pelos clientes — não usar).
CREATE OR REPLACE VIEW bss.trabalhador_lacunas AS
WITH base AS (
    SELECT
        lmi.id_trabalhador,
        MIN(lmi.mes_referencia) AS desde,
        MAX(lmi.mes_referencia) AS ate
    FROM bss.lista_mensal_item lmi
    GROUP BY lmi.id_trabalhador
    HAVING COUNT(DISTINCT lmi.mes_referencia) > 1   -- precisa de 2+ meses pra ter "gap"
),
meses_esperados AS (
    SELECT
        b.id_trabalhador,
        gs::DATE AS mes_esperado
    FROM base b
    CROSS JOIN LATERAL generate_series(b.desde, b.ate, INTERVAL '1 month') AS gs
),
meses_pagos AS (
    SELECT id_trabalhador, mes_referencia
    FROM bss.lista_mensal_item
)
SELECT
    me.id_trabalhador,
    me.mes_esperado AS mes_faltante
FROM meses_esperados me
LEFT JOIN meses_pagos mp
       ON mp.id_trabalhador  = me.id_trabalhador
      AND mp.mes_referencia  = me.mes_esperado
WHERE mp.id_trabalhador IS NULL;


-- ============================================================================
-- FUNÇÃO: gerar_protocolo()
-- ============================================================================
-- Retorna próximo protocolo no formato AAMMDD + 3 dígitos sequenciais.
-- Sequencial reseta todo dia. Ex: 260504001, 260504002, 260505001.
-- IMPORTANTE: usar dentro da MESMA transação do INSERT do processo, com
-- LOCK na tabela ou retry em caso de violação de unique. Em alta concorrência,
-- migrar pra advisory lock ou sequence dedicada.
CREATE OR REPLACE FUNCTION bss.gerar_protocolo() RETURNS VARCHAR(9)
LANGUAGE plpgsql
AS $$
DECLARE
    v_prefixo VARCHAR(6);
    v_seq     INT;
BEGIN
    v_prefixo := TO_CHAR(NOW() AT TIME ZONE 'America/Sao_Paulo', 'YYMMDD');
    SELECT COALESCE(MAX(SUBSTRING(protocolo FROM 7 FOR 3)::INT), 0) + 1
    INTO v_seq
    FROM bss.processo_beneficio
    WHERE protocolo LIKE v_prefixo || '%';
    RETURN v_prefixo || LPAD(v_seq::TEXT, 3, '0');
END;
$$;

-- Uso:
--   INSERT INTO bss.processo_beneficio (protocolo, ...) VALUES (bss.gerar_protocolo(), ...);


-- ============================================================================
-- FUNÇÃO: pode_abrir_processo(id_trabalhador)
-- ============================================================================
-- Retorna texto vazio se está OK, ou descrição do bloqueio.
-- Usar antes de criar processo + diariamente para reavaliar processos parados.
CREATE OR REPLACE FUNCTION bss.motivo_bloqueio_processo(p_id_trabalhador BIGINT)
RETURNS TEXT
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_id_empresa  BIGINT;
    v_inadimp     RECORD;
    v_meses_emp   INT;
    v_meses_trab  INT;
BEGIN
    SELECT t.id_empresa_atual INTO v_id_empresa
    FROM bss.trabalhador t WHERE t.id = p_id_trabalhador;

    IF v_id_empresa IS NULL THEN
        RETURN 'Trabalhador sem vínculo ativo com empresa';
    END IF;

    -- (1) Empresa inadimplente
    SELECT * INTO v_inadimp FROM bss.empresa_inadimplencia
    WHERE id_empresa = v_id_empresa;
    IF FOUND THEN
        RETURN format(
            'Empresa inadimplente: %s boleto(s) vencido(s) (R$ %s) desde %s',
            v_inadimp.qtd_boletos_vencidos,
            v_inadimp.valor_em_atraso,
            v_inadimp.vencido_desde
        );
    END IF;

    -- (2) Empresa irregular (gap de planilha)
    SELECT COUNT(*) INTO v_meses_emp FROM bss.empresa_meses_faltantes
    WHERE id_empresa = v_id_empresa;
    IF v_meses_emp > 0 THEN
        RETURN format('Empresa irregular: %s mês(es) sem planilha submetida', v_meses_emp);
    END IF;

    -- (3) Trabalhador com lacuna
    SELECT COUNT(*) INTO v_meses_trab FROM bss.trabalhador_lacunas
    WHERE id_trabalhador = p_id_trabalhador;
    IF v_meses_trab > 0 THEN
        RETURN format('Trabalhador com %s mês(es) sem contribuição', v_meses_trab);
    END IF;

    RETURN '';  -- sem bloqueio
END;
$$;

-- Uso:
--   SELECT bss.motivo_bloqueio_processo(12345);
--   → '' (pode abrir) ou 'Empresa inadimplente: ...' / 'Trabalhador com 2 mês(es)...'


-- ============================================================================
-- COMENTÁRIOS FINAIS
-- ============================================================================
-- Tabelas que NÃO migramos (decidido):
--   - *_audit (vamos usar history apenas onde for crítico)
--   - aow_*, aok_*, aor_* (workflow/knowledge/reports do SuiteCRM)
--   - emails*, inbound_email* (não vamos manter sistema de email integrado)
--   - jjwg_* (geocoding — fora do escopo MVP)
--   - tracker, sessions, sugarfeed (sistema interno)
--   - acl_* (substituído pelo sistema de roles do BSS)
--
-- Próximo passo:
--   - Validar com a equipe da GNB se não falta nenhum campo crítico
--   - Confirmar tipos exatos (alguns _cstm têm INT mas dados parecem strings)
--   - Decidir sobre sample/teste: rodar este SQL num Postgres dev e simular dados
