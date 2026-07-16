-- ============================================================================
-- 16_empresa_autocadastro.sql
--
-- Campos que bss.empresa passa a precisar quando nasce de um CADASTRO
-- (autocadastro pelo portal) e não do sync do legado.
--
-- Ver docs/AUTOCADASTRO.md pro fluxo completo. Resumo:
--   CNPJ novo → consulta RFB → cria empresa com os dados da Receita
--               (usuário NÃO edita) → contato vira gestor → analista aprova
--
-- ----------------------------------------------------------------------------
-- POR QUE ESTES CAMPOS
-- ----------------------------------------------------------------------------
-- `email`   — a empresa HOJE não tem e-mail nenhum. Nenhum. O autocadastro é
--             movido a e-mail, e a tela de detalhe já mostra "—" nesse campo
--             porque ele não existe. Vem da RFB.
-- `tipo_cadastro` — o legado distingue cadastro interno de autocadastro; o
--             trabalhador já tem o equivalente ("VIA UPLOAD"), a empresa não.
-- RFB       — situação cadastral e CNAE são a base pra aceitar ou reprovar o
--             cadastro (a doc antiga previa reprovar CNAE não atendido).
-- `status_cadastro` — NÃO confundir com `status` (ativa/suspensa/cancelada),
--             que é a situação OPERACIONAL da empresa no BSS. Este aqui é o
--             estado do CADASTRO: pendente → aprovado/reprovado.
--
-- IDEMPOTENTE: ADD COLUMN IF NOT EXISTS.
-- ============================================================================

ALTER TABLE bss.empresa
    -- Contato (RFB e cobrança) -----------------------------------------------
    ADD COLUMN IF NOT EXISTS email            VARCHAR(150),
    ADD COLUMN IF NOT EXISTS email_cobranca   VARCHAR(150),

    -- Origem do cadastro -----------------------------------------------------
    -- 'interno' = cadastrada pela equipe GNB (inclui tudo que veio do sync)
    -- 'auto'    = autocadastro pelo portal
    ADD COLUMN IF NOT EXISTS tipo_cadastro    VARCHAR(20) NOT NULL DEFAULT 'interno',

    -- Estado do CADASTRO (≠ status operacional) ------------------------------
    -- 'aprovado' de default: tudo que já existe veio do legado e está valendo.
    -- Só o autocadastro cria linha 'pendente'.
    ADD COLUMN IF NOT EXISTS status_cadastro  VARCHAR(20) NOT NULL DEFAULT 'aprovado',
    ADD COLUMN IF NOT EXISTS motivo_reprovacao TEXT,

    -- Dados da Receita Federal -----------------------------------------------
    ADD COLUMN IF NOT EXISTS situacao_cadastral      VARCHAR(50),  -- ATIVA, BAIXADA, SUSPENSA...
    ADD COLUMN IF NOT EXISTS data_situacao_cadastral DATE,
    ADD COLUMN IF NOT EXISTS cnae_principal          VARCHAR(10),
    ADD COLUMN IF NOT EXISTS cnae_descricao          VARCHAR(255),
    -- Quando a RFB foi consultada. A situação cadastral MUDA (empresa é baixada,
    -- suspensa) — sem isto não dá pra saber se o dado está velho.
    ADD COLUMN IF NOT EXISTS rfb_consultado_em       TIMESTAMPTZ;


-- Fila de aprovação de empresa: filtro mais usado da tela interna
CREATE INDEX IF NOT EXISTS idx_empresa_status_cadastro
    ON bss.empresa (status_cadastro)
 WHERE status_cadastro <> 'aprovado';

-- Busca por e-mail (autocadastro procura contato por e-mail)
CREATE INDEX IF NOT EXISTS idx_empresa_email
    ON bss.empresa (lower(email))
 WHERE email IS NOT NULL;


COMMENT ON COLUMN bss.empresa.tipo_cadastro IS
    'interno = cadastrada pela GNB (inclui todo o legado sincronizado); auto = autocadastro pelo portal';
COMMENT ON COLUMN bss.empresa.status_cadastro IS
    'Estado do CADASTRO: pendente/aprovado/reprovado. NAO confundir com status (ativa/suspensa/cancelada), que e a situacao operacional';
COMMENT ON COLUMN bss.empresa.rfb_consultado_em IS
    'Quando os dados da Receita foram buscados. Situacao cadastral muda com o tempo — usar pra decidir reconsulta';


DO $$
DECLARE
    total BIGINT;
BEGIN
    SELECT COUNT(*) INTO total FROM bss.empresa;
    RAISE NOTICE 'bss.empresa: % linhas, todas marcadas tipo_cadastro=interno / status_cadastro=aprovado', total;
    RAISE NOTICE 'Correto: tudo que existe hoje veio do legado. Só o autocadastro cria pendente.';
END $$;
