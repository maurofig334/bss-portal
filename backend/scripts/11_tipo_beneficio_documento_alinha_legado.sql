-- ============================================================================
-- 11_tipo_beneficio_documento_alinha_legado.sql
--
-- Alinha o `codigo` de bss.tipo_beneficio_documento aos valores REAIS de
-- `documents.category_id` do SuiteCRM legado.
--
-- POR QUÊ: a migration 10 semeou códigos "bonitos" inventados por mim a partir
-- dos rótulos do portal (ex.: 'certidao_nascimento'). A inspeção do legado
-- (scripts/inspecionar_documentos.py, 01/07/2026) mostrou que o legado usa
-- outros valores em documents.category_id (ex.: 'certidao_de_nascimento').
-- Sem alinhar, o sync de documentos não consegue casar o anexo com a regra
-- (tipo_beneficio_documento) e todo documento cairia em "sem tipo".
--
-- Volumes por category_id no legado (deleted=0), pra referência:
--   certidao_de_nascimento 5.113 | outros 3.351 | ctps 2.295
--   autorizacao_de_credito 1.704 | termo_de_responsabilidade 1.378
--   comprovante_bancario 1.373   | comprovante_de_vinculo 1.364
--   comprovante_de_endereco 1.266| certidao_de_obito 1.200
--   comprovante_de_sepultamento 1.191 | casamento_uniao 1.008
--   atestado_medico 126 | cat 120 | trct 106 | comprovante_rescisao 105
--   laudo_medico_inss 36 | processo_de_funeraria 7
--
-- Já coincidiam (não precisam de UPDATE): ctps, outros, cat, atestado_medico, trct.
--
-- IDEMPOTENTE: o UPDATE só age se o código antigo ainda existir; rodar duas
-- vezes não faz nada na segunda. Usa WHERE NOT EXISTS pra não violar a
-- UNIQUE (id_tipo_beneficio, codigo) caso o alvo já esteja lá.
-- ============================================================================

DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT * FROM (VALUES
            -- (tipo_codigo, codigo_antigo, codigo_novo_do_legado)
            ('natalidade',          'certidao_nascimento',           'certidao_de_nascimento'),

            ('falecimento',         'certidao_obito',                'certidao_de_obito'),
            ('falecimento',         'certidao_casamento',            'casamento_uniao'),
            ('falecimento',         'vinculo_beneficiario',          'comprovante_de_vinculo'),
            ('falecimento',         'comprovante_endereco',          'comprovante_de_endereco'),
            ('falecimento',         'comprovante_sepultamento',      'comprovante_de_sepultamento'),
            ('falecimento',         'comprovante_conta_bancaria',    'comprovante_bancario'),
            ('falecimento',         'termo_responsabilidade',        'termo_de_responsabilidade'),
            ('falecimento',         'autorizacao_credito',           'autorizacao_de_credito'),

            ('incapacitacao',       'laudo_inss',                    'laudo_medico_inss'),
            ('incapacitacao',       'comprovante_endereco',          'comprovante_de_endereco'),
            ('incapacitacao',       'termo_responsabilidade',        'termo_de_responsabilidade'),
            ('incapacitacao',       'autorizacao_credito',           'autorizacao_de_credito'),
            -- incapacitacao.comprovante_bancario já bate com o legado

            ('reembolso_rescisao',  'comprovante_deposito_rescisao', 'comprovante_rescisao'),

            ('acionamento_funeral', 'processo_funeraria',            'processo_de_funeraria')
        ) AS v(tipo_codigo, codigo_antigo, codigo_novo)
    LOOP
        UPDATE bss.tipo_beneficio_documento d
           SET codigo = r.codigo_novo
          FROM bss.tipo_beneficio t
         WHERE t.id = d.id_tipo_beneficio
           AND t.codigo = r.tipo_codigo
           AND d.codigo = r.codigo_antigo
           AND NOT EXISTS (
                 SELECT 1
                   FROM bss.tipo_beneficio_documento x
                  WHERE x.id_tipo_beneficio = d.id_tipo_beneficio
                    AND x.codigo = r.codigo_novo
               );
    END LOOP;
END $$;


-- Conferência: os códigos abaixo devem existir e bater 1:1 com
-- documents.category_id do legado.
--   SELECT t.codigo AS tipo, d.codigo, d.nome, d.obrigatorio
--     FROM bss.tipo_beneficio_documento d
--     JOIN bss.tipo_beneficio t ON t.id = d.id_tipo_beneficio
--    ORDER BY t.ordem, d.ordem;
