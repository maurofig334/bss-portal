-- ============================================================================
-- 21_modelo_email.sql — modelos de e-mail em massa (inadimplência, etc.)
-- ============================================================================
--
-- A BSS dispara e-mails institucionais em lote: avisa inadimplentes, irregulares,
-- lembra de emitir boletos, etc. Os TEXTOS são escritos e ajustados pela própria
-- BSS (falam em responsabilidade civil, citam o Código Civil) — então precisam
-- morar num lugar editável, não chumbados no código.
--
-- O corpo usa variáveis {{nome}} que o resolvedor (app/modelo_variaveis.py)
-- preenche na hora do envio/preview. Nomes limpos, não os $contact_..._c do
-- SuiteCRM — o de-para está em docs/MODELOS_EMAIL.md.
--
-- DESTINATÁRIO: cada modelo vai pro CONTATO (pessoa que administra os CNPJs) ou
-- pra EMPRESA (email_cobranca). Muda quais variáveis fazem sentido — um modelo
-- de contato pode listar VÁRIAS empresas; um de empresa fala de uma só.
--
-- Esta migração cria a tabela e semeia os 13 modelos do print como RASCUNHO
-- (assunto/corpo vazios, ativo=FALSE). A BSS preenche o conteúdo depois. Semear
-- vazio > deixar a BSS criar do zero: garante codigo/destinatario consistentes
-- e o disparo (fase futura) já encontra a chave que espera.
--
-- Aplicar:
--     venv/bin/python -m scripts.aplicar_sql scripts/21_modelo_email.sql
-- ============================================================================

CREATE TABLE IF NOT EXISTS bss.modelo_email (
    id            BIGSERIAL PRIMARY KEY,
    -- codigo = chave estável usada pelo disparo automático (ex: o job de
    -- inadimplência procura 'inadimplente_contato'). NÃO renomear depois de
    -- ligado a um gatilho.
    codigo        VARCHAR(50)  NOT NULL UNIQUE,
    nome          VARCHAR(120) NOT NULL,       -- rótulo na tela
    -- Pra quem vai: decide o conjunto de variáveis válidas.
    destinatario  VARCHAR(10)  NOT NULL DEFAULT 'contato'
                  CHECK (destinatario IN ('contato', 'empresa')),
    -- Agrupamento solto na tela (inadimplencia, irregularidade, boleto,
    -- cadastro, beneficio). Texto livre de propósito — não vale uma FK.
    categoria     VARCHAR(30),
    assunto       TEXT NOT NULL DEFAULT '',
    corpo         TEXT NOT NULL DEFAULT '',
    ativo         BOOLEAN NOT NULL DEFAULT FALSE,   -- rascunho não dispara
    observacao    TEXT,                             -- nota interna da BSS
    -- Auditoria: texto com peso jurídico, importa saber quem mudou por último.
    atualizado_por_id INT,
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE bss.modelo_email IS
    'Modelos de e-mail em massa. Corpo usa {{variaveis}} (ver app/modelo_variaveis.py).';

-- Os 13 modelos do print, como rascunho. ON CONFLICT DO NOTHING pra ser
-- idempotente: rodar de novo não apaga o que a BSS já escreveu.
INSERT INTO bss.modelo_email (codigo, nome, destinatario, categoria) VALUES
    ('inadimplente_contato',      'Contatos - Notif p/ Inadimplentes',      'contato', 'inadimplencia'),
    ('inadimplente_empresa',      'Empresas - Notif p/ Inadimplentes',      'empresa', 'inadimplencia'),
    ('inadimplente_contato_ant',  'Contatos - Notif p/ Inadimplentes (ANTIGO)', 'contato', 'inadimplencia'),
    ('inadimplente_empresa_ant',  'Empresas - Notif p/ Inadimplentes (ANTIGO)', 'empresa', 'inadimplencia'),
    ('boleto_vencido',            'Boleto Vencido',                         'contato', 'boleto'),
    ('nao_gerou_boletos_contato', 'Contatos - Não gerou Boletos',           'contato', 'boleto'),
    ('nao_gerou_boletos_empresa', 'Empresas - Não gerou Boletos',           'empresa', 'boleto'),
    ('novo_contato_autocadastro', 'Novo Contato - Autocadastro',            'contato', 'cadastro'),
    ('irregular_contato',         'Contatos - Notif p/ Irregulares',        'contato', 'irregularidade'),
    ('irregular_empresa',         'Empresas - Notif p/ Irregulares',        'empresa', 'irregularidade'),
    ('atualiza_base_empresa',     'Empresas - Atualiz. Base + Boletos',     'empresa', 'boleto'),
    ('atualiza_base_contato',     'Contatos - Atualiz. Base + Boletos',     'contato', 'boleto'),
    ('benef_conf_dados',          'Contatos - Atualização Benef - Conf de dados', 'contato', 'beneficio'),
    ('benef_doc_pendente',        'Contatos - Atualização Benef - Doc Pendente',  'contato', 'beneficio')
ON CONFLICT (codigo) DO NOTHING;
