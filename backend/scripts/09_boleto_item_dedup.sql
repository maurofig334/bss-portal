-- ============================================================================
-- 09_boleto_item_dedup.sql
--
-- Causa raiz: app/sync/boleto_item.py usava INSERT puro (sem ON CONFLICT).
-- Cada execução do sync diário duplicava as 4.9M linhas. Descoberto em
-- 2026-05-11 quando a tela de detalhe do boleto mostrou trabalhadores
-- triplicados.
--
-- Esta migration:
--   1. Limpa duplicações em bss.boleto_item (mantém o id menor de cada par)
--   2. Adiciona UNIQUE (id_boleto, id_trabalhador) pra prevenir no futuro
--
-- Depois disso, o app/sync/boleto_item.py também precisa ser ajustado pra
-- usar ON CONFLICT DO NOTHING (feito na mesma sessão).
--
-- Pode demorar 1-3 min pra rodar (varre 4.9M+ linhas).
-- Idempotente — se rodar de novo após dedup, vai apagar 0 linhas.
-- ============================================================================

BEGIN;

-- 0. Estatísticas ANTES:
DO $$
DECLARE
    total BIGINT;
    distintos BIGINT;
BEGIN
    SELECT COUNT(*), COUNT(DISTINCT (id_boleto, id_trabalhador))
      INTO total, distintos
      FROM bss.boleto_item;
    RAISE NOTICE 'ANTES: total=%, distintos=%, duplicacoes=%',
                 total, distintos, total - distintos;
END $$;

-- 1. Limpa duplicações: pra cada par (boleto, trabalhador), mantém o id menor.
--    USING + sub-query é mais rápido que WHERE id IN (SELECT...) em volumes grandes.
DELETE FROM bss.boleto_item bi1
 USING bss.boleto_item bi2
 WHERE bi1.id_boleto      = bi2.id_boleto
   AND bi1.id_trabalhador = bi2.id_trabalhador
   AND bi1.id             > bi2.id;

-- 2. Estatísticas DEPOIS da dedup:
DO $$
DECLARE
    total BIGINT;
BEGIN
    SELECT COUNT(*) INTO total FROM bss.boleto_item;
    RAISE NOTICE 'DEPOIS DEDUP: total=%', total;
END $$;

-- 3. Adiciona UNIQUE constraint pra prevenir no futuro:
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'bss.boleto_item'::regclass
           AND contype = 'u'
           AND pg_get_constraintdef(oid) ~ '\(id_boleto, id_trabalhador\)'
    ) THEN
        ALTER TABLE bss.boleto_item
            ADD CONSTRAINT uq_boleto_item_boleto_trab
            UNIQUE (id_boleto, id_trabalhador);
        RAISE NOTICE 'UNIQUE (id_boleto, id_trabalhador) adicionado.';
    ELSE
        RAISE NOTICE 'UNIQUE (id_boleto, id_trabalhador) ja existe — pulando.';
    END IF;
END $$;

COMMIT;
