-- ============================================================================
-- 22_pagamento_id_legado.sql — prepara bss.pagamento pro sync do contas a pagar
-- ============================================================================
--
-- A tabela bss.pagamento existe desde o schema inicial, mas nunca foi
-- sincronizada — está VAZIA. Antes de escrever o sync, dois ajustes:
--
-- 1. id_legado_uuid — a chave de idempotência. O sync usa ON CONFLICT nela.
--    O schema não tinha (tinha só numero_pagamento, que dependia de id_cpagar_c).
--
-- 2. numero_pagamento vira NULLABLE de fato / documentado como morto.
--    DESCOBERTA (22/07/2026): id_cpagar_c no legado é ZERO em todas as 10.554
--    linhas — o campo existe e nunca foi preenchido. O comentário do schema
--    ("numero_pagamento = id_cpagar_c sequencial") está errado, como o do
--    protocolo estava. A identidade real do pagamento é o UUID da base
--    pagar_contas_a_pagar, não esse número. numero_pagamento fica NULL.
--
-- Aplicar:
--     venv/bin/python -m scripts.aplicar_sql scripts/22_pagamento_id_legado.sql
-- ============================================================================

ALTER TABLE bss.pagamento
    ADD COLUMN IF NOT EXISTS id_legado_uuid CHAR(36);

-- UNIQUE pra o ON CONFLICT do sync funcionar. Parcial (WHERE NOT NULL) porque
-- pagamentos criados no BSS (pós-Big Bang) não terão uuid do legado, e
-- múltiplos NULL não podem colidir.
CREATE UNIQUE INDEX IF NOT EXISTS uq_pagamento_legado
    ON bss.pagamento (id_legado_uuid)
    WHERE id_legado_uuid IS NOT NULL;

COMMENT ON COLUMN bss.pagamento.numero_pagamento IS
    'MORTO no legado: id_cpagar_c é 0 em todas as linhas. Identidade real = id_legado_uuid.';
