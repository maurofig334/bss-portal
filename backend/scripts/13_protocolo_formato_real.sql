-- ============================================================================
-- 13_protocolo_formato_real.sql
--
-- Corrige o PROTOCOLO: formato real, backfill dos migrados e continuidade
-- da série depois do Big Bang.
--
-- O QUE ESTAVA ERRADO
-- -------------------
-- O 01_schema_inicial.sql assumiu:
--     "protocolo = AAMMDD + 3 dígitos sequenciais por dia"
--     gerar_protocolo() → 260504001, 260504002, 260505001 (reseta todo dia)
--
-- A regra real (confirmada com o Mauro em 01/07/2026, com exemplo do legado):
--     protocolo = AA + MM (da criação) + 5 dígitos SEQUENCIAIS GLOBAIS
--     260420817 = 26 (ano) + 04 (mês) + 20817 (sequencial)
--
-- E os 5 dígitos são o próprio numero_processo (case_number do SuiteCRM) —
-- que o schema chamava de "INTERNO, não exibido ao cliente". É o contrário:
-- é o número mais visível que existe, o que o cliente usa pra falar do caso.
--
-- CONSEQUÊNCIA SE NÃO CORRIGIR: no primeiro processo criado após o Big Bang,
-- o protocolo mudaria de formato e a numeração recomeçaria do 001 — o cliente
-- veria os números "voltarem no tempo".
--
-- IDEMPOTENTE: backfill só onde protocolo IS NULL; sequence com IF NOT EXISTS;
-- função com CREATE OR REPLACE.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Diagnóstico: dá pra derivar protocolo de quantos processos?
-- ----------------------------------------------------------------------------
DO $$
DECLARE
    total        BIGINT;
    derivaveis   BIGINT;
    sem_numero   BIGINT;
    estouram     BIGINT;
BEGIN
    SELECT COUNT(*) INTO total FROM bss.processo_beneficio;
    SELECT COUNT(*) INTO derivaveis FROM bss.processo_beneficio
     WHERE numero_processo IS NOT NULL AND criado_em IS NOT NULL
       AND numero_processo BETWEEN 0 AND 99999;
    SELECT COUNT(*) INTO sem_numero FROM bss.processo_beneficio
     WHERE numero_processo IS NULL OR criado_em IS NULL;
    SELECT COUNT(*) INTO estouram FROM bss.processo_beneficio
     WHERE numero_processo > 99999;

    RAISE NOTICE 'processos=%  derivaveis=%  sem numero/data=%  numero>99999=%',
                 total, derivaveis, sem_numero, estouram;
    IF estouram > 0 THEN
        RAISE WARNING 'Existem % processos com numero_processo > 99999 — '
                      'nao cabem em 5 digitos. Protocolo ficara NULL neles.', estouram;
    END IF;
END $$;


-- ----------------------------------------------------------------------------
-- 2. Backfill: protocolo = AAMM(criacao) + LPAD(numero_processo, 5, '0')
-- ----------------------------------------------------------------------------
-- Só preenche onde está NULL (não sobrescreve nada já definido).
-- Colisões (mesmo AAMM+numero em dois processos) seriam violação da UNIQUE —
-- por isso filtramos duplicatas antes, deixando-as NULL pra análise manual.
WITH candidatos AS (
    SELECT p.id,
           to_char(p.criado_em, 'YYMM') || lpad(p.numero_processo::text, 5, '0') AS proto
      FROM bss.processo_beneficio p
     WHERE p.protocolo IS NULL
       AND p.numero_processo IS NOT NULL
       AND p.criado_em IS NOT NULL
       AND p.numero_processo BETWEEN 0 AND 99999
),
unicos AS (
    SELECT proto
      FROM candidatos
     GROUP BY proto
    HAVING COUNT(*) = 1
)
UPDATE bss.processo_beneficio p
   SET protocolo = c.proto
  FROM candidatos c
  JOIN unicos u ON u.proto = c.proto
 WHERE p.id = c.id
   AND NOT EXISTS (SELECT 1 FROM bss.processo_beneficio x WHERE x.protocolo = c.proto);


-- ----------------------------------------------------------------------------
-- 3. Sequence que CONTINUA a série do legado
-- ----------------------------------------------------------------------------
-- Os 5 dígitos são globais e nunca resetam. A sequence começa depois do maior
-- numero_processo migrado, pra o primeiro processo do BSS seguir a numeração
-- sem colidir com o legado.
CREATE SEQUENCE IF NOT EXISTS bss.seq_protocolo AS BIGINT START WITH 1;

DO $$
DECLARE
    proximo BIGINT;
BEGIN
    SELECT COALESCE(MAX(numero_processo), 0) + 1
      INTO proximo
      FROM bss.processo_beneficio
     WHERE numero_processo BETWEEN 0 AND 99999;

    -- Só avança a sequence (nunca recua) — seguro em reexecução
    IF proximo > (SELECT last_value FROM bss.seq_protocolo) THEN
        PERFORM setval('bss.seq_protocolo', proximo, false);
        RAISE NOTICE 'seq_protocolo posicionada em % (proximo numero_processo)', proximo;
    ELSE
        RAISE NOTICE 'seq_protocolo ja esta em % — nada a fazer',
                     (SELECT last_value FROM bss.seq_protocolo);
    END IF;
END $$;


-- ----------------------------------------------------------------------------
-- 4. gerar_protocolo(): formato real, série contínua
-- ----------------------------------------------------------------------------
-- Devolve (numero, protocolo) porque os dois andam juntos: o numero_processo
-- É o sequencial do protocolo. Quem inserir o processo grava ambos.
--
-- Sem lock e sem retry: a sequence garante unicidade do sequencial, e o
-- protocolo deriva dele. Simples e concorrente por construção — melhor que a
-- versão anterior, que pedia LOCK de tabela.
DROP FUNCTION IF EXISTS bss.gerar_protocolo();

CREATE OR REPLACE FUNCTION bss.gerar_protocolo(
    OUT numero BIGINT,
    OUT protocolo VARCHAR(9)
)
LANGUAGE plpgsql
AS $$
BEGIN
    numero := nextval('bss.seq_protocolo');
    IF numero > 99999 THEN
        RAISE EXCEPTION 'seq_protocolo estourou 5 digitos (%). '
                        'A mascara AAMM+5 nao comporta mais processos — '
                        'decidir com o cliente como evoluir.', numero;
    END IF;
    protocolo := to_char(NOW(), 'YYMM') || lpad(numero::text, 5, '0');
END $$;

COMMENT ON FUNCTION bss.gerar_protocolo() IS
    'Protocolo no formato real: AA+MM da criacao + 5 sequenciais globais '
    '(ex.: 260420817 = 2026-04 + 20817). Os 5 digitos sao o numero_processo, '
    'que continua a serie do legado via bss.seq_protocolo. '
    'Uso: SELECT * FROM bss.gerar_protocolo();';


-- Conferência:
--   SELECT protocolo, numero_processo, criado_em::date
--     FROM bss.processo_beneficio
--    WHERE protocolo IS NOT NULL ORDER BY numero_processo DESC LIMIT 5;
--   SELECT * FROM bss.gerar_protocolo();
