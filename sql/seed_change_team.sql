-- ============================================================================
-- Motor Prescritivo PRB — Seed inicial Change Team (84 PRBs)
-- ============================================================================
-- Executar UMA VEZ após sql/motor_tables.sql ter criado lwsa.motor_change_team.
-- Schema: lwsa
--
-- COMPATIBILIDADE: Postgres 9.2+
--   - ON CONFLICT só existe em 9.5+. Bloco abaixo usa fallback PL/pgSQL com
--     IF NOT EXISTS por linha, que funciona em qualquer versão >= 9.2.
--   - Confirmar versão real do Postgres antes do go-live (rodar SELECT version()).
--
-- IDEMPOTÊNCIA: arquivo pode ser executado múltiplas vezes sem inserir duplicata.
--   Cada IF NOT EXISTS checa lwsa.motor_change_team.numero antes de inserir.
--   Rodar 2x não duplica nenhuma entrada.
--
-- GESTÃO: para REMOVER um PRB da Change Team, NÃO delete a linha — atualize:
--   UPDATE lwsa.motor_change_team
--   SET ativo = false, removido_em = NOW(), observacao = 'motivo'
--   WHERE numero = 'PRB0000XXX';
--
-- FONTE: lista canônica enviada por Emerson Ramos em 2026-06-05 (sessão GSD).
--   84 PRBs únicos (92 entradas originais, 8 duplicatas removidas).
--   Duplicatas removidas: PRB0055284, PRB0057465, PRB0064231, PRB0068344,
--                         PRB0068880, PRB0068961, PRB0070869, PRB0071758.
-- ============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0040838') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0040838', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0050697') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0050697', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0055284') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0055284', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0055680') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0055680', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0057465') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0057465', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0058097') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0058097', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0058099') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0058099', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0058309') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0058309', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0059289') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0059289', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0061147') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0061147', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0062616') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0062616', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0063538') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0063538', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0064231') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0064231', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0065149') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0065149', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0065286') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0065286', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0066814') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0066814', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0066895') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0066895', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0066900') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0066900', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0068236') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0068236', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0068319') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0068319', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0068344') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0068344', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0068547') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0068547', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0068880') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0068880', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0068888') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0068888', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0068958') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0068958', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0068961') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0068961', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0069348') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0069348', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0069465') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0069465', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0069543') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0069543', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0069607') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0069607', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0069725') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0069725', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0069746') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0069746', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0069777') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0069777', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0069940') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0069940', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0069964') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0069964', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0070155') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0070155', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0070280') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0070280', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0070421') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0070421', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0070457') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0070457', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0070718') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0070718', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0070735') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0070735', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0070861') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0070861', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0070862') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0070862', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0070869') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0070869', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0071148') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0071148', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0071149') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0071149', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0071228') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0071228', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0071253') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0071253', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0071604') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0071604', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0071643') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0071643', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0071665') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0071665', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0071758') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0071758', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0071783') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0071783', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0071791') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0071791', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0071961') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0071961', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0071972') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0071972', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0071979') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0071979', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0071995') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0071995', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0071997') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0071997', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0072049') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0072049', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0072062') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0072062', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0072088') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0072088', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0072104') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0072104', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0072152') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0072152', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0072175') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0072175', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0072228') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0072228', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0072260') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0072260', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0072274') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0072274', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0072340') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0072340', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0072363') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0072363', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0072365') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0072365', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0072400') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0072400', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0072524') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0072524', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0072583') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0072583', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0072648') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0072648', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0072691') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0072691', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0072705') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0072705', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0072729') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0072729', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0072738') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0072738', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0072925') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0072925', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0073006') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0073006', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0073011') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0073011', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0073051') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0073051', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0073198') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0073198', true, 'Força-tarefa Change Team — onda inicial 2026-06-05');
    END IF;
END $$;
