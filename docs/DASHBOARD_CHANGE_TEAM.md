# Painel de Acompanhamento — Guia Operacional

**Versão:** v1.0
**Audiência:** operadores, coordenação e times de suporte

---

## 1. Visão Geral

Este painel consolida o estado atual de um conjunto de PRBs relevantes para o
acompanhamento operacional e para a validação de entregas.

A ideia é materializar o estado desses PRBs em um snapshot SQL atualizado em ciclos
regulares, permitindo revisão de status, risco e recidiva sem depender de análise
manual dispersa.

---

## 2. Arquitetura

```
+-----------------------+   a cada 6h    +--------------------------+
| Windows Task Scheduler|--------------->| Motor-PRB-Validador.bat   |
+-----------------------+                +--------------------------+
                                                    |
                                                    v
                                     +------------------------------+
                                     | python validar_entregas.py   |
                                     | executar_validacao()         |
                                     |  ├── V3.1                   |
                                     |  └── BLOCO Acompanhamento   |
                                     +------------------------------+
                                                    |
                          SELECT WHERE ativo=true   v
+------------------------------+      +------------------------------+
| tabela master de PRBs        |<-----| processo de montagem do painel |
| (soft delete)                |      +------------------------------+
+------------------------------+                    |
                                                    v
                                     +------------------------------+
                                     | TRUNCATE + INSERT atômico    |
                                     | persistência do snapshot      |
                                     +------------------------------+
```

**Componentes principais:**
- **Tabela master:** lista rastreada dos PRBs relevantes.
- **Tabela snapshot:** visão materializada para consumo em dashboard/bot.
- **Entry-point:** `validar_entregas.py::executar_validacao`.
- **Toggle:** env var `CHANGE_TEAM_HABILITADO` (default `"true"`).

---

## 3. Como usar o painel

1. O validador executa em intervalos regulares.
2. A tabela mestre seleciona PRBs ativos.
3. O snapshot atualiza a visualização operacional.
4. O dashboard usa esse materialized view para apresentar a situação atual.

---

## 4. SQL Canônico

### Query A — Listagem completa

```sql
SELECT
    prb_id, descricao_curta, produto, servidor,
    status_snow, prioridade_atual, dias_em_aberto, grupo_designado,
    ultima_atualizacao,
    veredicto, data_resolucao, dias_pos_resolucao,
    qtd_incs_pos_resolucao, qtd_incs_pre_resolucao,
    delta_chamados_pct, qtd_prbs_novos_pos_resolucao,
    snapshot_em
FROM tabela_painel
ORDER BY (veredicto IS NULL) DESC,
         dias_em_aberto DESC NULLS LAST;
```

### Query B — Split aberto vs resolvido

```sql
-- Abertos
SELECT *
FROM tabela_painel
WHERE veredicto IS NULL
ORDER BY dias_em_aberto DESC NULLS LAST;

-- Resolvidos
SELECT *
FROM tabela_painel
WHERE veredicto IS NOT NULL
ORDER BY data_resolucao DESC;
```

### Query C — Big Number "X de Y resolvidos"

```sql
SELECT
    SUM(CASE WHEN veredicto IS NOT NULL THEN 1 ELSE 0 END) AS resolvidos,
    SUM(CASE WHEN veredicto IS NULL     THEN 1 ELSE 0 END) AS abertos,
    SUM(CASE WHEN veredicto = 'REINCIDENCIA' THEN 1 ELSE 0 END) AS reincidencias,
    COUNT(*) AS total,
    ROUND(
        100.0 * SUM(CASE WHEN veredicto IS NOT NULL THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0),
        1
    ) AS pct_resolvido
FROM tabela_painel;
```

---

## 5. Considerações de operação

- A execução periódica deve ser controlada por agendamento externo.
- A tabela snapshot deve se manter consistente com a carga principal.
- Quaisquer mudanças na regra de avaliação devem ser documentadas e validadas em ambiente de teste.
- O dashboard deve ser usado como visão operacional, não como único critério de decisão.

---

## 6. Checklist de qualidade

- Validar consulta de origem para PRBs relevantes
- Validar persistência do snapshot
- Validar regra de veredicto e recidiva
- Validar alertas finais e mensagens de notificação
- Revisar o painel após qualquer ajuste no modelo de priorização

```sql
SELECT
    COUNT(*) AS total_rows,
    MAX(snapshot_em) AS ultimo_snapshot,
    AGE(NOW(), MAX(snapshot_em)) AS idade_snapshot
FROM lwsa.motor_change_team_painel;
```

Esperado: `idade_snapshot < 7 hours` em regime normal (cadência 6h + tolerância). Se > 12h, investigar (ver §6 Troubleshooting).

---

## 5. Gestão da Lista Master

> ⚠️ **NUNCA use `DELETE FROM lwsa.motor_change_team`** — isso destrói o
> histórico. Use **soft delete** (`UPDATE ... SET ativo = false`).

A coluna chave da master é **`numero`** (varchar(20), UNIQUE) — corresponde
ao número do PRB no SNow (ex.: `PRB0072001`).

### Adicionar PRB à Change Team

```sql
INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
VALUES (
    'PRB0080123',
    true,
    'Adicionado em 2026-06-10 — força-tarefa onda 2: incidente crítico de CAL'
);
```

### Remover PRB (soft delete — preserva histórico)

```sql
UPDATE lwsa.motor_change_team
SET ativo = false,
    removido_em = NOW(),
    observacao = 'Removido em 2026-06-15 — PRB resolvido e validado, fim do acompanhamento dedicado'
WHERE numero = 'PRB0080123';
```

### Reativar PRB (caso voltar para Change Team depois)

```sql
UPDATE lwsa.motor_change_team
SET ativo = true,
    removido_em = NULL,
    observacao = 'Reativado em 2026-07-01 — reincidência detectada pelo validador'
WHERE numero = 'PRB0080123';
```

### Listar histórico (quem foi/é Change Team)

```sql
SELECT numero, ativo, adicionado_em, removido_em, observacao
FROM lwsa.motor_change_team
ORDER BY adicionado_em DESC;
```

### Corrigir INSERT errado (apenas se feito agora, antes do próximo snapshot)

```sql
-- USE COM CUIDADO: só dentro de janela curta após o INSERT, antes do próximo ciclo do validador.
DELETE FROM lwsa.motor_change_team
WHERE numero = 'PRB0099999'
  AND ativo = true
  AND adicionado_em > NOW() - INTERVAL '1 hour';
```

Para INSERTs antigos, sempre prefira soft delete + observação explicativa.

---

## 6. Troubleshooting

### PRB sumiu do painel mas está em master ativo

**Causa provável:** Pitfall 5 do RESEARCH — número da master não encontrado no SNow (digitação errada ou PRB deletado lá).

```sql
-- 1. Confirme que o PRB existe no SNow:
SELECT numero, descricao_curta, status, produto, servidor
FROM lwsa.service_now_problemas
WHERE numero = 'PRB0080123';
```

Se retornar vazio: o número da master está errado. Corrija via UPDATE:
```sql
UPDATE lwsa.motor_change_team SET numero = 'PRB0080124' WHERE numero = 'PRB0080123';
```

(Como `numero` é UNIQUE, garanta que o novo número não existe antes.)

### PRB com produto/servidor vazio no painel

**Causa provável:** Pitfall 3 — Change Team não preencheu o CI (configuration item) no SNow.

Ação operacional: pedir ao responsável do PRB para preencher os campos `produto` e `servidor` no SNow. O próximo ciclo do validador (até 6h) pega.

### Snapshot defasado (`snapshot_em` > 12h atrás)

**Causa provável:** validador rodou mas o bloco Change Team falhou ou está desligado.

Diagnóstico:
```bash
# Verificar log do dia (formato: validador-entrega-YYYY-MM-DD.log)
Get-Content "logs/validador-entrega-$(Get-Date -Format 'yyyy-MM-dd').log" -Tail 40
```

Procurar: `Falha no Painel Change Team`. Se aparecer, ler o traceback.

Verificar toggle:
```powershell
$env:CHANGE_TEAM_HABILITADO  # se "false" → reativar
```

### Snapshot tem 0 rows mas master tem N ativos

**Causa provável:** falha de conexão ou permissão.

- Confirme `PERSISTIR_NO_BANCO=true` (env var ou config.ini).
- Confirme que a conta do motor tem permissão de TRUNCATE na tabela painel.
- Rode manualmente: `python validar_entregas.py` em modo verbose e leia o log.

### TRUNCATE travado (timeout)

**Causa provável:** Pitfall 1 do RESEARCH — leitores Superset bloqueando a tabela.

Mitigações:
1. Aguardar 6h pelo próximo ciclo (validador retenta).
2. Matar sessões abertas no Superset que estão lendo a tabela.
3. Em último caso, ajustar `statement_timeout` ou redesign para PostgreSQL `LOCK TIMEOUT`.

### `dias_em_aberto = NULL`

**Causa intencional:** Pitfall 6 do RESEARCH — `aberto_em` veio NULL do SNow.

No chart, considere usar `COALESCE(dias_em_aberto, -1)` ou um filtro `IS NOT NULL` para visibilidade explícita.

---

## 7. Ações Abertas (Phase 2+)

**Concluído no go-live (2026-06-09):**

- [x] ✅ **Versão do Postgres validada:** 9.2.19 (compatível com seed PL/pgSQL).
- [x] ✅ **Chart "PRB Change Team"** no ar no Superset corporativo (D-08).
- [x] ✅ **Ownership das tabelas** transferido para a conta do motor (`automatizacoes`)
  via `ALTER TABLE ... OWNER TO automatizacoes` — gotcha documentado em §2.5.
- [x] ✅ **Backfill dos PRBs históricos** no espelho `lwsa.service_now_problems`
  via `projetos/problemas/backfill.py` — passou de 10/84 para 84/84 encontrados.
- [x] ✅ **Tempo de ciclo medido em PROD:** ~143s para validador c/ Change Team
  (51 candidatos V3.1 + 84 Change Team). Acima do TODO original "5s" — vale
  re-medir conforme volume crescer.

**Pendente:**

- [ ] **Comparar com chart "PRB em Vigilância"** existente no Superset e ajustar
  colunas D-06 do `motor_change_team_painel` se necessário (ação aberta do CONTEXT §Specifics).
- [ ] **Decidir se vale criar CLI** `gerenciar_change_team.py add/remove PRB0XXXX` (Open Question 4 do RESEARCH — alternativa ao SQL manual).
- [ ] **Habilitar Slack pra reincidências** Change Team — go-live detectou **6 reincidências**
  (PRB0055284 com 726 dias pós-resolução, 136 INCs novas; outros 5 PRBs com 11-32
  dias) que ficaram apenas no painel porque `[Slack desabilitado/sem token nem webhook]`.
  Configurar `SLACK_BOT_TOKEN` ou `SLACK_WEBHOOK_URL` no `config.ini` da VM.
- [ ] **Avaliar sync automático** com SNow via etiqueta/campo custom (CONTEXT §Deferred).
- [ ] **Adicionar coluna `ultima_atualizacao` real** — hoje sempre `NULL` por limitação do SNow (não há campo direto). Phase 2 pode investigar via `atualizacoes JSON`.
- [ ] **Continuar monitorando `duracao_ciclo_ms`** — validador c/ Change Team está em ~143s;
  se passar de 5min, investigar (provavelmente otimizar `_avaliar_prb` para PRBs Change Team).

---

## Referências

- [`sql/motor_tables.sql`](../sql/motor_tables.sql) — DDL das duas tabelas (seções 7 e 8)
- [`sql/seed_change_team.sql`](../sql/seed_change_team.sql) — seed inicial dos 84 PRBs
- [`change_team.py`](../change_team.py) — orquestrador Python (Phase 1 Plan 04)
- [`validar_entregas.py`](../validar_entregas.py) — entry-point com 3º bloco try/except (Phase 1 Plan 05)
- [`notifier_db.py`](../notifier_db.py) — `persistir_painel_change_team` (Phase 1 Plan 04)
- [`.planning/phases/01-painel-change-team-discovery/01-CONTEXT.md`](../.planning/phases/01-painel-change-team-discovery/01-CONTEXT.md) — D-01..D-08 originais
- [`.planning/phases/01-painel-change-team-discovery/01-RESEARCH.md`](../.planning/phases/01-painel-change-team-discovery/01-RESEARCH.md) — Pitfalls + Validation Architecture
