-- ============================================================================
-- 06_boleto_emissao.sql
--
-- Ajustes em bss.boleto pra emissão pelo BSS (épico #21).
--
-- 1) Sequence pra gerar nosso_numero único, começando em 100.000.000 (9 dígitos)
--    — bem acima dos valores legados (max real ~60M; sentinela 99999999999).
-- 2) Coluna id_boleto_substituido (auto-FK) — rastreia "este boleto é a 2ª via
--    de qual outro?" Usado quando reemitimos: o velho fica 'cancelado', o novo
--    aponta pra ele.
-- 3) Coluna motivo_cancelamento (texto livre) — preenchida no cancelamento.
-- 4) Índice composto (id_empresa, id_sindicato, mes_referencia) parcial
--    em status vivos — pra checagem O(1) de duplicata na emissão.
--
-- Convenções confirmadas com cliente em 2026-05-09:
--   - mes_referencia no DB = mês de AMPARO (= mês do vencimento)
--   - COMPETÊNCIA é derivada: mes_amparo - 1 mês (não vai pro DB)
--   - status default 'gerado' → renderizado como "Aberto" na UI
--   - 'pendente' = legado de 2 anos atrás (5414 boletos) — ao reemitir, vira
--     'cancelado' com substituto novo em 'gerado'
--
-- Idempotente — pode rodar várias vezes.
-- ============================================================================

BEGIN;

-- 1) Sequence pra nosso_numero
CREATE SEQUENCE IF NOT EXISTS bss.seq_boleto_nosso_numero
    START WITH 100000000
    INCREMENT BY 1
    MINVALUE 100000000
    NO CYCLE;

-- 2) id_boleto_substituido (auto-FK pra rastrear reemissão)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema='bss' AND table_name='boleto'
           AND column_name='id_boleto_substituido'
    ) THEN
        ALTER TABLE bss.boleto
          ADD COLUMN id_boleto_substituido BIGINT
            REFERENCES bss.boleto(id) ON DELETE SET NULL;
        RAISE NOTICE 'Coluna id_boleto_substituido adicionada.';
    ELSE
        RAISE NOTICE 'Coluna id_boleto_substituido já existe — pulando.';
    END IF;
END $$;

-- 3) motivo_cancelamento
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema='bss' AND table_name='boleto'
           AND column_name='motivo_cancelamento'
    ) THEN
        ALTER TABLE bss.boleto ADD COLUMN motivo_cancelamento TEXT;
        RAISE NOTICE 'Coluna motivo_cancelamento adicionada.';
    ELSE
        RAISE NOTICE 'Coluna motivo_cancelamento já existe — pulando.';
    END IF;
END $$;

-- 4) Índice parcial pra checagem de duplicata na emissão
--    "já existe boleto vivo (não-cancelado) pra esse cnpj × sindicato × mes_amparo?"
CREATE INDEX IF NOT EXISTS idx_boleto_uniq_emissao
    ON bss.boleto (id_empresa, id_sindicato, mes_referencia)
    WHERE status IN ('gerado','vencido','pendente');

COMMIT;

-- Pós-validação:
--   \d bss.boleto
--   SELECT nextval('bss.seq_boleto_nosso_numero');  -- deve retornar 100000000
--   -- (rebobina pra não consumir o número de teste:)
--   SELECT setval('bss.seq_boleto_nosso_numero', 100000000, FALSE);
