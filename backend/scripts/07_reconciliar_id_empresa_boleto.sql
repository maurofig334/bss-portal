-- ============================================================================
-- 07_reconciliar_id_empresa_boleto.sql
--
-- A migração legado→BSS deixou TODOS os 162.894 boletos com id_empresa=NULL.
-- Sindicato e demais campos foram populados; só a empresa ficou faltando.
--
-- Esta migration infere id_empresa a partir do primeiro boleto_item:
--   bs.boleto_item.id_trabalhador → bss.trabalhador.id_empresa_atual
--
-- Limitação conhecida: id_empresa_atual reflete só o ÚLTIMO vínculo do
-- trabalhador. Pra boletos muito antigos onde o trabalhador trocou de
-- empresa, o resultado pode estar incorreto. Pra a demo isso não importa
-- (boletos antigos já estão 'pago' ou 'cancelado'). Pode ser refinado depois
-- cruzando com bss.lista_mensal_item da mesma época, se necessário.
--
-- Idempotente: WHERE b.id_empresa IS NULL — se rodar 2x, segunda é no-op.
-- ============================================================================

BEGIN;

-- Estatísticas ANTES:
DO $$
DECLARE
    sem_empresa BIGINT;
    com_empresa BIGINT;
BEGIN
    SELECT COUNT(*) FILTER (WHERE id_empresa IS NULL),
           COUNT(*) FILTER (WHERE id_empresa IS NOT NULL)
      INTO sem_empresa, com_empresa
      FROM bss.boleto;
    RAISE NOTICE 'ANTES: sem_empresa=%, com_empresa=%', sem_empresa, com_empresa;
END $$;

-- UPDATE em batch:
-- DISTINCT ON (id_boleto) pega o primeiro boleto_item de cada boleto (ordenado por id).
UPDATE bss.boleto b
   SET id_empresa    = sub.id_empresa,
       atualizado_em = NOW()
  FROM (
    SELECT DISTINCT ON (bi.id_boleto)
           bi.id_boleto,
           t.id_empresa_atual AS id_empresa
      FROM bss.boleto_item bi
      JOIN bss.trabalhador t ON t.id = bi.id_trabalhador
     WHERE t.id_empresa_atual IS NOT NULL
     ORDER BY bi.id_boleto, bi.id
  ) sub
 WHERE b.id = sub.id_boleto
   AND b.id_empresa IS NULL;

-- Estatísticas DEPOIS:
DO $$
DECLARE
    sem_empresa BIGINT;
    com_empresa BIGINT;
BEGIN
    SELECT COUNT(*) FILTER (WHERE id_empresa IS NULL),
           COUNT(*) FILTER (WHERE id_empresa IS NOT NULL)
      INTO sem_empresa, com_empresa
      FROM bss.boleto;
    RAISE NOTICE 'DEPOIS: sem_empresa=%, com_empresa=%', sem_empresa, com_empresa;
END $$;

COMMIT;

-- Pós-validação manual:
--   SELECT COUNT(*) FROM bss.boleto WHERE id_empresa IS NULL;
--   -- Deve estar próximo de zero. Os que sobrarem são órfãos sem boleto_item
--   -- ou com trabalhador sem id_empresa_atual.
