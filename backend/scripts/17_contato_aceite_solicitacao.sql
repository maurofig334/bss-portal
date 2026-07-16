-- ============================================================================
-- 17_contato_aceite_solicitacao.sql
--
-- Sustenta o Autocadastro do lado do CONTATO (usuário externo):
--   1. tipo_cadastro em bss_users
--   2. bss.aceite_termo        — auditoria jurídica do aceite
--   3. bss.solicitacao_acesso  — a fila que o analista aprova (e o sininho lê)
--
-- Ver docs/AUTOCADASTRO.md. Regra confirmada com o Mauro (01/07/2026):
--   TODO contato novo é aprovado por um analista interno — nos dois ramos do
--   fluxo, sem exceção. Não há caminho que conceda acesso sem alguém olhar.
--
-- ----------------------------------------------------------------------------
-- O QUE JÁ EXISTIA E NÃO PRECISA DE NADA
-- ----------------------------------------------------------------------------
-- O "Contato" do legado É o bss_users com perfil='empresa'. Não é entidade
-- separada — o schema já dizia isso no comentário de bss_users.perfil:
--     'empresa' = cliente — opera N empresas via bss.usuario_empresa
-- E os campos que o formulário coleta já têm casa:
--     e-mail (login) → bss_users.email (UNIQUE)
--     nome           → bss_users.nome
--     telefone       → bss_users.telefone
--     senha          → bss_users.senha_hash
--     CNPJs          → bss.usuario_empresa (N:N)
--     pendente       → ativo = false
--
-- IDEMPOTENTE: IF NOT EXISTS em tudo.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Origem do cadastro do usuário
-- ----------------------------------------------------------------------------
ALTER TABLE bss_users
    ADD COLUMN IF NOT EXISTS tipo_cadastro VARCHAR(20) NOT NULL DEFAULT 'interno';

COMMENT ON COLUMN bss_users.tipo_cadastro IS
    'interno = criado pela equipe GNB; auto = veio do autocadastro do portal';


-- ----------------------------------------------------------------------------
-- 2. ACEITE DO TERMO — auditoria jurídica
-- ----------------------------------------------------------------------------
-- O termo fala em "responsabilidade civil e criminal". Um aceite que não
-- registra QUEM aceitou, QUANDO, DE ONDE e QUAL TEXTO tem valor frágil: se o
-- texto mudar, ninguém sabe o que a pessoa realmente aceitou.
--
-- Por isso guardamos o HASH do texto, não só a versão: prova qual redação
-- estava no ar naquele instante, mesmo que alguém edite o template depois.
--
-- O termo é POR CNPJ (a doc antiga já dizia: "termo de uso e de aceite /
-- responsabilidade por CNPJ") — um contato que administra 4 CNPJs aceita 4x.
CREATE TABLE IF NOT EXISTS bss.aceite_termo (
    id              BIGSERIAL PRIMARY KEY,
    id_usuario      INT    NOT NULL,                                  -- FK lógica → bss_users.id
    id_empresa      BIGINT NOT NULL REFERENCES bss.empresa(id) ON DELETE CASCADE,
    -- Identificação do texto aceito:
    versao          VARCHAR(20) NOT NULL,        -- ex.: '2026-07-v1'
    texto_hash      CHAR(64),                    -- SHA-256 do texto exibido
    -- Prova de origem:
    ip              INET,
    user_agent      TEXT,
    aceito_em       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_aceite_usuario ON bss.aceite_termo (id_usuario);
CREATE INDEX IF NOT EXISTS idx_aceite_empresa ON bss.aceite_termo (id_empresa);

COMMENT ON TABLE bss.aceite_termo IS
    'Auditoria do aceite do termo de responsabilidade civil/criminal. Um aceite por (usuario, empresa). Nunca deletar: e prova juridica';
COMMENT ON COLUMN bss.aceite_termo.texto_hash IS
    'SHA-256 do texto que a pessoa viu. Prova a redacao aceita mesmo que o template mude depois';


-- ----------------------------------------------------------------------------
-- 3. SOLICITAÇÃO DE ACESSO — a fila do analista
-- ----------------------------------------------------------------------------
-- Por que não usar só usuario_empresa.ativo:
--   `ativo` guarda o ESTADO (tem acesso ou não), mas não distingue "pendente"
--   de "reprovado", nem registra quem aprovou e quando. A solicitação é o
--   PEDIDO e sua história; usuario_empresa é o RESULTADO dela.
--
-- Fluxo: autocadastro cria solicitacao(pendente) → analista aprova
--        → cria/ativa usuario_empresa → contato passa a enxergar o CNPJ.
CREATE TABLE IF NOT EXISTS bss.solicitacao_acesso (
    id              BIGSERIAL PRIMARY KEY,
    id_usuario      INT    NOT NULL,                                  -- quem pediu
    id_empresa      BIGINT NOT NULL REFERENCES bss.empresa(id) ON DELETE CASCADE,
    -- De onde veio:
    origem          VARCHAR(20) NOT NULL DEFAULT 'autocadastro',      -- autocadastro | interno
    -- Empresa já existia (reivindicação) ou nasceu junto (RFB)? Muda o risco:
    --   true  = alguém pedindo acesso a dados que JÁ ESTÃO LÁ  → conferir bem
    --   false = trouxe cliente novo, com a Receita validando    → risco baixo
    empresa_preexistente BOOLEAN NOT NULL DEFAULT TRUE,
    -- Estado:
    status          VARCHAR(20) NOT NULL DEFAULT 'pendente',          -- pendente | aprovada | reprovada
    motivo_reprovacao TEXT,
    -- Quem julgou:
    avaliado_por_id INT,                                              -- bss_users.id do analista
    avaliado_em     TIMESTAMPTZ,
    -- Prova de origem do pedido:
    ip_origem       INET,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_solic_usuario ON bss.solicitacao_acesso (id_usuario);
CREATE INDEX IF NOT EXISTS idx_solic_empresa ON bss.solicitacao_acesso (id_empresa);
-- Índice da FILA: é o que o sininho consulta a cada carga de página.
-- Parcial, porque 99% das linhas vão estar resolvidas e não interessam.
CREATE INDEX IF NOT EXISTS idx_solic_pendentes
    ON bss.solicitacao_acesso (criado_em)
 WHERE status = 'pendente';
-- Um pedido pendente por (usuario, empresa) — evita duplicar a fila se a pessoa
-- reenviar o formulário. Reprovados/aprovados podem repetir (nova tentativa).
CREATE UNIQUE INDEX IF NOT EXISTS uq_solic_pendente_por_par
    ON bss.solicitacao_acesso (id_usuario, id_empresa)
 WHERE status = 'pendente';

COMMENT ON TABLE bss.solicitacao_acesso IS
    'Fila de aprovacao do autocadastro. Todo contato novo passa por analista interno. usuario_empresa e o RESULTADO da aprovacao';
COMMENT ON COLUMN bss.solicitacao_acesso.empresa_preexistente IS
    'true = reivindicacao de empresa que ja existia (caso arriscado); false = empresa criada junto via RFB';


-- ----------------------------------------------------------------------------
-- 4. VIEW: a fila que a tela e o sininho consomem
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW bss.v_solicitacao_pendente AS
SELECT
    s.id,
    s.criado_em,
    s.origem,
    s.empresa_preexistente,
    s.ip_origem,
    u.id            AS id_usuario,
    u.nome          AS contato_nome,
    u.email         AS contato_email,
    u.telefone      AS contato_telefone,
    u.tipo_cadastro AS contato_tipo_cadastro,
    e.id            AS id_empresa,
    e.cnpj          AS empresa_cnpj,
    e.razao_social  AS empresa,
    e.tipo_cadastro AS empresa_tipo_cadastro,
    -- Contexto pro analista decidir: quem JÁ administra este CNPJ?
    -- Se a empresa já tem gestores, o natural é confirmar com eles.
    (SELECT COUNT(*) FROM bss.usuario_empresa ue
      WHERE ue.id_empresa = e.id AND ue.ativo) AS gestores_atuais,
    -- Há quanto tempo espera (a fila envelhece — o sininho não conta isso)
    EXTRACT(DAY FROM NOW() - s.criado_em)::int AS dias_esperando,
    -- O aceite correspondente, se houver
    (SELECT MAX(a.aceito_em) FROM bss.aceite_termo a
      WHERE a.id_usuario = s.id_usuario AND a.id_empresa = s.id_empresa) AS termo_aceito_em
FROM bss.solicitacao_acesso s
JOIN bss_users    u ON u.id = s.id_usuario
JOIN bss.empresa  e ON e.id = s.id_empresa
WHERE s.status = 'pendente';


DO $$
BEGIN
    RAISE NOTICE 'Criado: bss.aceite_termo, bss.solicitacao_acesso, bss.v_solicitacao_pendente';
    RAISE NOTICE 'bss_users ganhou tipo_cadastro (default interno — o que existe hoje e da GNB)';
    RAISE NOTICE 'Sininho: SELECT COUNT(*) FROM bss.v_solicitacao_pendente;';
END $$;
