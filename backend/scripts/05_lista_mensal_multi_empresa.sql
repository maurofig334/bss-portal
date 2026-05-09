-- ============================================================================
-- 05_lista_mensal_multi_empresa.sql
--
-- Libera multi-vínculo: trabalhador pode estar ATIVO em N empresas no mesmo
-- mês de referência (ex: trabalhador que tem 2 contratos CLT). Antes a regra
-- era "só pode estar em 1 empresa por mês", confirmada com cliente em
-- 2026-05-04, mas REVISTA em 2026-05-09: agora é multi-vínculo.
--
-- Mudança:
--   ANTES:  UNIQUE (id_trabalhador, mes_referencia)
--   AGORA:  UNIQUE (id_trabalhador, mes_referencia, id_empresa)
--
-- Algoritmo de desativação automática (rodado pela importação de planilha)
-- agora opera POR (CNPJ × mes_referencia): só "fecha" o vínculo do CNPJ que
-- subiu a planilha; vínculos em outros CNPJs ficam intactos.
--
-- Idempotente — pode rodar várias vezes.
-- ============================================================================

BEGIN;

-- 1) Drop a UNIQUE antiga (id_trabalhador, mes_referencia) — busca pelo nome real
DO $$
DECLARE
    nome_constraint TEXT;
BEGIN
    SELECT conname INTO nome_constraint
      FROM pg_constraint
     WHERE conrelid = 'bss.lista_mensal_item'::regclass
       AND contype = 'u'
       AND pg_get_constraintdef(oid) ~ '\(id_trabalhador, mes_referencia\)';
    IF nome_constraint IS NOT NULL THEN
        EXECUTE 'ALTER TABLE bss.lista_mensal_item DROP CONSTRAINT '
                || quote_ident(nome_constraint);
        RAISE NOTICE 'Removido UNIQUE antigo: %', nome_constraint;
    ELSE
        RAISE NOTICE 'UNIQUE antigo (trab,mes) não encontrado — talvez já removido.';
    END IF;
END $$;

-- 2) Adiciona a UNIQUE nova (trab, mes, empresa) se não existir
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'bss.lista_mensal_item'::regclass
           AND contype = 'u'
           AND pg_get_constraintdef(oid) ~ '\(id_trabalhador, mes_referencia, id_empresa\)'
    ) THEN
        ALTER TABLE bss.lista_mensal_item
            ADD CONSTRAINT uq_lmi_trab_mes_empresa
            UNIQUE (id_trabalhador, mes_referencia, id_empresa);
        RAISE NOTICE 'UNIQUE (trab, mes, empresa) adicionado.';
    ELSE
        RAISE NOTICE 'UNIQUE (trab, mes, empresa) já existe — pulando.';
    END IF;
END $$;

COMMIT;

-- Pós-validação:
--   \d bss.lista_mensal_item
--   -- Deve mostrar: UNIQUE (id_trabalhador, mes_referencia, id_empresa)
