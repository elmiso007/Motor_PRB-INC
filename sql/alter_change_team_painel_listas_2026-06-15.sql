-- =============================================================================
-- ALTER: motor_change_team_painel ganha 2 colunas (listas) — 2026-06-15
-- =============================================================================
-- Requisito da coordenação: além das CONTAGENS (qtd_incs_pos_resolucao,
-- qtd_prbs_novos_pos_resolucao), o chart "PRB Change Team" precisa exibir
-- os NÚMEROS reais das INCs/PRBs gerados após resolução — pra permitir
-- click-through ao SNow direto do painel.
--
-- Estratégia: ADITIVA. ALTER condicional (DO block) idempotente — pode rodar
-- múltiplas vezes sem erro. Linhas antigas ganham '[]'::json automaticamente.
--
-- Compatibilidade: Postgres 9.2.19 (Locaweb). Sem ON CONFLICT, sem jsonb.
-- =============================================================================

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='lwsa' AND table_name='motor_change_team_painel'
          AND column_name='incs_reincidentes'
    ) THEN
        ALTER TABLE lwsa.motor_change_team_painel
            ADD COLUMN incs_reincidentes json NOT NULL DEFAULT '[]'::json;
        RAISE NOTICE 'Coluna incs_reincidentes adicionada.';
    ELSE
        RAISE NOTICE 'Coluna incs_reincidentes já existe — nada a fazer.';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='lwsa' AND table_name='motor_change_team_painel'
          AND column_name='prbs_novos'
    ) THEN
        ALTER TABLE lwsa.motor_change_team_painel
            ADD COLUMN prbs_novos json NOT NULL DEFAULT '[]'::json;
        RAISE NOTICE 'Coluna prbs_novos adicionada.';
    ELSE
        RAISE NOTICE 'Coluna prbs_novos já existe — nada a fazer.';
    END IF;
END $$;

COMMENT ON COLUMN lwsa.motor_change_team_painel.incs_reincidentes IS
    'Array JSON com os números das INCs novas detectadas no mesmo (produto, servidor) após data_resolucao. Vazio se veredicto != REINCIDENCIA. Ex.: ["INC8847001","INC8847002"].';

COMMENT ON COLUMN lwsa.motor_change_team_painel.prbs_novos IS
    'Array JSON com os números dos PRBs novos abertos no mesmo (produto, servidor) após data_resolucao. Sinal grave: problema voltou em outra forma. Ex.: ["PRB0072001"].';

-- Verificação: confirmar que as 2 colunas existem com tipo json
SELECT column_name, data_type, column_default, is_nullable
FROM information_schema.columns
WHERE table_schema='lwsa'
  AND table_name='motor_change_team_painel'
  AND column_name IN ('incs_reincidentes', 'prbs_novos')
ORDER BY column_name;

-- Esperado: 2 linhas, ambas data_type='json', is_nullable='NO', default='[]'::json

-- =============================================================================
-- Se a verificação acima estiver OK, descomente:
-- =============================================================================
--COMMIT;

-- Para desfazer:
-- ROLLBACK;
