-- ============================================================================
-- Queries para extrair informacao do schema do SuiteCRM legado
-- ============================================================================
--
-- Use estas queries no servidor que ja tem acesso ao MySQL do SuiteCRM
-- (via MySQL Workbench, phpMyAdmin, linha de comando, ou DBeaver).
--
-- ESTRATEGIA SUGERIDA:
--   PASSO 0: rode QUERY 0 pra descobrir o nome do banco
--   PASSO 1: substitua 'suitecrm' por esse nome em TODAS as queries
--   PASSO 2: rode QUERY 1 e me mande o resultado
--   PASSO 3: eu te digo quais sao as tabelas de negocio importantes
--   PASSO 4: voce roda as queries 2x para essas tabelas e me manda
--
-- ============================================================================


-- ============================================================================
-- QUERY 0 - Descobrir os bancos disponiveis (rode isto antes de tudo)
-- ============================================================================

SHOW DATABASES;

-- Ignore: information_schema, mysql, performance_schema, sys
-- O nome restante (geralmente algo como "suitecrm", "crm", "gnb_crm") e o nosso.


-- ============================================================================
-- QUERY 1 - Overview de TODAS as tabelas (rode isto depois)
-- ============================================================================
-- Antes de rodar: Ctrl+H trocar 'suitecrm' pelo nome real do seu banco.

SELECT
    t.TABLE_NAME                                              AS tabela,
    t.TABLE_ROWS                                              AS registros_estimado,
    ROUND((t.DATA_LENGTH + t.INDEX_LENGTH) / 1024 / 1024, 2)  AS tamanho_mb,
    t.ENGINE                                                  AS engine,
    CASE
        WHEN RIGHT(t.TABLE_NAME, 5) = '_cstm'                                     THEN 'CUSTOM'
        WHEN RIGHT(t.TABLE_NAME, 6) = '_audit'                                    THEN 'AUDITORIA'
        WHEN RIGHT(t.TABLE_NAME, 6) = '_files'                                    THEN 'ARQUIVOS'
        WHEN INSTR(t.TABLE_NAME, 'relationships') > 0                             THEN 'RELACAO N-N'
        WHEN INSTR(t.TABLE_NAME, '_rel_') > 0                                     THEN 'RELACAO N-N'
        WHEN t.TABLE_NAME IN ('users','user_preferences','roles','tracker',
                              'sessions','sugarfeed','schedulers','scheduler_logs',
                              'config','saved_search','job_queue','acl_actions',
                              'acl_roles','acl_roles_actions','acl_roles_users')  THEN 'SISTEMA'
        WHEN LEFT(t.TABLE_NAME, 6) = 'oauth_'                                     THEN 'OAUTH'
        WHEN LEFT(t.TABLE_NAME, 4) = 'aow_'                                       THEN 'WORKFLOW'
        WHEN LEFT(t.TABLE_NAME, 4) = 'aok_'                                       THEN 'KNOWLEDGE'
        WHEN LEFT(t.TABLE_NAME, 4) = 'aor_'                                       THEN 'REPORTS'
        WHEN INSTR(t.TABLE_NAME, 'inbound_email') > 0                             THEN 'EMAIL'
        WHEN LEFT(t.TABLE_NAME, 7) = 'emails'                                     THEN 'EMAIL'
        ELSE 'NEGOCIO'
    END AS categoria
FROM information_schema.TABLES t
WHERE t.TABLE_SCHEMA = 'suitecrm'   -- TROQUE pelo nome real do banco
ORDER BY t.TABLE_ROWS DESC;


-- ============================================================================
-- QUERY 1B - Resumo por categoria (visao executiva)
-- ============================================================================

SELECT
    CASE
        WHEN RIGHT(t.TABLE_NAME, 5) = '_cstm'                                     THEN 'CUSTOM'
        WHEN RIGHT(t.TABLE_NAME, 6) = '_audit'                                    THEN 'AUDITORIA'
        WHEN RIGHT(t.TABLE_NAME, 6) = '_files'                                    THEN 'ARQUIVOS'
        WHEN INSTR(t.TABLE_NAME, 'relationships') > 0                             THEN 'RELACAO N-N'
        WHEN INSTR(t.TABLE_NAME, '_rel_') > 0                                     THEN 'RELACAO N-N'
        WHEN t.TABLE_NAME IN ('users','user_preferences','roles','tracker',
                              'sessions','sugarfeed','schedulers','scheduler_logs',
                              'config','saved_search','job_queue','acl_actions',
                              'acl_roles','acl_roles_actions','acl_roles_users')  THEN 'SISTEMA'
        WHEN LEFT(t.TABLE_NAME, 6) = 'oauth_'                                     THEN 'OAUTH'
        WHEN LEFT(t.TABLE_NAME, 4) = 'aow_'                                       THEN 'WORKFLOW'
        WHEN LEFT(t.TABLE_NAME, 4) = 'aok_'                                       THEN 'KNOWLEDGE'
        WHEN LEFT(t.TABLE_NAME, 4) = 'aor_'                                       THEN 'REPORTS'
        WHEN INSTR(t.TABLE_NAME, 'inbound_email') > 0                             THEN 'EMAIL'
        WHEN LEFT(t.TABLE_NAME, 7) = 'emails'                                     THEN 'EMAIL'
        ELSE 'NEGOCIO'
    END AS categoria,
    COUNT(*)                                                  AS qtd_tabelas,
    SUM(t.TABLE_ROWS)                                         AS total_registros,
    ROUND(SUM(t.DATA_LENGTH + t.INDEX_LENGTH)/1024/1024, 2)   AS total_mb
FROM information_schema.TABLES t
WHERE t.TABLE_SCHEMA = 'suitecrm'   -- TROQUE
GROUP BY categoria
ORDER BY total_registros DESC;


-- ============================================================================
-- QUERY 2A - Colunas de UMA tabela
-- ============================================================================

SELECT
    c.COLUMN_NAME    AS coluna,
    c.COLUMN_TYPE    AS tipo,
    c.IS_NULLABLE    AS nullable,
    c.COLUMN_DEFAULT AS valor_padrao,
    c.COLUMN_KEY     AS chave,
    c.EXTRA          AS extra,
    c.COLUMN_COMMENT AS comentario
FROM information_schema.COLUMNS c
WHERE c.TABLE_SCHEMA = 'suitecrm'         -- TROQUE
  AND c.TABLE_NAME   = 'NOME_DA_TABELA'   -- TROQUE
ORDER BY c.ORDINAL_POSITION;


-- ============================================================================
-- QUERY 2B - Indices de UMA tabela
-- ============================================================================

SELECT
    s.INDEX_NAME       AS indice,
    s.COLUMN_NAME      AS coluna,
    s.SEQ_IN_INDEX     AS posicao,
    CASE WHEN s.NON_UNIQUE = 0 THEN 'UNIQUE' ELSE 'INDEX' END AS tipo
FROM information_schema.STATISTICS s
WHERE s.TABLE_SCHEMA = 'suitecrm'         -- TROQUE
  AND s.TABLE_NAME   = 'NOME_DA_TABELA'   -- TROQUE
ORDER BY s.INDEX_NAME, s.SEQ_IN_INDEX;


-- ============================================================================
-- QUERY 2C - CREATE TABLE de UMA tabela (mostra tudo de uma vez)
-- ============================================================================

SHOW CREATE TABLE suitecrm.NOME_DA_TABELA;
-- TROQUE ambos


-- ============================================================================
-- QUERY 3 - Listar TODAS as tabelas que terminam em _cstm
-- ============================================================================
-- Mostra quais modulos tem campos custom adicionados pelo admin.

SELECT
    REPLACE(t.TABLE_NAME, '_cstm', '') AS modulo_base,
    t.TABLE_NAME                       AS tabela_cstm,
    t.TABLE_ROWS                       AS registros
FROM information_schema.TABLES t
WHERE t.TABLE_SCHEMA = 'suitecrm'        -- TROQUE
  AND RIGHT(t.TABLE_NAME, 5) = '_cstm'
ORDER BY t.TABLE_NAME;


-- ============================================================================
-- QUERY 4 - Sample (3 linhas) de uma tabela
-- ============================================================================
-- CUIDADO se a tabela tiver dados sensiveis (CPF etc).

SELECT * FROM suitecrm.NOME_DA_TABELA LIMIT 3;
-- TROQUE ambos


-- ============================================================================
-- QUERY 5 - Contagem real (cuidado: lenta em tabelas grandes)
-- ============================================================================

SELECT COUNT(*) AS registros_reais FROM suitecrm.NOME_DA_TABELA;
-- TROQUE ambos
