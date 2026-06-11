# Painel Change Team — Guia Operacional

**Versão:** v1.0 (Phase 1, 2026-06-05)
**Audiência:** força-tarefa Change Team + operador do Motor PRB-INC + DBA/PO
**Fonte canônica das decisões:** [`.planning/phases/01-painel-change-team-discovery/01-CONTEXT.md`](../.planning/phases/01-painel-change-team-discovery/01-CONTEXT.md) (D-01..D-08)

---

## 1. Visão Geral

A **Change Team** é uma força-tarefa interdisciplinar da Locaweb dedicada à
resolução de ~84 PRBs específicos (lista deduplicada da onda inicial de
2026-06-05 — 8 duplicatas removidas das 92 entries originais).

O **Painel Change Team** materializa o estado atual desses PRBs num snapshot
SQL atualizado a cada 6h, consumido via chart **"PRB Change Team"** no
Superset corporativo.

**Resumo das decisões locked (Phase 1, CONTEXT.md):**

| ID | Decisão | Implementação |
|---|---|---|
| D-01 | Lista master em tabela com soft delete | `lwsa.motor_change_team` (ativo + removido_em) |
| D-02 | Entry-point é o ValidadorEntrega (6h) | `Motor-PRB-Validador.bat` → `validar_entregas.py` |
| D-03 | Query separada SEM janela temporal | `extractor.listar_prbs_por_numero` |
| D-04 | TRUNCATE+INSERT atômico | `notifier_db.persistir_painel_change_team` |
| D-05 | Colunas para PRBs abertos | 9 campos + auditoria em `motor_change_team_painel` |
| D-06 | Colunas para PRBs resolvidos | D-05 + 7 sinais V3.1 (reusa `_avaliar_prb`, CON-012 LOCKED) |
| D-07 | Consumo via Superset corporativo (chart manual) | Setup descrito na §3 |
| D-08 | Feature = `change_team`; Chart = "PRB Change Team" | Aplicado em código, tabela e UI |

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
                                     |  ├── V3.1 (CON-012 LOCKED)    |
                                     |  └── BLOCO Change Team:       |
                                     |       try/except + lazy import|
                                     +------------------------------+
                                                    |
                          SELECT WHERE ativo=true   v
+------------------------------+      +------------------------------+
| lwsa.motor_change_team       |<-----| change_team.gerar_painel_... |
| (master — soft delete)       |      +------------------------------+
+------------------------------+                    |
                                                    v
                          listar_prbs_por_numero    +----------------+
+------------------------------+    SEM JANELA      | extractor.py   |
| lwsa.service_now_problemas   |<-----------------> | (FonteInc)     |
+------------------------------+                    +----------------+
                                                    |
                                                    v
                                     +------------------------------+
                                     | TRUNCATE + INSERT atômico    |
                                     | notifier_db.persistir_painel |
                                     +------------------------------+
                                                    |
                                                    v
+------------------------------+    SQL nativo     +----------------+
| lwsa.motor_change_team_painel|<-------------------| Superset chart |
| (snapshot reescrito a cada   |                   | "PRB Change Team"
|  ciclo)                      |                   +----------------+
+------------------------------+
```

**Componentes:**
- **Tabela master:** `lwsa.motor_change_team` — lê com `WHERE ativo = true`. Coluna chave: `numero` (PRB no SNow).
- **Tabela snapshot:** `lwsa.motor_change_team_painel` — TRUNCATE+INSERT a cada execução do validador. Sem FK pra filhos (tabela folha).
- **Entry-point:** `validar_entregas.py::executar_validacao` — 3º bloco try/except condicional em `config.CHANGE_TEAM_HABILITADO`.
- **Toggle:** env var `CHANGE_TEAM_HABILITADO` (default `"true"`). Set `"false"` para desligar sem deploy.

---

## 2.5. Pré-requisitos do banco PROD (aprendidos no go-live 2026-06-09)

Antes de o painel funcionar contra Postgres real, **3 setups são obrigatórios**.
Sem eles o try/except do Defense in Depth não quebra V3.1, mas o snapshot fica
vazio (0 rows) indefinidamente.

**1. Versão do Postgres confirmada: 9.2.19** (Locaweb). Compatível com o DO
block PL/pgSQL do seed (`IF NOT EXISTS (SELECT 1 ...)`). ⚠️ Em 9.2, `COUNT(*)
FILTER (WHERE ...)` e `ON CONFLICT` NÃO existem — usar `SUM(CASE WHEN ... THEN
1 ELSE 0 END)`.

**2. Ownership das tabelas:** quem rodar `sql/motor_tables.sql` (geralmente
via DBeaver com conta admin tipo `a_report`) precisa **transferir ownership
das 2 tabelas para a conta do motor** (`automatizacoes` na Locaweb), porque
`TRUNCATE ... RESTART IDENTITY` exige owner da sequência (não basta GRANT).

```sql
ALTER TABLE lwsa.motor_change_team        OWNER TO automatizacoes;
ALTER TABLE lwsa.motor_change_team_painel OWNER TO automatizacoes;
```

A sequence ligada à tabela acompanha o owner automaticamente — não tente
`ALTER SEQUENCE ... OWNER TO` direto (Postgres bloqueia com "cannot change
owner of sequence linked to table"). Sintoma se faltar este passo:
`ERROR: must be owner of relation motor_change_team_painel_id_seq`.

**3. PRBs históricos no espelho SNow:** `lwsa.service_now_problems` na Locaweb
só replica PRBs recentes. Se a master Change Team referencia PRBs antigos
(numeração baixa), eles **não aparecem no espelho** → `gerar_painel_change_team`
loga `WARNING: PRBs Change Team na master mas nao no SNow: [...]` e o painel
fica subdimensionado. Rodar **backfill** via `projetos/problemas/backfill.py`
antes do primeiro disparo do validador resolve.

Para diagnosticar quantos da master estão no espelho:

```sql
SELECT COUNT(*) AS no_snow
FROM lwsa.service_now_problems p
JOIN lwsa.motor_change_team m ON m.numero = p.numero
WHERE m.ativo = true;
```

Esperado: igual ao `count` da master. Se < master, falta backfill.

---

## 3. Como Construir o Chart "PRB Change Team" no Superset

> ⚠️ **Setup manual** — D-07 explicitamente coloca a construção do chart
> fora do escopo automatizado. Esse passo é executado **uma vez** por quem
> tem permissão de criar chart no Superset corporativo.

**Passos:**

1. No Superset corporativo, **+ Chart → New Chart**.
2. **Datasource:** selecionar a conexão Postgres que já aponta para `lwsa.*` (mesma usada pelos outros charts `motor_*`).
3. **Dataset:** criar novo dataset via SQL Lab apontando para `lwsa.motor_change_team_painel`.
4. **Tipo de chart:** **Table** (recomendado para o MVP — listagem tabular).
5. **Colunas a exibir** (ordem visual sugerida):

   ```
   prb_id, descricao_curta, produto, servidor, status_snow,
   prioridade_atual, dias_em_aberto, grupo_designado,
   ultima_atualizacao, veredicto, data_resolucao, dias_pos_resolucao,
   qtd_incs_pos_resolucao, qtd_incs_pre_resolucao,
   delta_chamados_pct, qtd_prbs_novos_pos_resolucao, snapshot_em
   ```

6. **Ordenação default sugerida:**
   - Abertos primeiro (`veredicto IS NULL DESC`)
   - Mais antigos visíveis (`dias_em_aberto DESC NULLS LAST`)

7. **Nome do chart:** **"PRB Change Team"** (D-08 LOCKED).
8. **Dashboard:** salvar em dashboard "Motor PRB" existente ou criar novo "Force-Task Change Team".

---

## 4. SQL Canônico

### Query A — Listagem completa (base do chart Table)

```sql
SELECT
    prb_id, descricao_curta, produto, servidor,
    status_snow, prioridade_atual, dias_em_aberto, grupo_designado,
    ultima_atualizacao,
    veredicto, data_resolucao, dias_pos_resolucao,
    qtd_incs_pos_resolucao, qtd_incs_pre_resolucao,
    delta_chamados_pct, qtd_prbs_novos_pos_resolucao,
    snapshot_em
FROM lwsa.motor_change_team_painel
ORDER BY (veredicto IS NULL) DESC,
         dias_em_aberto DESC NULLS LAST;
```

### Query B — Split aberto vs resolvido (filtros sugeridos para o dashboard)

```sql
-- Abertos (D-05): sem veredicto, ainda em andamento
SELECT *
FROM lwsa.motor_change_team_painel
WHERE veredicto IS NULL
ORDER BY dias_em_aberto DESC NULLS LAST;

-- Resolvidos (D-06): com veredicto + sinais pós-resolução
SELECT *
FROM lwsa.motor_change_team_painel
WHERE veredicto IS NOT NULL
ORDER BY data_resolucao DESC;
```

### Query C — Big Number "X de Y resolvidos"

> ⚠️ Postgres da Locaweb é **9.2.19** — `COUNT(*) FILTER (WHERE ...)` foi
> introduzido em 9.4 e **dá `ERROR: syntax error at or near "("`** aqui.
> Usar `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` no lugar.

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
FROM lwsa.motor_change_team_painel;
```

Acrescentei `reincidencias` no mesmo big number — é o sinal mais acionável
operacionalmente (PRBs marcados como resolvidos mas com problema voltando).
No go-live de 2026-06-09: 6/84 reincidências, sendo PRB0055284 já há 726
dias pós-resolução.

### Query D — Health check (snapshot fresco?)

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
