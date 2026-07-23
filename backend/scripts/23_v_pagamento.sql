-- ============================================================================
-- 23_v_pagamento.sql — view do contas a pagar com processo/empresa resolvidos
-- ============================================================================
--
-- Mesmo padrão de v_boleto/v_processo: a tela e o export leem a view, não a
-- tabela crua, pra já vir com protocolo, empresa, tipo e trabalhador.
--
-- DATA: usa data_prevista como a data operacional. Descoberta no sync
-- (conferir_pagamentos.py): data_vencimento é NULL em 100% dos pagamentos —
-- o legado só preenchia data_prevista. Filtrar/ordenar por data_vencimento
-- daria vazio sempre.
--
-- Aplicar:
--     venv/bin/python -m scripts.aplicar_sql scripts/23_v_pagamento.sql
-- ============================================================================

CREATE OR REPLACE VIEW bss.v_pagamento AS
SELECT
    pg.id,
    pg.id_processo,
    pg.parcela,
    pg.valor,
    pg.status,
    pg.forma_pagamento,
    pg.documento,
    -- data_prevista é a data real (ver cabeçalho). Exposta também como
    -- data_referencia pra a tela não precisar saber dessa história.
    pg.data_prevista,
    pg.data_prevista        AS data_referencia,
    pg.data_pagamento,
    pg.beneficiario_nome,
    pg.beneficiario_cpf,
    -- Do processo:
    p.protocolo,
    p.id_empresa,
    p.id_sindicato,
    p.id_tipo_beneficio,
    e.razao_social          AS empresa,
    e.cnpj                  AS empresa_cnpj,
    s.razao_social          AS sindicato,
    tb.nome                 AS tipo_beneficio,
    t.nome_completo         AS trabalhador,
    t.cpf                   AS trabalhador_cpf,
    pg.criado_em
FROM bss.pagamento pg
JOIN bss.processo_beneficio p ON p.id = pg.id_processo
LEFT JOIN bss.empresa        e  ON e.id  = p.id_empresa
LEFT JOIN bss.sindicato      s  ON s.id  = p.id_sindicato
LEFT JOIN bss.tipo_beneficio tb ON tb.id = p.id_tipo_beneficio
LEFT JOIN bss.trabalhador    t  ON t.id  = p.id_trabalhador;
