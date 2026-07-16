-- ============================================================================
-- 19_empresa_cnpj_nullable.sql
--
-- Remove o NOT NULL de bss.empresa.cnpj — que NUNCA deveria ter existido.
--
-- ----------------------------------------------------------------------------
-- O QUE ESTAVA ACONTECENDO (grave — leia inteiro)
-- ----------------------------------------------------------------------------
-- O cron das 03:00 (`sync_legado --tabela todas`) MORRIA todas as noites no
-- sync de empresa:
--
--     psycopg.errors.NotNullViolation: null value in column "cnpj" of
--     relation "empresa" violates not-null constraint
--     DETAIL: Failing row contains (..., ACK SERVICO EMPRESARIAL EIRELI, null, ...)
--
-- E `--tabela todas` roda em ORDEM:
--     sindicato → EMPRESA → trabalhador → boleto → boleto_item → processo
--                    ✗ morre aqui, nada depois roda
--
-- Consequência: por semanas, SÓ o sindicato sincronizou. Descoberto em
-- 01/07/2026 porque o BSS estava com 44.704 trabalhadores a menos que o
-- legado, e processos novos apareciam sem trabalhador nas telas.
--
-- A falha era BARULHENTA (traceback no log todas as noites) — mas ninguém
-- lia o log. Falha que ninguém vê é igual a falha silenciosa.
--
-- ----------------------------------------------------------------------------
-- POR QUE NULLABLE É O CERTO
-- ----------------------------------------------------------------------------
-- O schema canônico SEMPRE disse que cnpj é opcional (01_schema_inicial.sql:196):
--
--     -- CNPJ NÃO é UNIQUE: legado tem dupes (cadastros duplicados, filiais
--     -- com mesmo CNPJ). Limpar manualmente depois e adicionar UNIQUE quando
--     -- data estiver consistente.
--     cnpj VARCHAR(14),        ← sem NOT NULL
--
-- O NOT NULL foi adicionado DIRETO NO BANCO, fora de qualquer migration
-- versionada — mesmo padrão do `uq_processo_protocolo`, que também não existe
-- em script nenhum. O banco divergiu do schema canônico, e a divergência
-- derrubou o sync.
--
-- E o legado TEM empresa sem CNPJ. Espelhar isso é o comportamento correto do
-- projeto: trazemos o dado como ele é e a BSS limpa na origem. Uma empresa sem
-- CNPJ é quase inútil pro BSS (o match de boleto e trabalhador é por CNPJ),
-- mas descartá-la em silêncio seria pior — a gente perde o registro e ninguém
-- fica sabendo.
--
-- IDEMPOTENTE: DROP NOT NULL é no-op se já estiver nullable.
-- ============================================================================

ALTER TABLE bss.empresa ALTER COLUMN cnpj DROP NOT NULL;


-- Índice pra achar as empresas sem CNPJ (devem ser poucas — vale a BSS limpar)
CREATE INDEX IF NOT EXISTS idx_empresa_sem_cnpj
    ON bss.empresa (id)
 WHERE cnpj IS NULL;


DO $$
DECLARE
    nulos    BIGINT;
    nullable TEXT;
BEGIN
    SELECT is_nullable INTO nullable
      FROM information_schema.columns
     WHERE table_schema = 'bss' AND table_name = 'empresa' AND column_name = 'cnpj';
    SELECT COUNT(*) INTO nulos FROM bss.empresa WHERE cnpj IS NULL;

    RAISE NOTICE 'bss.empresa.cnpj agora é nullable=%  ·  empresas sem CNPJ hoje: %',
                 nullable, nulos;
    RAISE NOTICE 'Proximo: rodar o sync completo e conferir o cron das 03:00.';
    RAISE NOTICE 'Listar as sem CNPJ: SELECT id, razao_social, id_legado_uuid '
                 'FROM bss.empresa WHERE cnpj IS NULL;';
END $$;
