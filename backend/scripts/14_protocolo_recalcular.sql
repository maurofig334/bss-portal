-- ============================================================================
-- 14_protocolo_do_legado.sql  (arquivo mantém o nome 14_protocolo_recalcular
-- por já estar versionado; o conteúdo mudou completamente — ver histórico)
--
-- Prepara bss.processo_beneficio.protocolo pra receber o valor REAL do legado
-- (cases.name), em vez de um número derivado.
--
-- ----------------------------------------------------------------------------
-- HISTÓRICO DESTE ERRO — vale ler antes de mexer
-- ----------------------------------------------------------------------------
-- A migration 13 fez BACKFILL DERIVANDO o protocolo:
--     protocolo = AA + MM (de criado_em) + LPAD(numero_processo, 5, '0')
-- A fórmula foi validada em DOIS processos e bateu nos dois... mas os dois
-- eram do formato NOVO. Amostra viciada.
--
-- A realidade tem (pelo menos) DOIS formatos convivendo:
--   NOVO   9 dígitos:  260420817 = AA+MM da criação + 5 sequenciais
--   ANTIGO 14 dígitos: 20240322105945 — timestamp vindo de um sistema PHP
--                      ANTERIOR ao SuiteCRM
--
-- E o protocolo ESTÁ GRAVADO: fica em `cases.name` (o SuiteCRM reaproveitou o
-- campo "Assunto" pra guardar o número). Não há o que calcular — é copiar.
--
-- Prova de que derivar era impossível: os registros de 14 dígitos têm
-- date_entered em 02–03/01/2025, todos no mesmo lote — a data da MIGRAÇÃO
-- PHP→SuiteCRM, não da criação. Derivar por AAMM da criação geraria o mesmo
-- prefixo (2501) pra milhares de processos criados ao longo de anos.
--
-- CONSEQUÊNCIA PRA criado_em: pros registros vindos do PHP, criado_em recebe a
-- data da migração (02–03/01/2025), não a criação real — que se perdeu. É
-- melhor que a data do sync (o bug anterior), mas NÃO é a verdade. Qualquer
-- relatório "processos por mês de criação" vai mostrar um pico artificial em
-- janeiro/2025.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Alargar a coluna: 14 dígitos não cabem em VARCHAR(9)
-- ----------------------------------------------------------------------------
-- O schema assumiu 9 chars (AAMMDD+3). Os protocolos do PHP têm 14.
-- VARCHAR(20) dá folga pra um eventual terceiro formato.
--
-- A view bss.v_processo expõe p.protocolo, e o Postgres não deixa alterar o
-- tipo de coluna usada por view ("cannot alter type of a column used by a view
-- or rule"). Então: dropa, altera, recria idêntica.
DROP VIEW IF EXISTS bss.v_processo;

ALTER TABLE bss.processo_beneficio
    ALTER COLUMN protocolo TYPE VARCHAR(20);

-- Recriada exatamente como no 01_schema_inicial.sql (linhas 926-966).
-- Se a view mudar lá, esta cópia precisa acompanhar.
CREATE OR REPLACE VIEW bss.v_processo AS
SELECT
    p.id,
    p.numero_processo,
    p.protocolo,
    p.status,
    sp.nome                           AS status_nome,
    sp.categoria                      AS status_categoria,
    sp.cor_hex                        AS status_cor,
    p.id_empresa,
    e.razao_social                    AS empresa,
    e.cnpj                            AS empresa_cnpj,
    p.id_sindicato,
    s.razao_social                    AS sindicato,
    p.id_trabalhador,
    t.cpf                             AS trabalhador_cpf,
    t.nome_completo                   AS trabalhador_nome,
    p.id_tipo_beneficio,
    tb.nome                           AS tipo_beneficio,
    tb.codigo                         AS tipo_beneficio_codigo,
    p.beneficiario_nome,
    p.beneficiario_cpf,
    p.beneficiario_grau_parentesco,
    p.liberalidade,
    p.data_evento,
    p.data_obito,
    p.data_finalizacao,
    p.forma_pagamento,
    p.codigo_rastreio_cartao,
    p.vencimento_cartao_em,
    p.qtd_bebes,
    p.dados_revisados,
    p.ultima_atualizacao_portal_em,
    p.criado_em,
    p.atualizado_em
FROM bss.processo_beneficio p
LEFT JOIN bss.empresa         e  ON e.id  = p.id_empresa
LEFT JOIN bss.sindicato       s  ON s.id  = p.id_sindicato
LEFT JOIN bss.trabalhador     t  ON t.id  = p.id_trabalhador
LEFT JOIN bss.tipo_beneficio  tb ON tb.id = p.id_tipo_beneficio
LEFT JOIN bss.status_processo sp ON sp.codigo = p.status;


-- ----------------------------------------------------------------------------
-- 2. Zerar TODOS os protocolos derivados pela migration 13
-- ----------------------------------------------------------------------------
-- Todos são suspeitos: nos antigos estão simplesmente errados (formato e valor),
-- e nos novos foram calculados a partir de criado_em quando ele ainda guardava
-- a data do sync. O sync corrigido repovoa a partir de cases.name.
UPDATE bss.processo_beneficio
   SET protocolo = NULL
 WHERE id_legado_uuid IS NOT NULL;


-- ----------------------------------------------------------------------------
-- 3. Diagnóstico
-- ----------------------------------------------------------------------------
DO $$
DECLARE
    tam INT;
    com_proto BIGINT;
BEGIN
    SELECT character_maximum_length INTO tam
      FROM information_schema.columns
     WHERE table_schema = 'bss' AND table_name = 'processo_beneficio'
       AND column_name = 'protocolo';
    SELECT COUNT(*) INTO com_proto
      FROM bss.processo_beneficio WHERE protocolo IS NOT NULL;

    RAISE NOTICE 'protocolo agora e VARCHAR(%)  ·  linhas com protocolo preenchido: %',
                 tam, com_proto;
    RAISE NOTICE 'Proximo passo: python -m scripts.sync_legado --tabela processo';
    RAISE NOTICE '  (traz cases.name -> protocolo, o numero real do legado)';
END $$;


-- NOTA sobre bss.gerar_protocolo() (criada na migration 13): continua VÁLIDA.
-- Ela serve pros processos NOVOS, criados no BSS depois do Big Bang, e usa o
-- formato ATUAL do legado (AAMM + 5 sequenciais), continuando a série via
-- bss.seq_protocolo. Os formatos antigos são história — não se geram mais.
