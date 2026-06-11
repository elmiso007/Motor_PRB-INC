# Requirements: Motor PRB-INC

**Defined:** 2026-06-05
**Core Value:** Antecipar crises de produto — transformar 5 INCs aparentemente
isoladas em 1 prescricao P1-P5 acionavel antes que viram incidente operacional
grave.

## v1 Requirements

Requirements do baseline em producao (status Complete) + nova feature em
discovery (status Pending). Cada requisito mapeia para exatamente uma phase.

### Extracao

- [x] **EXTR-01**: Motor le INCs abertas nas ultimas 24h de
  `lwsa.service_now_incidentes`, com filtro `organizacao IN (config.ORGANIZACOES_ATIVAS)`,
  prioridade parseada e data BRT→UTC. Falha aborta ciclo.
- [x] **EXTR-02**: Motor le chamados das ultimas 24h de Locaweb
  (`dynamics.chamados` JOIN `lw_octadesk.classificacoes`) e KingHost
  (`kinghost.chamados`) via `TABELAS_CHAMADOS_POR_ORGANIZACAO`. Falha nao
  aborta ciclo (chamados=[]).
- [x] **EXTR-03**: Motor le PRBs ativos (status em `STATUS_PRB_ATIVOS`) de
  `lwsa.service_now_problemas` retornando numero, produto, servidor,
  prioridade, status, data_abertura.

### Analise

- [x] **ANAL-01**: Motor agrupa INCs semanticamente via TF-IDF + DBSCAN
  (`eps=0.55, min_samples=2, cosseno`), com fusao por CI (produto, servidor)
  para singletons truthy. Fallback Jaccard se sklearn indisponivel.
- [x] **ANAL-02**: Cada cluster recebe score de criticidade (0.35 volume +
  0.30 indisponibilidade + 0.25 sem_contorno + 0.10 recorrencia_ci) e de
  ineficiencia (0.6 volume_updates + 0.4 velocidade_updates_hora).

### Regras

- [x] **RULE-01**: Motor aplica cascata P1-P5 conforme matriz oficial
  (CON-001 a CON-006) com justificativa textual auditavel.
- [x] **RULE-02**: Motor promove P3 → P2 quando cluster tem >=5 INCs P3
  identicas (CON-007).
- [x] **RULE-03**: Motor compara prioridade nova vs. PRB matched por (produto,
  servidor) e sugere upgrade quando aplicavel (CON-008). Acao final: ABRIR_PRB
  / REPRIORIZAR_PRB / MONITORAR / NENHUMA.

### Saude do Cliente

- [x] **HLTH-01**: Motor identifica clientes com recorrencia alta (>=3 INCs
  em 6m + >=1 INC em 7d), filtra `tipo_usuario='Nominal'`, normaliza via
  `sql_normalizar_login_cliente`. Estrategia bulk+slim (CON-009). Performance
  ~30-45s ciclo.

### Validador

- [x] **VALD-01**: Motor olha PRBs entregues pelo Change Team e classifica em
  REINCIDENCIA / ENTREGA_VALIDADA / INCONCLUSIVO, com 3 sinais auxiliares
  (volumetria pre 60d, delta chamados vinculados 14d, PRBs novos pos-resolucao
  no mesmo CI). Persiste em `motor_validacao_entrega` (21 colunas) e em
  `motor_validacao_entrega_equipe` (times impactados). CON-012.

### Output

- [x] **OUT-01**: Motor grava `output/dashboard_state.json` (UTF-8 indent 2,
  ~30KB) SEMPRE em cada ciclo, com estrutura normalizada (clusters/incidentes
  separados). Primeiro nas saidas.
- [x] **OUT-02**: Motor persiste atomicamente em 5 tabelas `lwsa.motor_*`
  (execucao, cluster, prescricao, saude_cliente, validacao_entrega).
  Singletons filtrados antes do INSERT em `motor_cluster`. Configuravel via
  `PERSISTIR_NO_BANCO`. Falha de Postgres nao aborta motor.
- [x] **OUT-03**: Motor dispara Slack para `prescricoes.urgencia=CRITICA` +
  `saude.alerta_recorrencia_alta` + reincidencias do ValidadorEntrega.
  Preferencia `slack_sdk.WebClient.chat_postMessage` com fallback HTTP
  webhook. Rate limit 1s.

### Orquestracao

- [x] **ORCH-01**: Motor preventivo executa via `Motor-PRB.bat` a cada 15min
  no Windows Task Scheduler. `python main.py` single-run termina com exit
  code 0/1.
- [x] **ORCH-02**: ValidadorEntrega executa via `Motor-PRB-Validador.bat` a
  cada 6h. `python validar_entregas.py` single-run com log proprio.
- [x] **ORCH-03**: Logs UTF-8 rotacionados por dia em `motor-prb-{YYYY-MM-DD}.log`
  (Windows console UTF-8 forcado).
- [x] **ORCH-04**: Modo `USAR_MOCKS=true` gera ~91 INCs + 80 chamados + 2
  PRBs + 13-19 clientes sinteticos via factories `criar_fonte_*()`. Default
  producao: false (desde 2026-06-02).

### Painel Change Team

- [x] **PNCT-01**: Painel de acompanhamento dos 84 PRBs especificos da
  force-task interdisciplinar Change Team. Materializa em
  `lwsa.motor_change_team_painel` (snapshot atomico a cada 6h via
  ValidadorEntrega) com tracking de status SNow, idade, prioridade,
  veredicto V3.1 (PRBs entregues) e sinais pos-resolucao reaproveitando
  `validador_entrega._avaliar_prb` (CON-012 LOCKED preservado).
  - **Acceptance fechado (2026-06-05, Phase 1):**
    - Criterio de selecao: tabela dedicada `lwsa.motor_change_team` com
      coluna `numero` + soft delete (D-01)
    - Fronteira tecnologica: Superset corporativo lendo SQL direto da
      tabela materializada — chart "PRB Change Team" (D-07, D-08)
    - Cadencia: 6h via ValidadorEntrega (D-02) — entry-point ja em producao
    - Onde mora a lista: `lwsa.motor_change_team` (soft delete via
      ativo/removido_em — D-01)
    - Audiencia: Change Team + operador + DBA/PO; consumo via Superset
      corporativo (documentado em docs/DASHBOARD_CHANGE_TEAM.md §1, §3)

## v2 Requirements

Nao ha v2 formalizado no momento. Candidatos potenciais surgirao apos discovery
de PNCT-01 (ex.: integracao bidirecional com SNow, painel real-time, ML com
feedback loop). Tracked separadamente quando promovidos.

## Out of Scope

Explicitamente excluido para evitar scope creep. Mantido para prevenir
re-adicao sem revisao.

| Feature | Razao |
|---------|-------|
| Loop interno de cadencia Python | Task Scheduler externo cobre, sem ganho em paralelizar — removido em 2026-06-05 |
| API REST bidirecional com ServiceNow | Motor sugere, humano decide (mantem auditabilidade) |
| ML supervisionado com feedback loop | Regras deterministicas auditaveis sao premissa do MVP |
| Real-time streaming de INCs | Ciclo 15min e suficiente para o uso atual |
| Microservices | Monolito modular adequado ao tamanho atual |
| Substituir TF-IDF por sentence-transformers | Custo ~500MB + ~5s startup nao compensa textos curtos a cada 15min |
| Migrar Postgres `json` para `jsonb` | Adiado ate Locaweb atualizar infra para >= 9.4 |
| Anti alert-fatigue para PRBs (Slack) | Aceito como limitacao do MVP — so Saude do Cliente tem |
| Health check HTTP | Monitorar timestamp do JSON ou MAX em motor_execucao |

## Traceability

Mapeamento de cada requisito v1 para a phase correspondente.

| Requirement | Phase | Status |
|-------------|-------|--------|
| EXTR-01 | Phase 0 | Complete |
| EXTR-02 | Phase 0 | Complete |
| EXTR-03 | Phase 0 | Complete |
| ANAL-01 | Phase 0 | Complete |
| ANAL-02 | Phase 0 | Complete |
| RULE-01 | Phase 0 | Complete |
| RULE-02 | Phase 0 | Complete |
| RULE-03 | Phase 0 | Complete |
| HLTH-01 | Phase 0 | Complete |
| VALD-01 | Phase 0 | Complete |
| OUT-01 | Phase 0 | Complete |
| OUT-02 | Phase 0 | Complete |
| OUT-03 | Phase 0 | Complete |
| ORCH-01 | Phase 0 | Complete |
| ORCH-02 | Phase 0 | Complete |
| ORCH-03 | Phase 0 | Complete |
| ORCH-04 | Phase 0 | Complete |
| PNCT-01 | Phase 1 | Complete (2026-06-05) |

**Coverage:**
- v1 requirements: 18 total (18 Complete)
- Mapped to phases: 18
- Unmapped: 0 ✓

> **Nota:** o requirement REQ-logs-rotacionados (originalmente listado em
> requirements.md do ingest) foi consolidado dentro de ORCH-03. Total efetivo
> v1: 18 itens.

---
*Requirements defined: 2026-06-05*
*Last updated: 2026-06-05 after GSD bootstrap (new-project-from-ingest)*
