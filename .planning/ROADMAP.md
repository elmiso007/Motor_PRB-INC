# Roadmap: Motor PRB-INC

## Overview

Motor PRB-INC ja esta em producao na Locaweb desde maio/2026, com motor
preventivo (15min), ValidadorEntrega V3.1 (6h) e fase Saude do Cliente em
operacao. O roadmap v1.0 captura essa linha de base como Phase 0 (estado
as-built) e abre Phase 1 — Painel Change Team em modo discovery, para refinar
escopo dos ~88 PRBs da force-task antes de prescrever implementacao. Phases
2+ ficam intencionalmente em aberto: serao moldadas pelo resultado da
discovery de Phase 1.

## Phases

**Phase Numbering:**

- Integer phases (0, 1, 2): Planejado milestone work
- Decimal phases (1.1, 1.2): Insercoes urgentes (marcadas com INSERTED)

- [x] **Phase 0: Estado as-built (baseline)** - Documenta o motor ja em
      producao: extracao, analise, regras, saude do cliente, validador, output
      e agendamento.

- [x] **Phase 1: Painel Change Team — Discovery** - Coleta escopo dos 84 PRBs
      (lista deduplicada de 92 entries originais), define cadencia 6h (D-02),
      decide fronteira tecnologica Superset corporativo (D-07) e implementa
      tabela materializada + chart guia. Complete 2026-06-05.

## Phase Details

### Phase 0: Estado as-built (baseline)

**Goal**: Registrar o comportamento ja em producao do Motor PRB-INC para dar
coesao ao GSD, sem replanejar nada. Cobre motor preventivo, validador
retrospectivo, saude do cliente, persistencia Postgres e agendamento via Task
Scheduler.
**Depends on**: Nothing (baseline)
**Requirements**: EXTR-01, EXTR-02, EXTR-03, ANAL-01, ANAL-02, RULE-01,
RULE-02, RULE-03, HLTH-01, VALD-01, OUT-01, OUT-02, OUT-03, ORCH-01, ORCH-02,
ORCH-03, ORCH-04
**Success Criteria** (what must be TRUE):

  1. Operador ve, a cada 15min, um ciclo completo do motor preventivo
     produzindo `output/dashboard_state.json`, rows em `lwsa.motor_*` e
     mensagens Slack apenas para casos CRITICA + alerta_recorrencia_alta +
     reincidencia.

  2. ValidadorEntrega roda a cada 6h e classifica PRBs entregues em
     REINCIDENCIA / ENTREGA_VALIDADA / INCONCLUSIVO, com 4 sinais auxiliares
     persistidos em `motor_validacao_entrega` (21 colunas) e em
     `motor_validacao_entrega_equipe`.

  3. Saude do Cliente identifica clientes Nominal com >=3 INCs em 30d e >=1
     INC em 7d, gerando timeline cronologica no dashboard JSON em ~30-45s.

  4. Cascata P1-P5 aplica a matriz oficial (CON-001 a CON-006) com
     justificativa textual auditavel em cada cluster prescrito.

  5. Operador consegue rodar `python main.py` localmente em modo mock
     (`USAR_MOCKS=true`) e ver ciclo completo sem dependencia de Postgres.
**Plans**: 0 plans (estado as-built — nao requer planejamento downstream)
**Status**: Complete (operando em producao desde maio/2026)
**UI hint**: no

### Phase 1: Painel Change Team — Discovery

**Goal**: Definir escopo, audiencia, cadencia e fronteira tecnologica do
painel de acompanhamento dos ~88 PRBs da force-task Change Team. Saida da
discovery e um PRD/SPEC suficiente para prescrever Phase 2+ (implementacao).
**Depends on**: Phase 0 baseline (registrada)
**Requirements**: PNCT-01
**Success Criteria** (what must be TRUE):

  1. Lista canonica dos ~88 PRBs da Change Team esta documentada, com criterio
     de selecao explicito (numero, grupo_designado, etiqueta SNow ou tabela
     dedicada) e local de armazenamento decidido.

  2. Fronteira tecnologica esta decidida — extensao do
     `output/dashboard_state.json` (com nova secao `change_team`), dashboard
     web novo (Streamlit, HTML estatico ou outro) ou hibrido — com justificativa
     registrada como ADR.

  3. Cadencia de atualizacao do painel esta definida (acompanha 15min do
     motor preventivo, real-time sob demanda, ou janela proxima ao validador
     6h) e compativel com a arquitetura escolhida.

  4. Audiencia e modo de consumo estao mapeados (Change Team apenas,
     coordenacao + Change Team, ou aberto), incluindo onde sera publicado
     (Slack, navegador interno, e-mail, etc.).

  5. PRD/SPEC suficiente para abrir Phase 2 esta gravado em
     `.planning/discovery/` ou equivalente, com acceptance criteria de PNCT-01
     promovidos de "em aberto" para fechados.**Plans**: 6 plans
**Wave 1**

  - [x] 01-01-PLAN.md — SQL DDL idempotente (motor_change_team + motor_change_team_painel) + seed 84 PRBs
  - [x] 01-02-PLAN.md — Models (PainelChangeTeamRow) + Config (toggle CHANGE_TEAM_HABILITADO + nomes de tabela)

**Wave 2** *(blocked on Wave 1 completion)*

  - [x] 01-03-PLAN.md — Extractor: novo metodo listar_prbs_por_numero (ABC + Real + Mock)
  - [x] 01-04-PLAN.md — Modulo change_team.py + persistencia atomica em notifier_db

**Wave 3** *(blocked on Wave 2 completion)*

  - [x] 01-05-PLAN.md — Integracao no validar_entregas.py (3o try/except) + 6 testes
  - [x] 01-06-PLAN.md — Documentacao operacional docs/DASHBOARD_CHANGE_TEAM.md (chart Superset + gestao master)

**Status**: Complete (2026-06-05) — implementacao + 116 testes verdes + smoke OK + VERIFICATION.md PASSED. Bug colateral fixado (change_team SELECT numero em vez de prb_id).
**UI hint**: yes (chart Superset corporativo — D-07)

> **Nota sobre Phase 2+:** intencionalmente nao prescritas. O resultado da
> discovery de Phase 1 (PRD/ADR) vai determinar quantas phases de
> implementacao serao necessarias, o stack (ex.: Streamlit + Postgres readers
> vs nova secao no JSON) e o roteiro de entrega. Quando a discovery encerrar,
> rodar `/gsd-plan-phase 1` para gerar Plans de implementacao e, se a
> implementacao for grande, expandir o roadmap com Phase 2+.

## Progress

**Execution Order:**
Phases execute in numeric order: 0 (complete) → 1 (discovery) → 2+ (TBD apos
discovery)

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 0. Estado as-built (baseline) | 0/0 | Complete | 2026-06-05 (registrada) |
| 1. Painel Change Team — Discovery | 6/6 | Complete | 2026-06-05 |
