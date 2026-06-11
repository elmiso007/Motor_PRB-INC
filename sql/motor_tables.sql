-- ============================================================================
-- Motor Prescritivo PRB — DDL das tabelas de persistência
-- ============================================================================
-- Executar UMA VEZ no banco compartilhado (mesmo do locapredict + service_now).
-- Schema: lwsa
--
-- COMPATIBILIDADE: Postgres 9.2+
--   - Usa tipo `json` (não `jsonb`, que só existe em 9.4+).
--   - Indexes envolvidos em DO blocks (`CREATE INDEX IF NOT EXISTS` só existe em 9.5+).
--   - Migração futura para jsonb documentada em GLOSSARIO.md (seção
--     "Compatibilidade e migração de versões").
--
-- IDEMPOTÊNCIA: arquivo pode ser executado múltiplas vezes sem erro.
--   - CREATE TABLE IF NOT EXISTS funciona em 9.2+ (introduzido em 9.1).
--   - Indexes verificados via pg_indexes antes de criar.
--
-- MODELO: histórico com TTL (limpeza automática feita pelo motor a cada ciclo,
-- via DELETE FROM motor_execucao WHERE timestamp_utc < NOW() - INTERVAL '30 days').
-- ON DELETE CASCADE garante que clusters/prescrições/saúdes são apagados junto.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. motor_execucao — uma linha por ciclo (cabeça do agregado)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lwsa.motor_execucao (
    id                      serial PRIMARY KEY,
    timestamp_utc           timestamp with time zone NOT NULL,
    total_incs_lidas        int NOT NULL DEFAULT 0,
    total_chamados          int NOT NULL DEFAULT 0,
    total_clusters          int NOT NULL DEFAULT 0,
    total_prescricoes       int NOT NULL DEFAULT 0,
    total_saude_clientes    int NOT NULL DEFAULT 0,
    erros                   json NOT NULL DEFAULT '[]'::json,
    duracao_ciclo_ms        int
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='lwsa' AND indexname='idx_motor_execucao_timestamp') THEN
        CREATE INDEX idx_motor_execucao_timestamp ON lwsa.motor_execucao(timestamp_utc DESC);
    END IF;
END $$;

COMMENT ON TABLE  lwsa.motor_execucao IS 'Motor Prescritivo PRB — cabeça de cada ciclo (1 linha por execução).';
COMMENT ON COLUMN lwsa.motor_execucao.timestamp_utc IS 'Início do ciclo em UTC tz-aware.';
COMMENT ON COLUMN lwsa.motor_execucao.erros IS 'Lista de strings de erro do ciclo (json array).';
COMMENT ON COLUMN lwsa.motor_execucao.duracao_ciclo_ms IS 'Tempo total de execução em milissegundos (proxy de saúde do motor).';


-- ----------------------------------------------------------------------------
-- 2. motor_cluster — N por execução (clusters semânticos formados)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lwsa.motor_cluster (
    id                          serial PRIMARY KEY,
    execucao_id                 int NOT NULL REFERENCES lwsa.motor_execucao(id) ON DELETE CASCADE,
    cluster_id                  varchar(64) NOT NULL,
    nome                        text NOT NULL,
    produto                     text,
    servidor                    text,
    qtd_incs                    int NOT NULL,
    score_criticidade           numeric(4,3) NOT NULL,
    score_ineficiencia          numeric(4,3) NOT NULL,
    tem_solucao_contorno        boolean NOT NULL,
    tempo_contorno_min_medio    int NOT NULL DEFAULT 0,
    chamados_relacionados       int NOT NULL DEFAULT 0,
    cis_recorrentes_15d         json NOT NULL DEFAULT '[]'::json,
    termos_dominantes           json NOT NULL DEFAULT '[]'::json,
    inc_ids                     json NOT NULL DEFAULT '[]'::json
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='lwsa' AND indexname='idx_motor_cluster_execucao') THEN
        CREATE INDEX idx_motor_cluster_execucao ON lwsa.motor_cluster(execucao_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='lwsa' AND indexname='idx_motor_cluster_produto') THEN
        CREATE INDEX idx_motor_cluster_produto ON lwsa.motor_cluster(produto);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='lwsa' AND indexname='idx_motor_cluster_servidor') THEN
        CREATE INDEX idx_motor_cluster_servidor ON lwsa.motor_cluster(servidor);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='lwsa' AND indexname='idx_motor_cluster_criticidade') THEN
        CREATE INDEX idx_motor_cluster_criticidade ON lwsa.motor_cluster(score_criticidade DESC);
    END IF;
END $$;

COMMENT ON TABLE  lwsa.motor_cluster IS 'Clusters semânticos formados por TF-IDF + DBSCAN no analyzer.';
COMMENT ON COLUMN lwsa.motor_cluster.cluster_id IS 'ID interno do motor (ex.: "cluster-0", "singleton-INC0001234"). NÃO é PK.';
COMMENT ON COLUMN lwsa.motor_cluster.score_criticidade IS '0.000-1.000. Combinação ponderada de 4 sinais (volume, indisp, sem contorno, recorrência CI).';
COMMENT ON COLUMN lwsa.motor_cluster.score_ineficiencia IS '0.000-1.000. Composição volume (0.6) + velocidade (0.4) de updates.';
COMMENT ON COLUMN lwsa.motor_cluster.inc_ids IS 'Array de inc_ids do cluster (sem duplicar dados — INCs vivem em service_now_incidentes).';


-- ----------------------------------------------------------------------------
-- 3. motor_prescricao — N por execução (saída do rules_engine)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lwsa.motor_prescricao (
    id                      serial PRIMARY KEY,
    execucao_id             int NOT NULL REFERENCES lwsa.motor_execucao(id) ON DELETE CASCADE,
    cluster_id              varchar(64) NOT NULL,
    acao                    varchar(30) NOT NULL,
    urgencia                varchar(20) NOT NULL,
    prioridade_sugerida     varchar(5) NOT NULL,
    prb_existente           varchar(20),
    prioridade_atual_prb    varchar(5),
    sugestao_repriorizacao  text,
    justificativa           json NOT NULL DEFAULT '[]'::json
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='lwsa' AND indexname='idx_motor_prescricao_execucao') THEN
        CREATE INDEX idx_motor_prescricao_execucao ON lwsa.motor_prescricao(execucao_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='lwsa' AND indexname='idx_motor_prescricao_urgencia') THEN
        CREATE INDEX idx_motor_prescricao_urgencia ON lwsa.motor_prescricao(urgencia);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='lwsa' AND indexname='idx_motor_prescricao_prb') THEN
        CREATE INDEX idx_motor_prescricao_prb ON lwsa.motor_prescricao(prb_existente) WHERE prb_existente IS NOT NULL;
    END IF;
END $$;

COMMENT ON TABLE  lwsa.motor_prescricao IS 'Prescrições do rules_engine — o que o motor sugere para cada cluster.';
COMMENT ON COLUMN lwsa.motor_prescricao.acao IS 'ABRIR_PRB | REPRIORIZAR_PRB | MONITORAR | NENHUMA.';
COMMENT ON COLUMN lwsa.motor_prescricao.urgencia IS 'CRITICA | ALTA | MEDIA | BAIXA | PLANEJADO.';
COMMENT ON COLUMN lwsa.motor_prescricao.justificativa IS 'Lista de bullets auditáveis (json array). Por que o motor decidiu.';


-- ----------------------------------------------------------------------------
-- 4. motor_saude_cliente — N por execução (avaliações por cliente)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lwsa.motor_saude_cliente (
    id                          serial PRIMARY KEY,
    execucao_id                 int NOT NULL REFERENCES lwsa.motor_execucao(id) ON DELETE CASCADE,
    cliente_login               varchar(255) NOT NULL,
    qtd_incs_periodo            int NOT NULL DEFAULT 0,
    qtd_chamados_periodo        int NOT NULL DEFAULT 0,
    severidade_media            numeric(4,3) NOT NULL DEFAULT 0,
    alerta_recorrencia_alta     boolean NOT NULL DEFAULT false,
    linha_do_tempo              json NOT NULL DEFAULT '[]'::json
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='lwsa' AND indexname='idx_motor_saude_execucao') THEN
        CREATE INDEX idx_motor_saude_execucao ON lwsa.motor_saude_cliente(execucao_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='lwsa' AND indexname='idx_motor_saude_cliente') THEN
        CREATE INDEX idx_motor_saude_cliente ON lwsa.motor_saude_cliente(cliente_login);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='lwsa' AND indexname='idx_motor_saude_alerta') THEN
        CREATE INDEX idx_motor_saude_alerta ON lwsa.motor_saude_cliente(alerta_recorrencia_alta) WHERE alerta_recorrencia_alta = true;
    END IF;
END $$;

COMMENT ON TABLE  lwsa.motor_saude_cliente IS 'Saúde do cliente — avaliação por cliente em cada ciclo.';
COMMENT ON COLUMN lwsa.motor_saude_cliente.severidade_media IS '0.000-1.000. Média ponderada das prioridades (P1=1.0, P5=0.0).';
COMMENT ON COLUMN lwsa.motor_saude_cliente.alerta_recorrencia_alta IS 'True se >= 3 INCs E tem INC nos últimos 7 dias (anti alert-fatigue).';
COMMENT ON COLUMN lwsa.motor_saude_cliente.linha_do_tempo IS 'Eventos cronológicos consolidados (ServiceNow + chamados Locaweb/Kinghost).';


-- ----------------------------------------------------------------------------
-- 5. motor_validacao_entrega — N por execução (prisma retrospectivo)
-- ----------------------------------------------------------------------------
-- Veredicto sobre PRBs já entregues pelo Change Team. Roda separado do ciclo
-- preventivo (entry-point validar_entregas.py), mas grava na mesma motor_execucao.
CREATE TABLE IF NOT EXISTS lwsa.motor_validacao_entrega (
    id                          serial PRIMARY KEY,
    execucao_id                 int NOT NULL REFERENCES lwsa.motor_execucao(id) ON DELETE CASCADE,
    prb_id                      varchar(50) NOT NULL,
    descricao_curta             varchar(500),
    produto                     varchar(255),
    servidor                    varchar(255),
    status_prb                  varchar(100),
    data_resolucao              timestamp with time zone NOT NULL,
    dias_pos_resolucao          int NOT NULL,
    qtd_incs_pos_resolucao      int NOT NULL DEFAULT 0,
    veredicto                   varchar(30) NOT NULL,
    incs_reincidentes           json NOT NULL DEFAULT '[]'::json
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='lwsa' AND indexname='idx_motor_validacao_execucao') THEN
        CREATE INDEX idx_motor_validacao_execucao ON lwsa.motor_validacao_entrega(execucao_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='lwsa' AND indexname='idx_motor_validacao_prb') THEN
        CREATE INDEX idx_motor_validacao_prb ON lwsa.motor_validacao_entrega(prb_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='lwsa' AND indexname='idx_motor_validacao_veredicto') THEN
        CREATE INDEX idx_motor_validacao_veredicto ON lwsa.motor_validacao_entrega(veredicto);
    END IF;
END $$;

COMMENT ON TABLE  lwsa.motor_validacao_entrega IS 'Validação retrospectiva de PRBs entregues pelo Change Team (prisma do ValidadorEntrega).';
COMMENT ON COLUMN lwsa.motor_validacao_entrega.data_resolucao IS 'data_encerrado do PRB no ServiceNow (quando o Change Team marcou como entregue).';
COMMENT ON COLUMN lwsa.motor_validacao_entrega.dias_pos_resolucao IS 'Quantos dias se passaram entre data_resolucao e o ciclo atual.';
COMMENT ON COLUMN lwsa.motor_validacao_entrega.veredicto IS 'REINCIDENCIA | ENTREGA_VALIDADA | INCONCLUSIVO.';
COMMENT ON COLUMN lwsa.motor_validacao_entrega.incs_reincidentes IS 'Lista de INCs novas (numero, prioridade, data) que apareceram no mesmo (produto, servidor) após a resolução.';

-- ----------------------------------------------------------------------------
-- ALTER condicional: adicionar 8 colunas em motor_validacao_entrega
-- ----------------------------------------------------------------------------
-- Contexto + volumetria pré + delta de chamados pré/pós (V2 do ValidadorEntrega,
-- aplicado em 2026-06-02). Bloco DO com check em information_schema para
-- compatibilidade com Postgres 9.2/9.3 (sem IF NOT EXISTS de coluna).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='lwsa' AND table_name='motor_validacao_entrega'
          AND column_name='grupo_designado'
    ) THEN
        ALTER TABLE lwsa.motor_validacao_entrega
            ADD COLUMN grupo_designado varchar(255);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='lwsa' AND table_name='motor_validacao_entrega'
          AND column_name='data_abertura_prb'
    ) THEN
        ALTER TABLE lwsa.motor_validacao_entrega
            ADD COLUMN data_abertura_prb timestamp with time zone;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='lwsa' AND table_name='motor_validacao_entrega'
          AND column_name='qtd_incs_pre_resolucao'
    ) THEN
        ALTER TABLE lwsa.motor_validacao_entrega
            ADD COLUMN qtd_incs_pre_resolucao int NOT NULL DEFAULT 0;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='lwsa' AND table_name='motor_validacao_entrega'
          AND column_name='clientes_unicos_pre'
    ) THEN
        ALTER TABLE lwsa.motor_validacao_entrega
            ADD COLUMN clientes_unicos_pre int NOT NULL DEFAULT 0;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='lwsa' AND table_name='motor_validacao_entrega'
          AND column_name='categorias_pre'
    ) THEN
        ALTER TABLE lwsa.motor_validacao_entrega
            ADD COLUMN categorias_pre int NOT NULL DEFAULT 0;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='lwsa' AND table_name='motor_validacao_entrega'
          AND column_name='chamados_pre'
    ) THEN
        ALTER TABLE lwsa.motor_validacao_entrega
            ADD COLUMN chamados_pre int NOT NULL DEFAULT 0;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='lwsa' AND table_name='motor_validacao_entrega'
          AND column_name='chamados_pos'
    ) THEN
        ALTER TABLE lwsa.motor_validacao_entrega
            ADD COLUMN chamados_pos int NOT NULL DEFAULT 0;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='lwsa' AND table_name='motor_validacao_entrega'
          AND column_name='delta_chamados_pct'
    ) THEN
        ALTER TABLE lwsa.motor_validacao_entrega
            ADD COLUMN delta_chamados_pct numeric(8,3) NOT NULL DEFAULT 0.0;
    END IF;

    -- Rastreamento de PRBs novos pós-resolução (requisito de coordenação 2026-06-02).
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='lwsa' AND table_name='motor_validacao_entrega'
          AND column_name='qtd_prbs_novos_pos_resolucao'
    ) THEN
        ALTER TABLE lwsa.motor_validacao_entrega
            ADD COLUMN qtd_prbs_novos_pos_resolucao int NOT NULL DEFAULT 0;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='lwsa' AND table_name='motor_validacao_entrega'
          AND column_name='prbs_novos'
    ) THEN
        ALTER TABLE lwsa.motor_validacao_entrega
            ADD COLUMN prbs_novos json NOT NULL DEFAULT '[]'::json;
    END IF;

    -- Times impactados via dynamics.chamados.equipeproprietaria
    -- (requisito de coordenação 2026-06-03). Top N equipes proprietárias
    -- dos chamados vinculados pré/pós + % de redução por equipe.
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='lwsa' AND table_name='motor_validacao_entrega'
          AND column_name='equipes_impactadas_pre'
    ) THEN
        ALTER TABLE lwsa.motor_validacao_entrega
            ADD COLUMN equipes_impactadas_pre json NOT NULL DEFAULT '{}'::json;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='lwsa' AND table_name='motor_validacao_entrega'
          AND column_name='equipes_impactadas_pos'
    ) THEN
        ALTER TABLE lwsa.motor_validacao_entrega
            ADD COLUMN equipes_impactadas_pos json NOT NULL DEFAULT '{}'::json;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='lwsa' AND table_name='motor_validacao_entrega'
          AND column_name='equipes_delta_pct'
    ) THEN
        ALTER TABLE lwsa.motor_validacao_entrega
            ADD COLUMN equipes_delta_pct json NOT NULL DEFAULT '{}'::json;
    END IF;
END $$;

COMMENT ON COLUMN lwsa.motor_validacao_entrega.qtd_incs_pre_resolucao IS 'INCs no mesmo (produto, servidor) nos JANELA_VOLUMETRIA_PRE_DIAS antes de data_resolucao.';
COMMENT ON COLUMN lwsa.motor_validacao_entrega.delta_chamados_pct IS '(chamados_pos - chamados_pre) / chamados_pre. Match V3 por dynamics.chamados.prb / .inc.';
COMMENT ON COLUMN lwsa.motor_validacao_entrega.qtd_prbs_novos_pos_resolucao IS 'PRBs NOVOS abertos no mesmo (produto, servidor) após data_resolucao. Sinal de problema que voltou em outra forma.';
COMMENT ON COLUMN lwsa.motor_validacao_entrega.prbs_novos IS 'Array JSON com os numeros dos PRBs novos (ex.: ["PRB0012345"]).';
COMMENT ON COLUMN lwsa.motor_validacao_entrega.equipes_impactadas_pre IS 'Top N times Locaweb (dynamics.chamados.equipeproprietaria) com chamados vinculados ao PRB/INCs pré-resolução: {"equipe": qtd}. Espelhado em forma relacional na tabela motor_validacao_entrega_equipe (preferida para dashboards/joins).';
COMMENT ON COLUMN lwsa.motor_validacao_entrega.equipes_impactadas_pos IS 'Mesmas equipes do pre — contagem na janela pós-resolução (0 = parou de chamar): {"equipe": qtd}. Espelhado em motor_validacao_entrega_equipe.';
COMMENT ON COLUMN lwsa.motor_validacao_entrega.equipes_delta_pct IS '% de redução por equipe: {"equipe": -0.75}. Negativo = caiu, +N = subiu, -1.0 = zerou. Espelhado em motor_validacao_entrega_equipe.';


-- ----------------------------------------------------------------------------
-- 6. motor_validacao_entrega_equipe — N equipes por validação (V3.1, relacional)
-- ----------------------------------------------------------------------------
-- Espelho relacional das 3 colunas json equipes_* de motor_validacao_entrega.
-- Pensado para consumo de dashboards (Apache Superset, Power BI, Metabase) que
-- preferem SQL relacional puro a explosão de json em runtime. 1 linha por
-- (validação, equipe). FK + ON DELETE CASCADE acompanha o TTL do pai.
--
-- Volume típico: até TOP_EQUIPES_IMPACTADAS (7) linhas por PRB validado.
-- Por ciclo: 10 PRBs * 7 equipes = ~70 linhas. Irrelevante.
CREATE TABLE IF NOT EXISTS lwsa.motor_validacao_entrega_equipe (
    id              serial PRIMARY KEY,
    validacao_id    int NOT NULL REFERENCES lwsa.motor_validacao_entrega(id) ON DELETE CASCADE,
    equipe          varchar(255) NOT NULL,
    qtd_pre         int NOT NULL DEFAULT 0,
    qtd_pos         int NOT NULL DEFAULT 0,
    delta_pct       numeric(8,3) NOT NULL DEFAULT 0.0
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='lwsa' AND indexname='idx_motor_val_eq_validacao') THEN
        CREATE INDEX idx_motor_val_eq_validacao ON lwsa.motor_validacao_entrega_equipe(validacao_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='lwsa' AND indexname='idx_motor_val_eq_equipe') THEN
        CREATE INDEX idx_motor_val_eq_equipe ON lwsa.motor_validacao_entrega_equipe(equipe);
    END IF;
END $$;

COMMENT ON TABLE  lwsa.motor_validacao_entrega_equipe IS 'Espelho relacional das colunas json equipes_* de motor_validacao_entrega (V3.1). 1 linha por (validação, equipe). Preferida para dashboards.';
COMMENT ON COLUMN lwsa.motor_validacao_entrega_equipe.equipe IS 'dynamics.chamados.equipeproprietaria. Valores ''<sem-equipe>'' representam chamados sem time atribuído.';
COMMENT ON COLUMN lwsa.motor_validacao_entrega_equipe.qtd_pre IS 'Chamados vinculados pré-resolução na janela JANELA_CHAMADOS_DELTA_DIAS.';
COMMENT ON COLUMN lwsa.motor_validacao_entrega_equipe.qtd_pos IS 'Chamados vinculados pós-resolução. 0 = equipe parou de chamar.';
COMMENT ON COLUMN lwsa.motor_validacao_entrega_equipe.delta_pct IS '(qtd_pos - qtd_pre) / qtd_pre, arredondado a 3 casas. -1.0 = zerou.';


-- ----------------------------------------------------------------------------
-- 7. motor_change_team — lista master soft-deleted (D-01, Phase 1)
-- ----------------------------------------------------------------------------
-- Catálogo dos PRBs da force-task interdisciplinar "Change Team" (~84 entradas
-- no momento). Soft delete via `ativo` + `removido_em` preserva auditoria
-- ("esse PRB foi da Change Team em algum momento?"). Gestão manual via SQL
-- direto até decisão futura sobre CRUD CLI.
--
-- Para REMOVER um PRB da Change Team, NÃO delete a linha — atualize:
--   UPDATE lwsa.motor_change_team
--   SET ativo = false, removido_em = NOW(), observacao = 'motivo'
--   WHERE numero = 'PRB0000XXX';
CREATE TABLE IF NOT EXISTS lwsa.motor_change_team (
    id              serial PRIMARY KEY,
    numero          varchar(20) NOT NULL UNIQUE,
    ativo           boolean NOT NULL DEFAULT true,
    adicionado_em   timestamp with time zone NOT NULL DEFAULT NOW(),
    removido_em     timestamp with time zone,
    observacao      text
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='lwsa' AND indexname='idx_motor_change_team_numero') THEN
        CREATE INDEX idx_motor_change_team_numero ON lwsa.motor_change_team(numero);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='lwsa' AND indexname='idx_motor_change_team_ativos') THEN
        CREATE INDEX idx_motor_change_team_ativos ON lwsa.motor_change_team(numero) WHERE ativo = true;
    END IF;
END $$;

COMMENT ON TABLE  lwsa.motor_change_team IS 'Lista master da force-task Change Team — PRBs sob acompanhamento dedicado. Soft delete via ativo/removido_em.';
COMMENT ON COLUMN lwsa.motor_change_team.numero IS 'Identificador do PRB no ServiceNow (ex.: "PRB0072001"). UNIQUE — uma linha por PRB.';
COMMENT ON COLUMN lwsa.motor_change_team.ativo IS 'true = aparece no painel; false = histórico (mantém auditoria).';
COMMENT ON COLUMN lwsa.motor_change_team.observacao IS 'Texto livre — motivo da entrada/saída, link interno, etc.';


-- ----------------------------------------------------------------------------
-- 8. motor_change_team_painel — snapshot materializado (D-04 / D-05 / D-06)
-- ----------------------------------------------------------------------------
-- Reescrita inteira a cada execução do ValidadorEntrega (6h) via TRUNCATE+INSERT
-- atômico em notifier_db.persistir_painel_change_team. Sem FK para motor_execucao
-- porque snapshot é independente do ciclo (sem versionamento — só estado atual
-- interessa). Consumido pelo chart "PRB Change Team" no Superset corporativo (D-07).
--
-- ATENÇÃO (T-01-02): TRUNCATE pode aguardar leitores Superset (ACCESS EXCLUSIVE
-- lock). Cadência 6h tolera espera curta. Sem CASCADE — tabela é folha.
-- RESTART IDENTITY zera o serial PK a cada ciclo.
CREATE TABLE IF NOT EXISTS lwsa.motor_change_team_painel (
    id                              serial PRIMARY KEY,
    prb_id                          varchar(20) NOT NULL,
    descricao_curta                 varchar(500),
    produto                         varchar(255),
    servidor                        varchar(255),
    status_snow                     varchar(100),
    prioridade_atual                varchar(5),
    dias_em_aberto                  int,
    grupo_designado                 varchar(255),
    ultima_atualizacao              timestamp with time zone,
    -- Só preenchidos quando PRB está resolvido (D-06):
    veredicto                       varchar(30),
    data_resolucao                  timestamp with time zone,
    dias_pos_resolucao              int,
    qtd_incs_pos_resolucao          int,
    qtd_incs_pre_resolucao          int,
    delta_chamados_pct              numeric(8,3),
    qtd_prbs_novos_pos_resolucao    int,
    -- Auditoria:
    snapshot_em                     timestamp with time zone NOT NULL DEFAULT NOW()
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='lwsa' AND indexname='idx_motor_ct_painel_prb') THEN
        CREATE INDEX idx_motor_ct_painel_prb ON lwsa.motor_change_team_painel(prb_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='lwsa' AND indexname='idx_motor_ct_painel_status') THEN
        CREATE INDEX idx_motor_ct_painel_status ON lwsa.motor_change_team_painel(status_snow);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='lwsa' AND indexname='idx_motor_ct_painel_veredicto') THEN
        CREATE INDEX idx_motor_ct_painel_veredicto ON lwsa.motor_change_team_painel(veredicto) WHERE veredicto IS NOT NULL;
    END IF;
END $$;

COMMENT ON TABLE  lwsa.motor_change_team_painel IS 'Snapshot materializado dos PRBs Change Team. Reescrito inteiro a cada 6h pelo ValidadorEntrega (TRUNCATE+INSERT atômico). Consumido pelo chart "PRB Change Team" no Superset.';
COMMENT ON COLUMN lwsa.motor_change_team_painel.veredicto IS 'NULL para PRBs ainda abertos; REINCIDENCIA/ENTREGA_VALIDADA/INCONCLUSIVO para resolvidos.';
COMMENT ON COLUMN lwsa.motor_change_team_painel.snapshot_em IS 'Timestamp de quando este snapshot foi gravado — monitora frescor do painel.';


-- ----------------------------------------------------------------------------
-- ALTER condicional: adicionar coluna total_validacoes_entrega em motor_execucao
-- ----------------------------------------------------------------------------
-- Tabela motor_execucao já existe em produção (foi criada em DDL anterior).
-- Adicionamos a coluna com ALTER TABLE — IF NOT EXISTS de coluna só existe em
-- Postgres 9.6+, então usamos DO block com check em information_schema (9.2+).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'lwsa'
          AND table_name = 'motor_execucao'
          AND column_name = 'total_validacoes_entrega'
    ) THEN
        ALTER TABLE lwsa.motor_execucao
            ADD COLUMN total_validacoes_entrega int NOT NULL DEFAULT 0;
    END IF;
END $$;


-- ============================================================================
-- Verificação pós-execução (executar separadamente)
-- ============================================================================
-- Confirme que 5 tabelas foram criadas:
--   SELECT tablename FROM pg_tables WHERE schemaname='lwsa' AND tablename LIKE 'motor_%';
--
-- Confirme que 13 indexes foram criados:
--   SELECT indexname FROM pg_indexes WHERE schemaname='lwsa' AND indexname LIKE 'idx_motor%';
--
-- Confirme que motor_execucao tem 10 colunas (incluindo total_validacoes_entrega):
--   SELECT column_name FROM information_schema.columns
--   WHERE table_schema='lwsa' AND table_name='motor_execucao' ORDER BY ordinal_position;
--
-- ============================================================================
-- Queries de exemplo (não executadas, apenas referência)
-- ============================================================================
-- Tendência de alertas críticos por dia na última semana:
--   SELECT DATE_TRUNC('day', e.timestamp_utc) AS dia, COUNT(*) AS qtd_criticos
--   FROM lwsa.motor_execucao e
--   JOIN lwsa.motor_prescricao p ON p.execucao_id = e.id
--   WHERE p.urgencia = 'CRITICA' AND e.timestamp_utc >= NOW() - INTERVAL '7 days'
--   GROUP BY dia ORDER BY dia;
--
-- Cleanup TTL (chamado pelo motor a cada ciclo):
--   DELETE FROM lwsa.motor_execucao WHERE timestamp_utc < NOW() - INTERVAL '30 days';
-- ============================================================================