-- =============================================================================
-- Atualização da master Change Team — 2026-06-10
-- =============================================================================
-- Objetivo: sincronizar lwsa.motor_change_team com a nova lista de 84 PRBs
-- recebida da coordenação em 2026-06-10.
--
-- Estratégia: INCREMENTAL (preserva histórico). NÃO usa TRUNCATE.
--   1. Soft-delete (UPDATE ativo=false) dos PRBs ativos que NÃO estão na nova lista
--   2. Reativa (UPDATE ativo=true) dos PRBs que estão na nova lista mas estão inativos
--   3. INSERT dos PRBs que ainda não existem na master
--
-- Compatibilidade: Postgres 9.2.19 (Locaweb) — sem ON CONFLICT, sem MERGE.
-- Tudo dentro de 1 transação. ROLLBACK seguro até COMMIT explícito.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- ETAPA 0 — Criar tabela temporária com a nova lista canônica de 84 PRBs
-- -----------------------------------------------------------------------------
CREATE TEMP TABLE _change_team_nova_lista (numero varchar(20) PRIMARY KEY) ON COMMIT DROP;

INSERT INTO _change_team_nova_lista (numero) VALUES
    ('PRB0040838'), ('PRB0050697'), ('PRB0055284'), ('PRB0055680'),
    ('PRB0056922'), ('PRB0057465'), ('PRB0058097'), ('PRB0058099'),
    ('PRB0058309'), ('PRB0059289'), ('PRB0061147'), ('PRB0062476'),
    ('PRB0062616'), ('PRB0063538'), ('PRB0064231'), ('PRB0065149'),
    ('PRB0065286'), ('PRB0066814'), ('PRB0066895'), ('PRB0066900'),
    ('PRB0067965'), ('PRB0068236'), ('PRB0068319'), ('PRB0068344'),
    ('PRB0068547'), ('PRB0068880'), ('PRB0068888'), ('PRB0068958'),
    ('PRB0068961'), ('PRB0069348'), ('PRB0069465'), ('PRB0069543'),
    ('PRB0069607'), ('PRB0069725'), ('PRB0069746'), ('PRB0069777'),
    ('PRB0069940'), ('PRB0069964'), ('PRB0070155'), ('PRB0070280'),
    ('PRB0070421'), ('PRB0070457'), ('PRB0070718'), ('PRB0070735'),
    ('PRB0070861'), ('PRB0070862'), ('PRB0070869'), ('PRB0071148'),
    ('PRB0071149'), ('PRB0071228'), ('PRB0071253'), ('PRB0071604'),
    ('PRB0071643'), ('PRB0071665'), ('PRB0071758'), ('PRB0071783'),
    ('PRB0071791'), ('PRB0071961'), ('PRB0071979'), ('PRB0072062'),
    ('PRB0072088'), ('PRB0072104'), ('PRB0072152'), ('PRB0072175'),
    ('PRB0072228'), ('PRB0072260'), ('PRB0072274'), ('PRB0072311'),
    ('PRB0072340'), ('PRB0072363'), ('PRB0072365'), ('PRB0072400'),
    ('PRB0072524'), ('PRB0072583'), ('PRB0072648'), ('PRB0072691'),
    ('PRB0072705'), ('PRB0072729'), ('PRB0072925'), ('PRB0073006'),
    ('PRB0073011'), ('PRB0073051'), ('PRB0073198'), ('PRB0073350');

-- -----------------------------------------------------------------------------
-- ETAPA 1 — Diagnóstico ANTES da atualização (para audit log)
-- -----------------------------------------------------------------------------
SELECT 'ANTES' AS momento,
       (SELECT COUNT(*) FROM lwsa.motor_change_team WHERE ativo = true)  AS ativos_atual,
       (SELECT COUNT(*) FROM lwsa.motor_change_team WHERE ativo = false) AS inativos_atual,
       (SELECT COUNT(*) FROM _change_team_nova_lista)                    AS total_nova_lista;

-- Listar o que SAI (estava ativo, não está na nova lista)
SELECT 'SAI (soft-delete)' AS acao, m.numero, m.adicionado_em, m.observacao
FROM lwsa.motor_change_team m
WHERE m.ativo = true
  AND m.numero NOT IN (SELECT numero FROM _change_team_nova_lista)
ORDER BY m.numero;

-- Listar o que ENTRA (não existe na master)
SELECT 'ENTRA (insert novo)' AS acao, n.numero
FROM _change_team_nova_lista n
WHERE n.numero NOT IN (SELECT numero FROM lwsa.motor_change_team)
ORDER BY n.numero;

-- Listar o que REATIVA (estava inativo, voltou na nova lista)
SELECT 'REATIVA' AS acao, m.numero, m.removido_em, m.observacao
FROM lwsa.motor_change_team m
WHERE m.ativo = false
  AND m.numero IN (SELECT numero FROM _change_team_nova_lista)
ORDER BY m.numero;

-- =============================================================================
-- ⚠️ REVISE OS 3 SELECTs ACIMA ANTES DE CONTINUAR ⚠️
-- =============================================================================
-- Se as operações listadas estão corretas, prossiga executando o resto.
-- Se houver algo errado, execute ROLLBACK; e ajuste a nova lista.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- ETAPA 2 — Soft-delete dos PRBs que SAIRAM da força-tarefa
-- -----------------------------------------------------------------------------
UPDATE lwsa.motor_change_team
SET ativo = false,
    removido_em = NOW(),
    observacao = COALESCE(observacao || ' | ', '')
              || 'Removido em 2026-06-10 — atualização da lista master (não consta na onda 2026-06-10).'
WHERE ativo = true
  AND numero NOT IN (SELECT numero FROM _change_team_nova_lista);

-- -----------------------------------------------------------------------------
-- ETAPA 3 — Reativa PRBs que voltaram para a força-tarefa
-- -----------------------------------------------------------------------------
UPDATE lwsa.motor_change_team
SET ativo = true,
    removido_em = NULL,
    observacao = COALESCE(observacao || ' | ', '')
              || 'Reativado em 2026-06-10 — atualização da lista master.'
WHERE ativo = false
  AND numero IN (SELECT numero FROM _change_team_nova_lista);

-- -----------------------------------------------------------------------------
-- ETAPA 4 — INSERT dos PRBs novos (não existem ainda na master)
-- -----------------------------------------------------------------------------
INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
SELECT n.numero,
       true,
       'Adicionado em 2026-06-10 — atualização da lista master (onda Change Team 2026-06-10).'
FROM _change_team_nova_lista n
WHERE n.numero NOT IN (SELECT numero FROM lwsa.motor_change_team);

-- -----------------------------------------------------------------------------
-- ETAPA 5 — Diagnóstico DEPOIS da atualização
-- -----------------------------------------------------------------------------
SELECT 'DEPOIS' AS momento,
       (SELECT COUNT(*) FROM lwsa.motor_change_team WHERE ativo = true)  AS ativos_novo,
       (SELECT COUNT(*) FROM lwsa.motor_change_team WHERE ativo = false) AS inativos_novo,
       (SELECT COUNT(*) FROM _change_team_nova_lista)                    AS total_nova_lista,
       (SELECT COUNT(*) FROM lwsa.motor_change_team WHERE ativo = true)
       = (SELECT COUNT(*) FROM _change_team_nova_lista) AS bate_total;

-- Esperado: bate_total = true (84 ativos = 84 da nova lista)
-- Se vier false, algo deu errado — execute ROLLBACK e investigue.

-- =============================================================================
-- COMMIT manual — descomente a linha abaixo SOMENTE quando estiver tudo certo
-- =============================================================================
-- COMMIT;

-- Se quiser desfazer tudo:
-- ROLLBACK;
