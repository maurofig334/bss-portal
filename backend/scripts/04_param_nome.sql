-- ============================================================================
-- 04_param_nome.sql
--   Adiciona coluna 'nome' em bss.parametros_boleto pra preservar o nome do
--   parâmetro do legado (cbr_parametros_boleto.name). Esse nome é importante
--   porque é o que identifica o parâmetro pra usuários (ex: "FEMACO - ASSEIO
--   E CONSERV.", "SETH SJRP - ACORDOS EM GRUPO I") — e nem sempre coincide
--   com o nome do sindicato.
--
--   Idempotente — pode rodar várias vezes.
-- ============================================================================

BEGIN;

ALTER TABLE bss.parametros_boleto
    ADD COLUMN IF NOT EXISTS nome VARCHAR(255);

COMMIT;
