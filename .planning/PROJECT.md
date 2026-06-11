# Motor PRB-INC

## What This Is

Sistema Python prescritivo, em producao na Locaweb, que antecipa PRBs (Problem
Records) cruzando incidentes do ServiceNow com chamados Dynamics/KingHost.
Aplica uma matriz oficial P1-P5 sobre clusters semanticos de INCs (TF-IDF +
DBSCAN), avalia saude do cliente e valida retrospectivamente entregas do
Change Team. Consumido por plantao, coordenacao e force-task Change Team via
dashboard JSON, persistencia Postgres (`lwsa.motor_*`) e alertas Slack
criticos.

## Core Value

Antecipar crises de produto — transformar 5 INCs aparentemente isoladas em
1 prescricao P1-P5 acionavel antes que viram incidente operacional grave.

## Requirements

### Validated

<!-- Ja em producao na Locaweb. Comportamento confirmado pelas reunioes
Jessica/Victor/Bruno e pelos resultados operacionais 2026-06-02. -->

- ✓ Extracao de INCs do ServiceNow (24h) — Phase 0
- ✓ Extracao de chamados multi-org (Locaweb + KingHost) via registry — Phase 0
- ✓ Extracao de PRBs ativos para match de repriorizacao — Phase 0
- ✓ Clusterizacao TF-IDF + DBSCAN + fusao por CI — Phase 0
- ✓ Scores de criticidade e ineficiencia ponderados — Phase 0
- ✓ Cascata P1-P5 com matriz oficial Locaweb — Phase 0
- ✓ Gatilho proativo P3 → P2 (>=5 INCs identicas) — Phase 0
- ✓ Sugestao de repriorizacao (so upgrade, nunca rebaixa) — Phase 0
- ✓ Saude do Cliente com bulk+slim e timeline cronologica — Phase 0
- ✓ ValidadorEntrega V3.1 (3 veredictos + 3 sinais auxiliares) — Phase 0
- ✓ Dashboard JSON gravado a cada ciclo — Phase 0
- ✓ Persistencia atomica em 5 tabelas `lwsa.motor_*` — Phase 0
- ✓ Alertas Slack filtrados (criticos + recorrencia + reincidencia) — Phase 0
- ✓ Motor preventivo a cada 15min via Task Scheduler — Phase 0
- ✓ ValidadorEntrega a cada 6h via Task Scheduler — Phase 0
- ✓ Logs UTF-8 rotacionados por dia — Phase 0
- ✓ Modo mock (`USAR_MOCKS=true`) para desenvolvimento — Phase 0
- ✓ Convencoes UTC interno + BRT na fronteira — Phase 0

### Active

<!-- Em discovery. Acceptance criteria a definir antes da implementacao. -->

- [ ] Painel Change Team — acompanhamento dos ~88 PRBs da force-task
      interdisciplinar (escopo, cadencia e fronteira tecnologica em aberto)

### Out of Scope

<!-- Limites explicitos para evitar scope creep. -->

- Loop interno de cadencia em Python — Task Scheduler externo cobre, sem ganho
  em paralelizar
- API REST bidirecional com ServiceNow — motor sugere, humano decide (mantem
  auditabilidade)
- ML supervisionado com feedback loop — regras deterministicas auditaveis sao
  premissa do MVP
- Real-time streaming de INCs — ciclo 15min e suficiente para o uso atual
- Microservices — monolito modular adequado ao tamanho atual
- Substituir TF-IDF por sentence-transformers — custo (~500MB modelo, ~5s
  startup) nao compensa para textos tecnicos curtos a cada 15min
- Migrar Postgres `json` para `jsonb` — adiado ate Locaweb atualizar infra para
  >= 9.4

## Context

- **Ambiente:** producao Locaweb, schema `lwsa.motor_*` no Postgres compartilhado
  (versao 9.2/9.3). Roda em maquina Windows via Task Scheduler. Slack via
  Bot Token compartilhado com locapredict.
- **Projeto irmao:** locapredict (`MRP para PRB/locapredict/`). Reutiliza
  padroes: `sql_normalizar_login_cliente`, `config.ini`, Slack bot token.
- **Origem:** reuniao com Jessica, Victor e Bruno (Locaweb) levantou a dor —
  plantao dependia de percepcao humana para notar que 5 INCs isoladas eram o
  mesmo problema crescendo.
- **Resultados:** registrados em 2026-06-02 (apresentacao oficial). Mock
  desligado em producao na mesma data; loop interno removido em favor de
  single-run em 2026-06-05.
- **Stack:** Python 3.10+ (testado em 3.13), psycopg2-binary, scikit-learn,
  slack_sdk, requests, pandas, tzdata, pytest.
- **Volumes tipicos por ciclo:** ~91 INCs + ~80 chamados + ~2 PRBs → ~24 rows
  Postgres + ~13-15 mensagens Slack. Pipeline 5-10s. Saude do Cliente isolada
  ~30-45s.
- **Limitacoes conscientes:** sem `breach_time` do SNow (P1.A heuristico via
  ineficiencia); `tempo_solucao_contorno_min` hardcoded em 0; motor stateless
  entre ciclos (analise temporal via SQL).

## Constraints

<decisions locked="true">

> Regras de negocio LOCKED. Vindas da SPEC docs/REGRAS.md, validadas pela
> reuniao Jessica/Victor/Bruno. **Nao podem ser auto-overridden por agente.**
> Qualquer alteracao exige PR explicito + nova revisao do PO.

- **CON-001 — Matriz oficial P1-P5 (cascata)**: P1 Crise → P2 Alta → P3 Media
  → P4 Baixa → P5 Planejado. Primeira regra que casa vence. Default ao final:
  P5 (com contorno e qtd_incs<5) ou P4 fallback generico. Fonte: docs/REGRAS.md
  secao 1.
- **CON-002 — Criterios P1 (Crise)**: regras P1.A (Reclame Aqui + sem contorno
  + ineficiencia >= 0.6), P1.B (contratacao + indisponibilidade_total + sem
  contorno), P1.C (indisponibilidade_total + produto em {CAL, Central do
  Cliente, Painel do Produto}), P1.D (termos de risco/seguranca). Fonte:
  docs/REGRAS.md secao 2.
- **CON-003 — Criterios P2 (Alta)**: P2.A a P2.E conforme docs/REGRAS.md
  secao 3, incluindo limiares `LIMIAR_P2_INCS_SEM_CONTORNO=5`,
  `LIMIAR_P2_INCS_COM_CONTORNO=100`, `LIMIAR_P2_CONTORNO_MIN=60`.
- **CON-004 — Criterios P3 (Media)**: P3.A a P3.D conforme docs/REGRAS.md
  secao 4, incluindo faixa 20-99 INCs com contorno e tempo 10-59 min.
- **CON-005 — Criterios P4 (Baixa)**: P4.A conforme docs/REGRAS.md secao 5,
  com tempo de contorno < 10 min ou volume < 20.
- **CON-006 — Criterios P5 (Planejado)**: default da cascata com contorno e
  qtd_incs<5, sempre marcado como "aguarda confirmacao Coord/PO". Decisao
  final humana. Fonte: docs/REGRAS.md secao 6.
- **CON-007 — Gatilho proativo P3 → P2**: cluster com >= 5 INCs P3 identicas
  promove para P2. Nao promove P2 → P1 nem P4/P5 → P2. Fonte: docs/REGRAS.md
  secao 7.
- **CON-008 — Sugestao de repriorizacao (so upgrade)**: match por (produto,
  servidor); so sugere mudanca se nova prioridade for mais grave (numero
  menor). Nunca rebaixa. Acoes: REPRIORIZAR_PRB / MONITORAR / ABRIR_PRB /
  NENHUMA. Fonte: docs/REGRAS.md secao 8.
- **CON-009 — Saude do Cliente — alerta_recorrencia_alta**: janela 30d, filtro
  tipo_usuario='Nominal', `LIMIAR_INCS_SAUDE_CLIENTE=3`, exige >=1 INC nos
  ultimos 7d. Severidade media por prioridade (P1=1.0 ... P5=0.0). Fonte:
  docs/REGRAS.md secao 9.
- **CON-010 — Clusterizacao TF-IDF + DBSCAN**: `DBSCAN_EPS=0.55` (cosseno),
  `DBSCAN_MIN_SAMPLES=2`, `TFIDF_NGRAM_RANGE=(1,2)`. Fusao por CI pos-DBSCAN.
  Singletons (qtd=1) NAO persistem em `motor_cluster`. Fonte: docs/REGRAS.md
  secao 12.
- **CON-011 — Filtros de organizacao e login**: `ORGANIZACOES_ATIVAS=("Locaweb",)`
  default. `LOGIN_CLIENTE_PADROES_EXCLUIDOS=("kinghost",)` aplicado so em
  `contar_clientes_com_inc_recente`. Fonte: docs/REGRAS.md secao 13.
- **CON-012 — ValidadorEntrega V3.1**: 3 veredictos (REINCIDENCIA com
  `LIMIAR_INCS_REINCIDENCIA=3` → Slack ON; ENTREGA_VALIDADA com
  `MIN_DIAS_PARA_VALIDAR=7` → Slack OFF; INCONCLUSIVO → Slack OFF). 3 sinais
  auxiliares: volumetria pre (60d), delta chamados vinculados (14d cada lado),
  PRBs novos pos-resolucao no mesmo CI. Fonte: docs/REGRAS.md secao 14.
- **CON-013 — Termos heuristicos (word boundary regex)**: listas
  `TERMOS_RECLAME_AQUI`, `TERMOS_CONTRATACAO`, `TERMOS_INDISPONIBILIDADE_TOTAL`,
  `TERMOS_RISCO_SEGURANCA`, `TERMOS_SEM_CONTORNO`,
  `_TERMOS_INDICADORES_CONTORNO`. Match via `\b...\b`. Ajuste exige revisao
  deliberada. Fonte: docs/REGRAS.md secao 10.

</decisions>

### Outros constraints (nao-locked, operacionais)

- **Infraestrutura**: conta Postgres do motor precisa SELECT em `lwsa.*`,
  `dynamics.*`, `kinghost.*`, `lw_octadesk.*`; INSERT+SELECT em `lwsa.motor_*`;
  USAGE+SELECT em sequencias. Compatibilidade Postgres 9.2/9.3 (`json` em vez
  de `jsonb`).
- **Runtime**: Python 3.10+ (testado 3.13), dependencias psycopg2-binary,
  scikit-learn, requests, slack_sdk, pandas, tzdata, pytest. `config.ini`
  compartilhado com locapredict em `projetos/config.ini`.
- **Scheduling**: motor preventivo 15min via `Motor-PRB.bat`; ValidadorEntrega
  6h via `Motor-PRB-Validador.bat`. Exit code 0/1 sinaliza sucesso/falha.

## Key Decisions

<!-- 21 decisoes implicitas mineradas de docs/ARQUITETURA.md. Nao-locked: vieram
de DOC, nao de ADR formal. Promover a ADR caso queira blindar contra mudancas. -->

| Decisao | Racional | Status |
|---------|----------|--------|
| DEC-001 — TF-IDF + DBSCAN (sklearn) em vez de sentence-transformers | Custo ~500MB + ~5s startup nao compensa para textos curtos a cada 15min | ✓ Boa |
| DEC-002 — Postgres com tipo `json` (nao `jsonb`) | Compatibilidade Postgres 9.2/9.3 da Locaweb | — Pendente (migrar quando infra atualizar) |
| DEC-003 — Le do Data Warehouse, nao da API SNow | Sem acoplamento direto com SNow, latencia previsivel | ✓ Boa |
| DEC-004 — Single-run + Task Scheduler externo (sem loop) | Task Scheduler atua como supervisor, crash isolado | ✓ Boa (refatorado 2026-06-05) |
| DEC-005 — Validador em entry-point proprio (cadencia 6h separada) | Nao compete com ciclo 15min do preventivo | ✓ Boa |
| DEC-006 — Arquitetura 4 niveis com imports unidirecionais | Sem ciclos, verificavel via grep | ✓ Boa |
| DEC-007 — Motor stateless entre ciclos | Analise temporal via SQL no historico | ⚠️ Revisitar (sem anti alert-fatigue p/ PRB) |
| DEC-008 — JSON em paralelo a Postgres | Rede de seguranca se Postgres cair | ✓ Boa |
| DEC-009 — slack_sdk WebClient com fallback webhook HTTP | Padrao locapredict + compatibilidade | ✓ Boa |
| DEC-010 — Defense in Depth (try/except em 4 niveis) | Uptime e prioridade; ~30% das linhas sao erro | ✓ Boa |
| DEC-011 — UTC interno, BRT na fronteira | Comparacoes seguras independente do servidor | ✓ Boa |
| DEC-012 — Configurabilidade externa total (zero numero magico) | Ajustes operacionais sem refactor | ✓ Boa |
| DEC-013 — Registry declarativo multi-tenancy | Adicionar organizacao = editar dict | ✓ Boa |
| DEC-014 — Filtros default focados em Locaweb | KingHost so quando explicito | ✓ Boa |
| DEC-015 — Singletons nao persistem em motor_cluster | Tabela ~70% mais limpa | ✓ Boa |
| DEC-016 — Saude do Cliente bulk+slim em 2 fases | Caiu de ~80min para ~30-45s | ✓ Boa |
| DEC-017 — Login canonico via SQL portado do locapredict | GROUP BY estavel | ✓ Boa |
| DEC-018 — ValidadorEntrega V3.1 com 4 sinais por PRB | V2 produto-match era ruidoso, V3 vinculado e mais preciso | ✓ Boa |
| DEC-019 — Stop-words PT-BR sem acentos | Casa com texto NFKD normalizado | ✓ Boa |
| DEC-020 — Repriorizacao so upgrade (nunca downgrade) | Motor nunca perde foco automaticamente | ✓ Boa |
| DEC-021 — Gatilho proativo so promove uma faixa (P3→P2) | Conservadorismo: sinal volumetrico forte gera escalada, nao crise | ✓ Boa |

---
*Last updated: 2026-06-05 after GSD bootstrap (new-project-from-ingest)*
