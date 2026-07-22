-- ============================================================================
-- 20_mensagem_leitura.sql — marca d'água de leitura do canal de mensagens
-- ============================================================================
--
-- POR QUE
-- -------
-- O sino do ANALISTA não precisa disto: "cliente aguardando resposta" é
-- derivado de quem escreveu a última mensagem, e apaga sozinho quando a BSS
-- responde. Não há o que marcar.
--
-- O sino do CLIENTE é diferente. Se ele acendesse com "a última mensagem é da
-- BSS", ficaria aceso PARA SEMPRE depois de qualquer resposta — porque o
-- cliente muitas vezes lê, entende e não precisa responder nada. Sino que
-- nunca apaga vira paisagem, e aí ninguém olha nem quando importa.
--
-- Então: uma marca d'água por usuário por processo. "Li até aqui."
--
-- MODELO
-- ------
-- Uma linha por (usuário, processo), atualizada quando ele abre a aba de
-- mensagens. Não é uma linha por mensagem lida — isso seria N vezes maior
-- pra responder exatamente a mesma pergunta.
--
-- Serve pros dois lados: hoje só o cliente usa, mas quando quisermos "não
-- lidas" pro analista, a tabela já está aqui.
--
-- Aplicar:
--     venv/bin/python -m scripts.aplicar_sql scripts/20_mensagem_leitura.sql
-- ============================================================================

CREATE TABLE IF NOT EXISTS bss.processo_mensagem_leitura (
    id_usuario   INT         NOT NULL,
    id_processo  BIGINT      NOT NULL REFERENCES bss.processo_beneficio(id) ON DELETE CASCADE,
    -- Timestamp da mensagem mais recente que este usuário já viu neste
    -- processo. Comparado com criado_em das mensagens pra achar as novas.
    lido_ate     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id_usuario, id_processo)
);

-- O sino do cliente pergunta "quais dos MEUS processos têm mensagem nova?",
-- ou seja, varre por usuário. A PK (id_usuario, id_processo) já serve —
-- índice adicional só por id_processo é pra ir no sentido contrário
-- ("quem leu este processo?"), que é o caso do futuro "visto por".
CREATE INDEX IF NOT EXISTS idx_pml_processo
    ON bss.processo_mensagem_leitura (id_processo);

COMMENT ON TABLE bss.processo_mensagem_leitura IS
    'Marca d''água de leitura do canal de mensagens. Uma linha por (usuário, processo).';
COMMENT ON COLUMN bss.processo_mensagem_leitura.lido_ate IS
    'criado_em da mensagem mais recente já vista por este usuário neste processo.';
