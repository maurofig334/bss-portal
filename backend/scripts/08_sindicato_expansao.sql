-- ============================================================================
-- 08_sindicato_expansao.sql
--
-- Expande bss.sindicato com campos descobertos no legado SuiteCRM em
-- 2026-05-11 (épico/task #17). Os nomes das colunas do legado estão em
-- comentários ao lado pra rastreabilidade.
--
-- Mapeamento legado → BSS:
--   sindi_sindicatos.sindi_sindicatos_type → tipo_sindicato (ex: 'FEMACO')
--   sindi_sindicatos.phone_office          → telefone
--   sindi_sindicatos.phone_alternate       → outro_telefone
--   sindi_sindicatos.phone_fax             → fax
--   sindi_sindicatos.website               → website
--   sindi_sindicatos.description           → descricao
--   sindi_sindicatos.shipping_address_*    → endereco_*
--   sindi_sindicatos_cstm.patronaleempresa_c → patronal_empresa
--   sindi_sindicatos_cstm.contact_id_c → contato_principal (via contacts.name)
--   email_addr_bean_rel + email_addresses  → email
--
-- Idempotente (DO blocks com IF NOT EXISTS).
-- ============================================================================

BEGIN;

DO $$
BEGIN
    -- Tipo de sindicato (FEMACO, NAO FEMACO, etc — valor livre por enquanto)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema='bss' AND table_name='sindicato'
                      AND column_name='tipo_sindicato') THEN
        ALTER TABLE bss.sindicato ADD COLUMN tipo_sindicato VARCHAR(50);
        RAISE NOTICE 'tipo_sindicato adicionada';
    END IF;

    -- Telefones
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema='bss' AND table_name='sindicato'
                      AND column_name='telefone') THEN
        ALTER TABLE bss.sindicato ADD COLUMN telefone VARCHAR(100);
        RAISE NOTICE 'telefone adicionada';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema='bss' AND table_name='sindicato'
                      AND column_name='outro_telefone') THEN
        ALTER TABLE bss.sindicato ADD COLUMN outro_telefone VARCHAR(100);
        RAISE NOTICE 'outro_telefone adicionada';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema='bss' AND table_name='sindicato'
                      AND column_name='fax') THEN
        ALTER TABLE bss.sindicato ADD COLUMN fax VARCHAR(100);
        RAISE NOTICE 'fax adicionada';
    END IF;

    -- Contato e e-mail
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema='bss' AND table_name='sindicato'
                      AND column_name='email') THEN
        ALTER TABLE bss.sindicato ADD COLUMN email VARCHAR(255);
        RAISE NOTICE 'email adicionada';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema='bss' AND table_name='sindicato'
                      AND column_name='contato_principal') THEN
        ALTER TABLE bss.sindicato ADD COLUMN contato_principal VARCHAR(255);
        RAISE NOTICE 'contato_principal adicionada';
    END IF;

    -- Patronal/Empresa (texto livre, conforme cliente em 2026-05-08)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema='bss' AND table_name='sindicato'
                      AND column_name='patronal_empresa') THEN
        ALTER TABLE bss.sindicato ADD COLUMN patronal_empresa VARCHAR(255);
        RAISE NOTICE 'patronal_empresa adicionada';
    END IF;

    -- Website e descrição livre
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema='bss' AND table_name='sindicato'
                      AND column_name='website') THEN
        ALTER TABLE bss.sindicato ADD COLUMN website VARCHAR(255);
        RAISE NOTICE 'website adicionada';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema='bss' AND table_name='sindicato'
                      AND column_name='descricao') THEN
        ALTER TABLE bss.sindicato ADD COLUMN descricao TEXT;
        RAISE NOTICE 'descricao adicionada';
    END IF;

    -- Endereço (aba "Informações para Entrega" no legado — vem de shipping_address_*)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema='bss' AND table_name='sindicato'
                      AND column_name='endereco_logradouro') THEN
        ALTER TABLE bss.sindicato ADD COLUMN endereco_logradouro VARCHAR(255);
        ALTER TABLE bss.sindicato ADD COLUMN endereco_cidade     VARCHAR(100);
        ALTER TABLE bss.sindicato ADD COLUMN endereco_uf         VARCHAR(2);
        ALTER TABLE bss.sindicato ADD COLUMN endereco_cep        VARCHAR(10);
        ALTER TABLE bss.sindicato ADD COLUMN endereco_pais       VARCHAR(50);
        RAISE NOTICE 'endereco_* (5 colunas) adicionadas';
    END IF;
END $$;

COMMIT;

-- Pós-validação:
--   \d bss.sindicato
--   -- Deve mostrar as novas colunas no fim
