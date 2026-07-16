-- ============================================================================
-- 15_protocolo_sem_unique.sql
--
-- Remove a restrição UNIQUE de bss.processo_beneficio.protocolo, trocando por
-- índice não-único.
--
-- POR QUÊ
-- -------
-- O protocolo vem de `cases.name` no legado (o SuiteCRM reaproveitou o campo
-- "Assunto" pra guardar o número que o cliente conhece). E `cases.name` TEM
-- DUPLICATAS — o sync quebrou com:
--     UniqueViolation: duplicate key value violates unique constraint
--     "uq_processo_protocolo"  DETAIL: Key (protocolo)=(260420827) already exists
--
-- Faz sentido: "Assunto" é campo de texto livre no SuiteCRM, sem constraint do
-- outro lado. Nada impedia dois cases de receberem o mesmo número.
--
-- PRECEDENTE NO PRÓPRIO PROJETO — a mesma decisão já foi tomada duas vezes:
--   trabalhador.cpf : "CPF deveria ser único, mas legado da GNB tem dupes.
--                      Manter como índice (não-único) e limpar depois da migração."
--   empresa.cnpj    : "CNPJ NÃO é UNIQUE: legado tem dupes (cadastros
--                      duplicados, filiais com mesmo CNPJ). Limpar manualmente
--                      depois e adicionar UNIQUE quando data estiver consistente."
--
-- Protocolo entra na mesma fila: espelhamos a realidade do legado, não
-- inventamos desempate. Quem limpa duplicata é a BSS, na origem. Quando o dado
-- estiver consistente, a UNIQUE volta.
--
-- NOTA SOBRE DRIFT DE SCHEMA
-- --------------------------
-- A constraint `uq_processo_protocolo` NÃO existe em nenhum script versionado.
-- O 01_schema_inicial.sql declara `protocolo VARCHAR(9) UNIQUE`, que o Postgres
-- nomearia `processo_beneficio_protocolo_key`. Alguém criou/renomeou direto no
-- banco. Por isso o DO block abaixo DESCOBRE a constraint em vez de assumir o
-- nome — e derruba qualquer unique que exista sobre a coluna.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Derruba qualquer UNIQUE (constraint ou índice) sobre protocolo
-- ----------------------------------------------------------------------------
DO $$
DECLARE
    r RECORD;
BEGIN
    -- Constraints UNIQUE que cobrem exatamente a coluna protocolo
    FOR r IN
        SELECT con.conname
          FROM pg_constraint con
          JOIN pg_class      rel ON rel.oid = con.conrelid
          JOIN pg_namespace  nsp ON nsp.oid = rel.relnamespace
         WHERE nsp.nspname = 'bss'
           AND rel.relname = 'processo_beneficio'
           AND con.contype = 'u'
           AND con.conkey = ARRAY[(
                 SELECT attnum FROM pg_attribute
                  WHERE attrelid = rel.oid AND attname = 'protocolo'
               )]::smallint[]
    LOOP
        EXECUTE format('ALTER TABLE bss.processo_beneficio DROP CONSTRAINT %I', r.conname);
        RAISE NOTICE 'constraint UNIQUE removida: %', r.conname;
    END LOOP;

    -- Índices UNIQUE avulsos (criados sem constraint) sobre a coluna
    FOR r IN
        SELECT i.relname AS idxname
          FROM pg_index     x
          JOIN pg_class     i ON i.oid = x.indexrelid
          JOIN pg_class     t ON t.oid = x.indrelid
          JOIN pg_namespace n ON n.oid = t.relnamespace
         WHERE n.nspname = 'bss'
           AND t.relname = 'processo_beneficio'
           AND x.indisunique
           AND NOT x.indisprimary
           AND pg_get_indexdef(x.indexrelid) LIKE '%(protocolo)%'
    LOOP
        EXECUTE format('DROP INDEX IF EXISTS bss.%I', r.idxname);
        RAISE NOTICE 'indice UNIQUE removido: %', r.idxname;
    END LOOP;
END $$;


-- ----------------------------------------------------------------------------
-- 2. Índice não-único: buscar por protocolo continua rápido
-- ----------------------------------------------------------------------------
-- É o número que o cliente usa pra falar do caso — busca por ele será comum.
CREATE INDEX IF NOT EXISTS idx_processo_protocolo
    ON bss.processo_beneficio (protocolo)
 WHERE protocolo IS NOT NULL;


-- ----------------------------------------------------------------------------
-- 3. Diagnóstico das duplicatas (roda de novo DEPOIS do sync pra ver o total)
-- ----------------------------------------------------------------------------
DO $$
DECLARE
    dups      BIGINT;
    afetados  BIGINT;
BEGIN
    SELECT COUNT(*), COALESCE(SUM(n), 0) INTO dups, afetados
      FROM (
        SELECT protocolo, COUNT(*) AS n
          FROM bss.processo_beneficio
         WHERE protocolo IS NOT NULL
         GROUP BY protocolo
        HAVING COUNT(*) > 1
      ) x;
    RAISE NOTICE 'protocolos duplicados: % (afetando % processos)', dups, afetados;
    IF dups > 0 THEN
        RAISE NOTICE 'Listar com: SELECT protocolo, COUNT(*), array_agg(id) '
                     'FROM bss.processo_beneficio WHERE protocolo IS NOT NULL '
                     'GROUP BY protocolo HAVING COUNT(*) > 1 ORDER BY 2 DESC;';
    END IF;
END $$;
