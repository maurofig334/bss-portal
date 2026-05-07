-- ============================================================================
-- 02_legado_dropdown.sql
--   1) Estende bss.tipo_beneficio com mapeamento pro dropdown legado
--      (tipodebeneficio_list do SuiteCRM)
--   2) Corrige bug histórico AC/AD que afetou ~18k linhas em
--      bss.processo_beneficio (TIPO_BENEFICIO_MAP de processo.py estava
--      com AC e AD trocados em relação à fonte canônica do SuiteCRM)
--
-- IDEMPOTENTE: roda quantas vezes quiser, não duplica nem reverte os fixes.
--
-- Pré-requisito: schema 01 já aplicado e sync de processos já rodou.
-- ============================================================================

BEGIN;

-- ──────────────────────────────────────────────────────────────────────────
-- 1) Extensão do catálogo de tipo de benefício
-- ──────────────────────────────────────────────────────────────────────────
ALTER TABLE bss.tipo_beneficio
    ADD COLUMN IF NOT EXISTS codigo_legado CHAR(2),
    ADD COLUMN IF NOT EXISTS slot_legado   SMALLINT;

-- Backfill seguindo a ordem canônica de tipodebeneficio_list no Dropdown
-- Editor do SuiteCRM. ATENÇÃO: AC=Acionamento Funeral e AD=Acidente — esta
-- é a ordem oficial. processo.py tinha o mapeamento invertido.
UPDATE bss.tipo_beneficio SET codigo_legado='AC', slot_legado= 1 WHERE codigo='acionamento_funeral';
UPDATE bss.tipo_beneficio SET codigo_legado='AU', slot_legado= 2 WHERE codigo='auxilio_creche';
UPDATE bss.tipo_beneficio SET codigo_legado='NA', slot_legado= 3 WHERE codigo='natalidade';
UPDATE bss.tipo_beneficio SET codigo_legado='AD', slot_legado= 4 WHERE codigo='acidente';
UPDATE bss.tipo_beneficio SET codigo_legado='IN', slot_legado= 5 WHERE codigo='incapacitacao';
UPDATE bss.tipo_beneficio SET codigo_legado='FA', slot_legado= 6 WHERE codigo='falecimento';
UPDATE bss.tipo_beneficio SET codigo_legado='RE', slot_legado= 7 WHERE codigo='reembolso_rescisao';
UPDATE bss.tipo_beneficio SET codigo_legado='CM', slot_legado= 8 WHERE codigo='consulta_medica';
UPDATE bss.tipo_beneficio SET codigo_legado='EX', slot_legado= 9 WHERE codigo='exame';
UPDATE bss.tipo_beneficio SET codigo_legado='BS', slot_legado=10 WHERE codigo='brinde_sindicato';

-- Sanidade: todas as 10 linhas precisam estar mapeadas antes das constraints
DO $$
DECLARE
    n_pendente INT;
BEGIN
    SELECT COUNT(*) INTO n_pendente FROM bss.tipo_beneficio
     WHERE codigo_legado IS NULL OR slot_legado IS NULL;
    IF n_pendente > 0 THEN
        RAISE EXCEPTION 'Backfill incompleto: % tipo(s) ainda sem codigo_legado/slot_legado', n_pendente;
    END IF;
END $$;

-- Constraints de unicidade (idempotente — drop+create se já existir)
ALTER TABLE bss.tipo_beneficio DROP CONSTRAINT IF EXISTS uq_tipo_beneficio_codigo_legado;
ALTER TABLE bss.tipo_beneficio DROP CONSTRAINT IF EXISTS uq_tipo_beneficio_slot_legado;
ALTER TABLE bss.tipo_beneficio
    ADD CONSTRAINT uq_tipo_beneficio_codigo_legado UNIQUE (codigo_legado),
    ADD CONSTRAINT uq_tipo_beneficio_slot_legado   UNIQUE (slot_legado);


-- ──────────────────────────────────────────────────────────────────────────
-- 2) Correção AC ↔ AD nos processos já sincronizados
-- ──────────────────────────────────────────────────────────────────────────
-- Bug original (processo.py TIPO_BENEFICIO_MAP):
--   "AC": "acidente"            ← errado, deveria ser "acionamento_funeral"
--   "AD": "acionamento_funeral" ← errado, deveria ser "acidente"
-- Resultado: processos AC e AD do legado foram migrados pro tipo errado em BSS.
-- Fix: trocar id_tipo_beneficio onde aponta pra "acidente" e "acionamento_funeral".
--
-- Salvaguarda: só roda o swap se o flag ainda não foi marcado (idempotência).
DO $$
DECLARE
    id_acidente   SMALLINT;
    id_funeral    SMALLINT;
    n_swap        INT;
    ja_corrigido  BOOLEAN;
BEGIN
    -- Marca de "já corrigi" via tabela auxiliar simples (cria se não existir).
    CREATE TABLE IF NOT EXISTS bss._migration_flag (
        nome   TEXT PRIMARY KEY,
        em     TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    SELECT EXISTS (SELECT 1 FROM bss._migration_flag WHERE nome = 'fix_ac_ad_processo')
      INTO ja_corrigido;
    IF ja_corrigido THEN
        RAISE NOTICE 'Fix AC/AD já aplicado anteriormente — pulando swap.';
        RETURN;
    END IF;

    SELECT id INTO id_acidente FROM bss.tipo_beneficio WHERE codigo='acidente';
    SELECT id INTO id_funeral  FROM bss.tipo_beneficio WHERE codigo='acionamento_funeral';

    -- Swap em uma só passada — Postgres avalia SET contra o snapshot pré-update.
    UPDATE bss.processo_beneficio
       SET id_tipo_beneficio = CASE id_tipo_beneficio
           WHEN id_acidente THEN id_funeral
           WHEN id_funeral  THEN id_acidente
       END
     WHERE id_tipo_beneficio IN (id_acidente, id_funeral);

    GET DIAGNOSTICS n_swap = ROW_COUNT;
    RAISE NOTICE 'Swap AC↔AD aplicado em % processos.', n_swap;

    INSERT INTO bss._migration_flag (nome) VALUES ('fix_ac_ad_processo');
END $$;

COMMIT;

-- Pós-validação (rodar manualmente pra inspecionar):
--   SELECT codigo, codigo_legado, slot_legado, ordem
--     FROM bss.tipo_beneficio ORDER BY slot_legado;
--
--   SELECT tb.codigo, COUNT(*) AS qtd
--     FROM bss.processo_beneficio p
--     JOIN bss.tipo_beneficio tb ON tb.id = p.id_tipo_beneficio
--    GROUP BY tb.codigo ORDER BY qtd DESC;
