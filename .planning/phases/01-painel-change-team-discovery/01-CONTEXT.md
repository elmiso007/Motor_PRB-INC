# Phase 1: Painel Change Team — Discovery - Context

**Gathered:** 2026-06-05
**Status:** Ready for planning (com 3 ações abertas — ver `Specific Ideas`)

<domain>
## Phase Boundary

Capturar a lista oficial dos ~88 PRBs da force-task interdisciplinar "Change
Team" e expor um **painel agregado de acompanhamento** que sobrevive a PRBs
abertos há meses (fora da janela natural de 14d do ValidadorEntrega). Saída
da discovery: PRD/SPEC suficiente para abrir Phase 2 (implementação da tabela
materializada + integração no validador + chart no Superset).

**In scope desta phase (discovery):** decisões de arquitetura, persistência,
cadência, exibição e nomenclatura. **NÃO está em scope** desta phase:
implementação dos arquivos `.py`/`.sql`, migration real, criação do chart no
Superset. Esses ficam para Phase 2+.

</domain>

<decisions>
## Implementation Decisions

### Lista master (capturado da conversa anterior ao ingest)

- **D-01:** Lista dos PRBs da Change Team mora em **tabela** `lwsa.motor_change_team`
  com soft delete (`ativo` + `removido_em` + `adicionado_em` + `observacao`).
  Por que tabela e não arquivo `.txt`: permite SQL ad-hoc, histórico do que
  entrou/saiu, e Superset consulta nativo. Soft delete preserva a auditoria
  ("esse PRB foi da Change Team em algum momento?").

### Cadência + entry-point (Área 1 da discussão)

- **D-02:** Entry-point é o **ValidadorEntrega** (cadência 6h via
  `Motor-PRB-Validador.bat`). Por que não o motor preventivo (15min):
  validador já lê PRBs do SNow e cruza com chamados Dynamics — o trabalho
  marginal de adicionar enriquecimento Change Team é pequeno. PRBs não mudam
  de status em minutos, então 4×/dia é suficiente.
- **D-03:** Validador faz uma **query separada SEM janela** para os PRBs da
  Change Team: `SELECT ... FROM lwsa.service_now_problemas WHERE numero IN
  (lista_change_team)`. O fluxo normal do validador (janela 14d) **não é
  alterado** — a query Change Team é independente e roda dentro do mesmo
  ciclo de 6h.
- **D-04:** Persistência é uma **tabela nova materializada**:
  `lwsa.motor_change_team_painel`. Estratégia **TRUNCATE + INSERT atômico**
  por execução (snapshot completo a cada 6h). Segue o padrão OUT-02 (
  persistência atômica em `lwsa.motor_*`).

### Estrutura de colunas exibidas no painel (Área 1, perguntas 3 e 4)

- **D-05:** Para PRBs **abertos** (sem veredicto do validador), exibir:
  `prb_id`, `descricao_curta`, `produto`, `servidor` (`cmdb_ci`), `status_snow`
  (state textual), `prioridade_atual`, `dias_em_aberto`, `grupo_designado`,
  `ultima_atualizacao`. Sem campos de veredicto.
- **D-06:** Para PRBs **resolvidos** dentro da lista Change Team, exibir tudo
  de D-05 + colunas de **acompanhamento pós-resolução** (replicando a
  estrutura do chart "PRB em Vigilância" já existente no Superset):
  veredicto do ValidadorEntrega (REINCIDENCIA / ENTREGA_VALIDADA /
  INCONCLUSIVO), `data_resolucao`, `dias_pos_resolucao`,
  `qtd_incs_pos_resolucao`, `qtd_incs_pre_resolucao` (60d), delta de chamados
  vinculados (`delta_chamados_pct`), `qtd_prbs_novos_pos_resolucao`. As
  colunas exatas serão **confirmadas em Phase 2** olhando o chart "PRB em
  Vigilância" atual.

### Consumo / fronteira tecnológica (clarificação pós-discussão livre)

- **D-07:** Painel é consumido **via Superset corporativo**. Chart chamado
  **"PRB Change Team"**, lendo SQL diretamente de `lwsa.motor_change_team_painel`.
  Não há JSON paralelo, não há HTML estático, não há novo dashboard custom.
- **D-08:** Naming: a **feature/força-tarefa** se chama "Change Team"
  (preservado em tabela, código, configs). O **chart visível no Superset**
  se chama "PRB Change Team" (rótulo final ao consumidor).

### Claude's Discretion

- Layout interno do código Python (módulo `change_team.py` dedicado vs.
  estender `extractor.py`) — padrão a definir pelo planner em Phase 2.
- Estratégia de transação do TRUNCATE+INSERT (SAVEPOINT explícito vs.
  transação implícita do psycopg2) — planner decide com base em
  `notifier_db.py`.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Especificação de regras (LOCKED)

- `docs/REGRAS.md` §14 — ValidadorEntrega V3.1 (CON-012). Entry-point que vai
  ser estendido pra incluir a query Change Team. **Não pode quebrar**
  o veredicto existente.

### Arquitetura e padrões do projeto

- `docs/ARQUITETURA.md` §4 — 12 módulos abertos. Define onde encaixar o novo
  `change_team.py` ou similar.
- `docs/ARQUITETURA.md` §5 — 7 princípios transversais. Decisões D-02/D-03/D-04
  seguem os princípios "configurabilidade externa total" + "stateless entre
  ciclos" + "defense in depth".
- `docs/MANUAL.md` §3 — Persistência Postgres (`lwsa.motor_*`). Define o
  padrão que `lwsa.motor_change_team_painel` deve seguir.
- `docs/VALIDADOR_ENTREGA.md` — fluxo completo do validador. Phase 2 precisa
  entender onde injetar a query nova sem afetar o fluxo principal.

### Código de referência (a ser estudado pelo gsd-phase-researcher)

- `validar_entregas.py` — entry-point atual do validador (single-run, exit code
  0/1). Phase 2 deve **estender**, não duplicar.
- `validador_entrega.py` — pipeline interno. Tem funções já preparadas pra
  cruzamento com `dynamics.chamados`.
- `notifier_db.py` — padrão de persistência atômica em `lwsa.motor_*`.
- `extractor.py` — funções `criar_fonte_problems()` e companhia.
- `sql/motor_tables.sql` — DDL atual de todas as tabelas `lwsa.motor_*`.
  Phase 2 deve adicionar `motor_change_team` + `motor_change_team_painel`
  aqui seguindo o mesmo estilo.

### Histórico GSD da phase

- `.planning/intel/SYNTHESIS.md` — onde o WARNING REQ-painel-change-team foi
  gerado.
- `.planning/intel/decisions.md` (DEC-001 a DEC-021) — 21 decisões mineradas
  de ARQUITETURA.md (não-locked, mas guiam o estilo).
- `.planning/intel/constraints.md` (CON-001 a CON-013) — 13 constraints
  LOCKED (matriz P1-P5).
- `.planning/INGEST-CONFLICTS.md` — registro do WARNING que motivou esta
  discovery.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`validar_entregas.py`** — entry-point single-run já existente; cadência
  6h via .bat já configurada. Phase 2 estende o `executar_validacao()` ou
  adiciona função `executar_change_team_snapshot()` no mesmo ciclo.
- **`notifier_db.py::persistir_execucao()`** — padrão TRUNCATE+INSERT atômico
  em `lwsa.motor_*`. Phase 2 imita pra `lwsa.motor_change_team_painel`.
- **`extractor.py::criar_fonte_problems()`** — extrai PRBs do SNow.
  Reutilizável com filtro `WHERE numero IN (...)`.
- **`models.py::ValidacaoEntrega`** — dataclass com veredictos. Phase 2 pode
  estender com flag `change_team: bool = False` ou criar `PainelChangeTeamRow`
  dataclass separada.

### Established Patterns

- **Naming `lwsa.motor_*`** — todas as tabelas internas do motor usam esse
  prefixo. `lwsa.motor_change_team` + `lwsa.motor_change_team_painel`
  seguem o padrão.
- **Single-run sempre** (DEC-004, removido em 2026-06-05) — Phase 2 NÃO deve
  introduzir nenhum loop interno.
- **JSON em paralelo (OUT-01)** — todos os jobs gravam `output/*.json` como
  rede de segurança. Phase 2 pode adicionar `output/change_team_painel.json`
  paralelo à tabela (decisão do planner, não obrigatório).
- **Configurabilidade externa (DEC-012)** — qualquer threshold/janela novo
  vai em `config.py`, não hardcoded.

### Integration Points

- O `validador_entrega.executar_validacao()` já recebe `fonte_problems` e
  `fonte_chamados`. Phase 2 adiciona chamada extra `gerar_painel_change_team(
  fonte_problems, lista_change_team)` no mesmo escopo, com try/except próprio
  pra não quebrar o validador principal (Defense in Depth — DEC-010).
- Chart Superset lê SQL direto — sem mudança de pipeline lá. Setup do chart
  é manual no Superset (não automatizado por enquanto).

</code_context>

<specifics>
## Specific Ideas

### Imitação do chart "PRB em Vigilância"

O usuário (Emerson) referenciou um chart já existente no Superset chamado
**"PRB em Vigilância"** que tem colunas de acompanhamento pós-resolução. O
novo chart "PRB Change Team" deve **espelhar a estrutura** desse chart, mas
filtrando pelos 88 PRBs da Change Team em vez do conjunto geral.

**Ação aberta — Phase 2 deve confirmar:** quais colunas exatas o chart "PRB
em Vigilância" tem hoje, pra replicar. Pode ser feito via screenshot do
chart ou export de SQL do Superset. A estrutura proposta em D-05/D-06 é uma
**inicial razoável** baseada no que `motor_validacao_entrega` já persiste,
mas precisa de validação visual.

### Ação aberta — gestão CRUD da lista

Não foi discutida nesta phase. Phase 2 vai decidir como Emerson adiciona/
remove PRBs da tabela `lwsa.motor_change_team`. Opções a avaliar:
- SQL direto (`INSERT INTO ... ON CONFLICT DO NOTHING`)
- Script CLI dedicado (`python gerenciar_change_team.py add PRB0XXXX`)
- Etiqueta no próprio SNow com sync automático

Default operacional para Phase 2 (até decidir): **SQL direto + seed inicial
via `sql/seed_change_team.sql`** com os 88 PRBs.

### Ação aberta — alertas Slack

Não foi discutida. Vale uma decisão futura: quando um PRB da Change Team tem
veredicto REINCIDENCIA, dispara Slack dedicado (canal/mention diferente do
geral)? Phase 2 pode tratar como **extensão opcional** — default: usa o
mesmo canal existente de reincidências.

</specifics>

<deferred>
## Deferred Ideas

- **Sync automático com SNow** (etiqueta/campo custom) — só faz sentido se
  Locaweb expor essa capacidade no SNow. Fica para depois do MVP do painel.
- **API REST para gerenciar a lista via UI web** — fora do espírito do MVP
  Python+SQL. Pode virar uma phase própria se a force-task evoluir.
- **Multi-força-tarefa** (vários painéis simultâneos via tabela `lwsa.motor_iniciativas`
  + FK) — overkill agora. Se virar recorrente, evolui depois.
- **Alertas Slack dedicados da Change Team** — diferido para Phase 2 ou 3.

</deferred>

---

*Phase: 1-Painel Change Team — Discovery*
*Context gathered: 2026-06-05*
