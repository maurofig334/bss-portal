-- ============================================================================
-- 03_param_sindicato_unique.sql
--   Ajusta constraints de bss.parametros_boleto pra refletir o modelo real:
--
--   No legado (SuiteCRM), 1 cbr_parametros_boleto pode ser apontado por N
--   sindicatos (compartilhamento por organização/segmento). No BSS, optamos
--   por manter 1:1 (cada sindicato com sua linha) pra permitir overrides
--   pontuais (banco diferente, tarifa especial em um caso).
--
--   Consequência:
--     - id_legado_uuid pode aparecer N vezes (não pode ser UNIQUE)
--     - id_sindicato é UNIQUE (1:1)
--
--   bss.valor_beneficio_sindicato JÁ tem UNIQUE (id_sindicato, id_tipo_beneficio)
--   no schema inicial — não precisa mexer aqui.
--
-- IDEMPOTENTE: usa IF EXISTS / IF NOT EXISTS / DO blocks.
-- ============================================================================

BEGIN;

-- ──────────────────────────────────────────────────────────────────────────
-- 1) Remove UNIQUE de id_legado_uuid (se existir) e mantém só índice
-- ──────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    nome_constraint TEXT;
BEGIN
    SELECT conname INTO nome_constraint
      FROM pg_constraint
     WHERE conrelid = 'bss.parametros_boleto'::regclass
       AND contype = 'u'
       AND pg_get_constraintdef(oid) LIKE '%(id_legado_uuid)%';
    IF nome_constraint IS NOT NULL THEN
        EXECUTE 'ALTER TABLE bss.parametros_boleto DROP CONSTRAINT ' || quote_ident(nome_constraint);
        RAISE NOTICE 'Removido UNIQUE em id_legado_uuid: %', nome_constraint;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_param_boleto_legado
    ON bss.parametros_boleto (id_legado_uuid)
    WHERE id_legado_uuid IS NOT NULL;

-- ──────────────────────────────────────────────────────────────────────────
-- 2) Garante UNIQUE em id_sindicato (1:1 BSS)
-- ──────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'bss.parametros_boleto'::regclass
           AND contype = 'u'
           AND pg_get_constraintdef(oid) LIKE '%(id_sindicato)%'
    ) THEN
        ALTER TABLE bss.parametros_boleto
            ADD CONSTRAINT uq_parametros_boleto_sindicato UNIQUE (id_sindicato);
        RAISE NOTICE 'UNIQUE em id_sindicato adicionado.';
    END IF;
END $$;

-- ──────────────────────────────────────────────────────────────────────────
-- 3) Sanidade: tarifa_titular era NOT NULL no schema inicial. Como o sync
--    pode receber NULL do legado (tarifa_c não preenchida), relaxamos pra
--    aceitar NULL — quem não tem tarifa cadastrada fica em branco até admin
--    revisar. Default 0 seria pior (mascararia falta de dado).
-- ──────────────────────────────────────────────────────────────────────────
ALTER TABLE bss.parametros_boleto
    ALTER COLUMN tarifa_titular DROP NOT NULL;

COMMIT;

-- Pós-validação:
--   \d bss.parametros_boleto
--   SELECT COUNT(*) FROM bss.parametros_boleto;  -- deve ser 0 antes do sync
