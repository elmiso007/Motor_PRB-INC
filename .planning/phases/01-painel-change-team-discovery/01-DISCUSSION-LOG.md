# Phase 1: Painel Change Team — Discovery - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-05
**Phase:** 1-Painel Change Team — Discovery
**Areas discussed:** Cadência + entry-point, Nomenclatura, Consumo (Superset)

---

## Pre-discussion — decisões herdadas

Antes do `/gsd-discuss-phase` rodar, o usuário já havia decidido em conversa
livre (via `AskUserQuestion` no fluxo `/gsd-progress`):

| Decisão | Opções apresentadas | Escolha |
|---|---|---|
| Onde mora a lista dos 88 PRBs | (a) Arquivo `.txt` na raiz / (b) Tabela `lwsa.motor_change_team` / (c) Campo custom no SNow | **Tabela `lwsa.motor_change_team`** |
| Tipo de visualização | (a) Painel agregado / (b) Lista detalhada / (c) Filtro toggle / (d) Alertas Slack dedicados | **Painel agregado** |

Essas decisões foram preservadas como D-01 (lista em tabela) no CONTEXT.md.

---

## Area: Seleção de gray areas

| Option | Description | Selected |
|--------|-------------|----------|
| Cadência + entry-point | Quem atualiza? Preventivo/Validador/job novo? | ✓ |
| Fronteira tecnológica do consumo | JSON / Tabela / Slack / combinação? | (clarificado via texto livre) |
| Cruzamentos com sinais existentes | Status SNow / Validador / Saúde do Cliente? | (parcialmente) |
| Gestão CRUD da lista | SQL direto / Script CLI / Etiqueta SNow? | (deferido para Phase 2) |

**User's choice:** Cadência + entry-point + observação livre sobre tabela "PRBs em Vigilância" no chart.

**Notes:** "Os PRBs já estão na minha tabela problemas porém eu quero acompanhar a lista que já enviei portanto a ideia seria mapear eles e ter uma tabela como apresento no chart PRBs em vigilancia acredito ser uma boa solução"

---

## Area: Cadência + entry-point

### Pergunta 1/4 — Qual job alimenta a tabela?

| Option | Description | Selected |
|--------|-------------|----------|
| ValidadorEntrega (6h) | Validador já lê PRBs e cruza com Dynamics — adição marginal | ✓ |
| Motor preventivo (15min) | Real-time mas custo desnecessário, +1-3s/ciclo | |
| Job novo dedicado | 3º .bat, isolamento máximo, mais manutenção | |
| Ambos (snapshot+delta) | Validador 6h + preventivo delta leve, mais complexo | |

**User's choice:** ValidadorEntrega (6h)
**Notes:** segue recomendação default.

### Pergunta 2/4 — Como tratar PRBs fora da janela 14d?

| Option | Description | Selected |
|--------|-------------|----------|
| Query separada sem janela | Validador mantém 14d; nova query para Change Team independente | ✓ |
| Estender janela inteira para 365d | Custo: validador processaria PRBs antigos sem necessidade | |
| Sem janela para tudo | Perda de performance | |

**User's choice:** Query separada sem janela
**Notes:** segue recomendação default.

### Pergunta 3/4 — O que mostrar para PRBs ABERTOS?

| Option | Description | Selected |
|--------|-------------|----------|
| Status SNow + idade + prioridade + dono | Snapshot do estado atual sem veredicto | ✓ |
| Só contagem agregada | Minimalista, perde drill-down | |
| Tudo + chamados ativos vinculados | Opção 1 + dynamics.chamados ativos | |

**User's choice:** Status SNow + idade + prioridade + grupo designado
**Notes:** segue recomendação default.

### Pergunta 4/4 — Onde persistir o snapshot?

| Option | Description | Selected |
|--------|-------------|----------|
| Tabela nova `lwsa.motor_change_team_painel` | TRUNCATE+INSERT atômico; segue OUT-02 | ✓ |
| Estender `motor_validacao_entrega` | Tabela só grava resolvidos; abertos ficariam de fora | |
| JSON + view materializada | Mais setup, refresh manual | |

**User's choice:** Tabela nova `lwsa.motor_change_team_painel`
**Notes:** segue recomendação default.

---

## Area: Nomenclatura

| Option | Description | Selected |
|--------|-------------|----------|
| PRBs em Vigilância | Feature interna Change Team; chart no Superset "PRBs em Vigilância" | (parcial) |
| Change Team em tudo | Renomear tabela e chart pra Change Team | (parcial) |
| Vigilância em tudo | Renomear até a tabela pra preparar futuras força-tarefas | |

**User's choice:** "PRB Change Team" — nome do chart no Superset
**Notes:** "seria uma boa ideia nos PRBs resolvidos exibem colunas de acompanhamento pós resolução como também já temos no outro chart o PRB em Vigilancia"

→ Resolução: feature/tabela permanecem `change_team`; chart no Superset é
"PRB Change Team"; estrutura de colunas dos PRBs resolvidos vai **imitar** o
chart "PRB em Vigilância" existente. Ação aberta na Phase 2.

---

## Area: Consumo (fronteira tecnológica)

| Option | Description | Selected |
|--------|-------------|----------|
| Superset corporativo | Chart lê SQL direto; coordenador/Change Team via BI | ✓ |
| Superset + seção no dashboard_state.json | Dupla persistência | |
| Só dashboard_state.json (sem Superset) | Mais simples mas perde BI | |

**User's choice:** Superset corporativo
**Notes:** segue recomendação default; alinha com infraestrutura BI já em uso pela Locaweb.

---

## Claude's Discretion

- Layout do código Python (módulo `change_team.py` dedicado vs. funções
  dentro de `extractor.py`/`validador_entrega.py`) — definido pelo planner
  da Phase 2.
- Estratégia de transação do TRUNCATE+INSERT — psycopg2 transação implícita
  é provavelmente suficiente; planner avalia com base em `notifier_db.py`.

## Deferred Ideas

- Sync automático com SNow (etiqueta/campo custom)
- API REST para gerenciar a lista via UI web
- Multi-força-tarefa (tabela `lwsa.motor_iniciativas` + FK)
- Alertas Slack dedicados da Change Team (canal/mention separado)
- Gestão CRUD da lista — diferida para Phase 2 (default: SQL direto + seed inicial)
