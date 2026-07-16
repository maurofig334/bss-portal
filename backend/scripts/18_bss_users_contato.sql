-- ============================================================================
-- 18_bss_users_contato.sql
--
-- Prepara bss_users pra receber os CONTATOS do legado (usuários externos).
--
-- Ver docs/AUTOCADASTRO.md. O "Contato" do SuiteCRM É o bss_users com
-- perfil='empresa' — não é entidade separada.
--
-- ESCOPO DESTA LEVA (decisão do Mauro, 01/07/2026):
--   Só contatos do grupo EMPRESAS. Funerárias e Sindicatos ficam de fora até
--   definirmos o que cada grupo enxerga. O legado tem três grupos externos
--   (Portal User Group: Empresas / Funerárias / Sindicatos); o BSS só tem
--   perfis 'empresa' e 'sindicato' — falta 'funeraria'.
--
--   Nota de contexto: a Funerária é quem abre o benefício "Acionamento
--   Funeral" — o mesmo que pode ser aberto SEM documentação, com upload
--   posterior (ver 10_tipo_beneficio_documento_seed.sql). O tipo de usuário e
--   a regra de documento são a mesma coisa vista de dois ângulos.
--
-- IDEMPOTENTE: ADD COLUMN IF NOT EXISTS.
-- ============================================================================

ALTER TABLE bss_users
    -- Chave de idempotência do sync (lição #2 do projeto: toda tabela
    -- espelhada tem id_legado_uuid). = contacts.id do SuiteCRM.
    -- NULL nos usuários nativos do BSS (staff GNB criado à mão).
    ADD COLUMN IF NOT EXISTS id_legado_uuid CHAR(36),

    -- Preferências de notificação. JSONB em vez de 4 colunas porque a lista
    -- cresce: hoje o legado tem financeiro/benefício/atualização/boleto, e
    -- qualquer aviso novo viraria mais uma migration.
    -- Formato: {"financeiro": true, "beneficio": true, "atualizacao": true, "boleto": true}
    ADD COLUMN IF NOT EXISTS preferencias_notificacao JSONB NOT NULL DEFAULT '{}'::jsonb;

-- UNIQUE simples (não parcial!). No Postgres, UNIQUE aceita múltiplos NULLs —
-- os usuários nativos convivem sem problema.
-- (Índice parcial NÃO é inferido por ON CONFLICT sem repetir o predicado —
--  armadilha que já quebrou o sync de documentos, ver migration 12.)
CREATE UNIQUE INDEX IF NOT EXISTS uq_bss_users_legado_uuid
    ON bss_users (id_legado_uuid);

COMMENT ON COLUMN bss_users.id_legado_uuid IS
    'contacts.id do SuiteCRM. NULL = usuario nativo do BSS (staff GNB)';
COMMENT ON COLUMN bss_users.preferencias_notificacao IS
    'JSONB: {"financeiro":bool,"beneficio":bool,"atualizacao":bool,"boleto":bool}. Vem de recebeemail*_c do legado';


-- ----------------------------------------------------------------------------
-- NOTA SOBRE SENHAS — importante, não apagar
-- ----------------------------------------------------------------------------
-- As senhas do legado NÃO são migradas, e não é escolha: `contacts_cstm.
-- password_c` guarda cifra REVERSÍVEL (16 bytes base64, ex.:
-- "Lr/Q78KQNmivwoez0uJSDA=="), não hash. Quem tem a chave lê a senha dos 2.833
-- usuários do portal em texto claro. É um achado de segurança que vale reportar
-- à BSS por si só.
--
-- O BSS usa bcrypt (via única). No sync, cada contato migrado recebe um bcrypt
-- de bytes ALEATÓRIOS: hash válido, senha que ninguém conhece. Login falha
-- limpo (401) e o usuário é obrigado a usar "esqueci minha senha".
--
-- CONSEQUÊNCIA PRO BIG BANG: no corte, TODOS os contatos externos precisam
-- redefinir senha. Isso é tarefa de comunicação, não detalhe técnico — precisa
-- estar no BIG_BANG.md e no aviso ao cliente.
-- ----------------------------------------------------------------------------

DO $$
DECLARE
    nativos BIGINT;
BEGIN
    SELECT COUNT(*) INTO nativos FROM bss_users WHERE id_legado_uuid IS NULL;
    RAISE NOTICE 'bss_users: % usuario(s) nativo(s) (id_legado_uuid NULL) — staff GNB', nativos;
    RAISE NOTICE 'Pronto pro sync de contatos (grupo Empresas).';
END $$;
