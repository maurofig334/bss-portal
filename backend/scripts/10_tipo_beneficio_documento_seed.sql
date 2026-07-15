-- ============================================================================
-- 10_tipo_beneficio_documento_seed.sql
--
-- Popula bss.tipo_beneficio_documento — a regra de QUAIS DOCUMENTOS cada tipo
-- de benefício exige (épico #22, módulo de Documentos).
--
-- FONTE: tela de inclusão de benefício do Portal BSS de homologação
--   (portalbsshom.nexussistemas.com.br → Benefícios → Adicionar),
--   seção "Documentos Obrigatórios". Extraída em 01/07/2026.
--   No portal, o asterisco (*) marca o documento obrigatório.
--
-- NÃO CONFUNDIR com a outra regra: QUAIS BENEFÍCIOS cada sindicato oferece
--   fica em bss.valor_beneficio_sindicato (UNIQUE id_sindicato+id_tipo_beneficio).
--   Por isso a lista de tipos no portal varia conforme o sindicato do trabalhador.
--
-- IDEMPOTENTE: ON CONFLICT (id_tipo_beneficio, codigo) DO UPDATE.
--
-- ----------------------------------------------------------------------------
-- REGRAS DE NEGÓCIO CONFIRMADAS PELO MAURO (01/07/2026):
--
--   * acionamento_funeral — 'Processo da Funerária' é obrigatorio=FALSE DE
--                          PROPÓSITO. Este benefício é aberto por um usuário
--                          específico e PODE SER ABERTO SEM DOCUMENTAÇÃO —
--                          o upload é posterior. Não "corrigir" pra TRUE.
--
--   * consulta_medica     — NÃO EXIGE DOCUMENTO NENHUM, por design. O tipo
--                          serve só pro usuário solicitar a consulta ou o
--                          reembolso. Por isso não há nenhuma linha aqui pra
--                          este tipo (o portal não exibir docs não é bug).
--
-- PENDENTE — Mauro vai definir com o especialista, em migration futura:
--   * exame, brinde_sindicato, auxilio_creche — sem regra de documentos ainda.
--     (não apareceram na inclusão porque a lista veio sem trabalhador
--      selecionado, logo sem o filtro de sindicato)
--
-- FORA DE ESCOPO (decidido pra depois):
--   * Documentos com "Baixar Formulário" (Termo de Responsabilidade e
--     Autorização de Crédito): o portal oferece um modelo pra baixar, assinar
--     e reanexar. Falta coluna (ex.: formulario_modelo_url) — migration futura.
-- ============================================================================

INSERT INTO bss.tipo_beneficio_documento (id_tipo_beneficio, codigo, nome, obrigatorio, ordem)
SELECT t.id, v.codigo, v.nome, v.obrigatorio, v.ordem
  FROM bss.tipo_beneficio t
  JOIN (VALUES
    -- ---------------------------------------------------------------- NATALIDADE
    ('natalidade', 'certidao_nascimento', 'Certidão de Nascimento',                   TRUE,   1),
    ('natalidade', 'ctps',                'CTPS - Carteira de Trabalho',              FALSE,  2),
    ('natalidade', 'outros',              'Outros',                                   FALSE, 99),

    -- --------------------------------------------------------------- FALECIMENTO
    ('falecimento', 'certidao_obito',              'Certidão de Óbito',                                                    TRUE,   1),
    ('falecimento', 'certidao_casamento',          'Certidão de casamento ou de união estável',                            TRUE,   2),
    ('falecimento', 'vinculo_beneficiario',        'Documento que Comprove o Vínculo do Trabalhador Falecido com o Beneficiário', TRUE, 3),
    ('falecimento', 'comprovante_endereco',        'Comprovante de Endereço',                                              TRUE,   4),
    ('falecimento', 'comprovante_sepultamento',    'Comprovante de Sepultamento',                                          TRUE,   5),
    ('falecimento', 'comprovante_conta_bancaria',  'Comprovante de conta bancária',                                        TRUE,   6),
    ('falecimento', 'ctps',                        'CTPS',                                                                 FALSE,  7),
    ('falecimento', 'termo_responsabilidade',      'Termo de Responsabilidade Falecimento',                                FALSE,  8),
    ('falecimento', 'autorizacao_credito',         'Autorização de crédito',                                               FALSE,  9),
    ('falecimento', 'outros',                      'Outros',                                                               FALSE, 99),

    -- ------------------------------------------------------------------ ACIDENTE
    ('acidente', 'cat',             'CAT - Comunicação de Acidente do Trabalho', TRUE,   1),
    ('acidente', 'atestado_medico', 'Atestado assinado pelo médico',             TRUE,   2),
    ('acidente', 'ctps',            'CTPS',                                      FALSE,  3),
    ('acidente', 'outros',          'Outros',                                    FALSE, 99),

    -- ------------------------------------------------------------- INCAPACITAÇÃO
    ('incapacitacao', 'laudo_inss',            'Laudo médico INSS (carta de concessão INSS) informando aposentadoria por invalidez', TRUE, 1),
    ('incapacitacao', 'comprovante_endereco',  'Comprovante de Endereço',                   TRUE,   2),
    ('incapacitacao', 'comprovante_bancario',  'Comprovante bancário',                      TRUE,   3),
    ('incapacitacao', 'ctps',                  'CTPS',                                      FALSE,  4),
    ('incapacitacao', 'termo_responsabilidade','Termo de Responsabilidade Incapacitação',   FALSE,  5),
    ('incapacitacao', 'autorizacao_credito',   'Autorização de Crédito Incapacitação',      FALSE,  6),
    ('incapacitacao', 'outros',                'Outros',                                    FALSE, 99),

    -- --------------------------------------------------------- REEMBOLSO RESCISÃO
    ('reembolso_rescisao', 'trct',                          'TRCT Termo de Rescisão do Contrato de Trabalho Completo', TRUE,   1),
    ('reembolso_rescisao', 'comprovante_deposito_rescisao', 'Comprovante de Depósito do Valor da Rescisão',            TRUE,   2),
    ('reembolso_rescisao', 'outros',                        'Outros',                                                  FALSE, 99),

    -- -------------------------------------------------------- ACIONAMENTO FUNERAL
    -- Opcional de propósito: o benefício é aberto por usuário específico e pode
    -- ser aberto SEM documentação — o upload vem depois. Não mudar pra TRUE.
    ('acionamento_funeral', 'processo_funeraria', 'Processo da Funerária', FALSE, 1)

  ) AS v(tipo_codigo, codigo, nome, obrigatorio, ordem)
    ON v.tipo_codigo = t.codigo
ON CONFLICT (id_tipo_beneficio, codigo) DO UPDATE
   SET nome        = EXCLUDED.nome,
       obrigatorio = EXCLUDED.obrigatorio,
       ordem       = EXCLUDED.ordem,
       ativo       = TRUE;


-- Conferência rápida (roda e mostra o resultado):
--   SELECT t.codigo AS tipo, d.codigo, d.nome, d.obrigatorio, d.ordem
--     FROM bss.tipo_beneficio_documento d
--     JOIN bss.tipo_beneficio t ON t.id = d.id_tipo_beneficio
--    ORDER BY t.ordem, d.ordem;
