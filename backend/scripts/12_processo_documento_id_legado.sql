-- ============================================================================
-- 12_processo_documento_id_legado.sql
--
-- Adiciona id_legado_uuid em bss.processo_documento.
--
-- POR QUÊ: a tabela nasceu como nativa do BSS (documento anexado pelo portal
-- novo), mas com o sync de documentos ela passa a ESPELHAR o legado — cada
-- linha de `documents` (via documents_cases) vira uma linha aqui. A lição #2
-- do projeto é explícita: "id_legado_uuid em toda tabela espelhada — chave de
-- idempotência". Sem isso, o sync teria que se apoiar na UNIQUE
-- (id_processo, id_tipo_documento, versao), e `versao` é derivada de
-- ROW_NUMBER por data — se um documento for apagado no legado, a numeração
-- desliza e o sync atualizaria a linha errada.
--
-- Com id_legado_uuid: ON CONFLICT (id_legado_uuid) DO UPDATE, igual aos
-- outros syncs (ver app/sync/processo_mensagem.py).
--
-- NULLABLE: documentos criados no BSS (pós Big Bang) não têm origem no legado.
--
-- IDEMPOTENTE: IF NOT EXISTS nos dois passos.
-- ============================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema = 'bss'
           AND table_name   = 'processo_documento'
           AND column_name  = 'id_legado_uuid'
    ) THEN
        ALTER TABLE bss.processo_documento ADD COLUMN id_legado_uuid CHAR(36);
        RAISE NOTICE 'coluna id_legado_uuid adicionada';
    ELSE
        RAISE NOTICE 'coluna id_legado_uuid ja existe — nada a fazer';
    END IF;
END $$;

-- UNIQUE simples (NÃO parcial).
--
-- ATENÇÃO — armadilha que já custou um sync quebrado: um índice PARCIAL
-- (WHERE id_legado_uuid IS NOT NULL) NÃO é inferido por
-- `ON CONFLICT (id_legado_uuid) DO UPDATE` — o Postgres exige que a cláusula
-- repita o predicado do índice, senão devolve:
--     InvalidColumnReference: there is no unique or exclusion constraint
--     matching the ON CONFLICT specification
--
-- E o parcial nem era necessário: no Postgres, UNIQUE comum permite MÚLTIPLOS
-- NULLs (nulos não conflitam entre si). Logo as linhas nativas do BSS, que
-- ficam com id_legado_uuid NULL, convivem sem problema — exatamente como já
-- acontece em bss.documento (id_legado_uuid CHAR(36) UNIQUE).
DROP INDEX IF EXISTS bss.uq_pdoc_legado_uuid;
CREATE UNIQUE INDEX IF NOT EXISTS uq_pdoc_legado_uuid
    ON bss.processo_documento (id_legado_uuid);


-- ----------------------------------------------------------------------------
-- Mesmo raciocínio pra bss.documento: ela JÁ tem id_legado_uuid UNIQUE
-- (declarado no 01_schema_inicial.sql), então nada a fazer lá.
-- ----------------------------------------------------------------------------

-- Conferência:
--   SELECT column_name, data_type, is_nullable
--     FROM information_schema.columns
--    WHERE table_schema='bss' AND table_name='processo_documento'
--    ORDER BY ordinal_position;
