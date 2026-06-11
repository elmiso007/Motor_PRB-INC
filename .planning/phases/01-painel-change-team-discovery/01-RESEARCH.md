# Phase 1: Painel Change Team — Research

**Researched:** 2026-06-05
**Domain:** Persistência Postgres atômica + integração no ValidadorEntrega + chart Superset
**Confidence:** HIGH (todas as conclusões verificadas em arquivos do projeto)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions (D-01 a D-08)

- **D-01:** Lista dos PRBs da Change Team mora em **tabela** `lwsa.motor_change_team`
  com soft delete (`ativo` + `removido_em` + `adicionado_em` + `observacao`).
  Por que tabela e não arquivo `.txt`: permite SQL ad-hoc, histórico, e Superset
  consulta nativo. Soft delete preserva auditoria.
- **D-02:** Entry-point é o **ValidadorEntrega** (cadência 6h via `Motor-PRB-Validador.bat`).
  Validador já lê PRBs do SNow e cruza com chamados Dynamics — trabalho marginal
  pequeno; 4×/dia é suficiente.
- **D-03:** Validador faz **query separada SEM janela** para os PRBs da Change Team:
  `SELECT ... FROM lwsa.service_now_problemas WHERE numero IN (lista_change_team)`.
  O fluxo normal do validador (janela 14d) **não é alterado** — a query Change Team
  é independente e roda dentro do mesmo ciclo de 6h.
- **D-04:** Persistência é uma **tabela nova materializada**: `lwsa.motor_change_team_painel`.
  Estratégia **TRUNCATE + INSERT atômico** por execução (snapshot completo a cada 6h).
  Segue padrão OUT-02 (persistência atômica em `lwsa.motor_*`).
- **D-05:** Para PRBs **abertos** (sem veredicto): `prb_id`, `descricao_curta`, `produto`,
  `servidor` (`cmdb_ci`), `status_snow` (state textual), `prioridade_atual`,
  `dias_em_aberto`, `grupo_designado`, `ultima_atualizacao`. Sem campos de veredicto.
- **D-06:** Para PRBs **resolvidos** dentro da lista Change Team: tudo de D-05 +
  veredicto do ValidadorEntrega (REINCIDENCIA / ENTREGA_VALIDADA / INCONCLUSIVO),
  `data_resolucao`, `dias_pos_resolucao`, `qtd_incs_pos_resolucao`,
  `qtd_incs_pre_resolucao` (60d), delta de chamados vinculados (`delta_chamados_pct`),
  `qtd_prbs_novos_pos_resolucao`. As colunas exatas serão **confirmadas em Phase 2**
  olhando o chart "PRB em Vigilância" atual.
- **D-07:** Painel é consumido **via Superset corporativo**. Chart chamado
  **"PRB Change Team"**, lendo SQL diretamente de `lwsa.motor_change_team_painel`.
  Sem JSON paralelo, sem HTML estático, sem dashboard custom.
- **D-08:** Naming: feature/força-tarefa = `change_team` (em tabela, código, configs).
  Chart visível no Superset = "PRB Change Team".

### Claude's Discretion

- Layout interno do código Python (módulo `change_team.py` dedicado vs. estender
  `extractor.py`) — planner decide em Phase 2.
- Estratégia de transação do TRUNCATE+INSERT (SAVEPOINT explícito vs. transação
  implícita do psycopg2) — planner decide com base em `notifier_db.py`.

### Deferred Ideas (OUT OF SCOPE)

- Sync automático com SNow via etiqueta/campo custom.
- API REST para gerenciar a lista via UI web.
- Multi-força-tarefa (vários painéis simultâneos via `lwsa.motor_iniciativas` + FK).
- Alertas Slack dedicados da Change Team (diferido para Phase 2 ou 3 — default
  inicial: usa o mesmo canal existente de reincidências).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PNCT-01 | Dashboard de acompanhamento dos ~88 PRBs específicos da force-task Change Team. Permite tracking de progresso (prioridade atual, status, idade, ultima_atualizacao), cruzamento com ValidadorEntrega (entregas vs reincidências), potencial cruzamento com Saúde do Cliente. | A Phase 1 deste plano resolve PNCT-01 integralmente via: (a) tabela master `lwsa.motor_change_team` com soft delete; (b) tabela materializada `lwsa.motor_change_team_painel` populada a cada 6h pelo ValidadorEntrega; (c) chart Superset corporativo "PRB Change Team" lendo SQL direto. Veja **Architectural Responsibility Map** abaixo. |
</phase_requirements>

## Summary

A phase implementa uma extensão limpa do **ValidadorEntrega** (já em produção desde maio/2026) que:

1. Lê uma **lista master soft-deleted** de PRBs da Change Team (tabela nova `lwsa.motor_change_team`).
2. Consulta o ServiceNow no mesmo banco compartilhado (`lwsa.service_now_problems`) por esses PRBs específicos **sem janela temporal** (D-03), reaproveitando o parser `_row_para_prb` já existente em `extractor.py`.
3. Para cada PRB resolvido, opcionalmente chama os mesmos sinais já implementados (volumetria pré, Δ chamados vinculados, PRBs novos pós) que o validador V3.1 calcula.
4. Persiste um snapshot completo via **TRUNCATE + INSERT em transação única** numa tabela materializada nova (`lwsa.motor_change_team_painel`), seguindo o padrão atômico já estabelecido em `notifier_db.persistir_execucao`.
5. O Superset corporativo lê `lwsa.motor_change_team_painel` via SQL direto — zero dependência adicional no pipeline do motor.

**O risco principal é o acoplamento ao fluxo do validador.** A query Change Team **deve** rodar em try/except próprio (Princípio "Defense in Depth", DEC-010) para que uma falha sua **nunca** derrube o veredicto V3.1 dos PRBs do fluxo padrão (CON-012 LOCKED). Toda a base técnica já existe — não há nada que precise ser hand-rolled.

**Primary recommendation:** Criar um **módulo dedicado `change_team.py`** (nível 3 — Domínio) com `gerar_painel_change_team(fonte_inc, fonte_chamados) -> List[PainelChangeTeamRow]` + persistência em `notifier_db.py` via nova função `persistir_painel_change_team(rows)`. Chamar como **3º bloco try/except** no `executar_validacao()` de `validar_entregas.py`, **APÓS** `gerar_validacoes_entrega` e `gravar_payload_dashboard`, mas **dentro** do mesmo ciclo e **antes** do `persistir_execucao` final.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Armazenar lista master dos 88 PRBs (soft delete) | Database / Storage (`lwsa.motor_change_team`) | — | D-01 LOCKED: tabela com auditoria, não arquivo. |
| Materializar snapshot do painel (TRUNCATE+INSERT 6h) | Database / Storage (`lwsa.motor_change_team_painel`) | API/Backend (validar_entregas.py orquestra) | D-04 LOCKED: snapshot atômico via padrão OUT-02. |
| Extrair PRBs do SNow por lista (sem janela) | API/Backend — Nível 3 Domínio (`extractor.py::ServiceNowExtractor`) | Database (`lwsa.service_now_problems`) | D-03 LOCKED: nova método em FonteIncidentes; reaproveita `_row_para_prb`. |
| Calcular sinais de acompanhamento pós-resolução (D-06) | API/Backend — Nível 3 Domínio (reaproveita `validador_entrega._avaliar_prb`) | Database (chamados Dynamics) | Reúsa V3.1 sem duplicar lógica. |
| Orquestrar ciclo + integração no entry-point | API/Backend — Nível 4 Orquestração (`validar_entregas.py::executar_validacao`) | OS/Task Scheduler externo (6h via .bat) | D-02 LOCKED: motor é single-run; Task Scheduler é o supervisor. |
| Apresentar painel ao consumidor humano | CDN / Static — Superset corporativo (chart "PRB Change Team") | Database (SQL read-only sobre `motor_change_team_painel`) | D-07 LOCKED: sem dashboard custom; SQL direto no Superset. |
| Seed inicial dos 88 PRBs | Database / Storage (script `sql/seed_change_team.sql`) | — | Default operacional Phase 2 (CONTEXT §Specific Ideas): SQL direto via `INSERT ... ON CONFLICT DO NOTHING`. |

## Project Constraints (from CLAUDE.md)

> Não existe `./CLAUDE.md` no diretório raiz `Motor PRB-INC/` neste momento. Constraints
> efetivas vêm de `PROJECT.md` (CON-001 a CON-013 LOCKED + DEC-001 a DEC-021) e do
> CONTEXT.md desta phase.

| Constraint | Source | Impact on this Phase |
|------------|--------|----------------------|
| CON-012 — ValidadorEntrega V3.1 LOCKED (3 veredictos + 5 sinais) | PROJECT.md | A integração Change Team **NÃO PODE** alterar a saída atual do validador. Adicionada como bloco isolado com try/except próprio. |
| CON-013 — Termos heurísticos word-boundary | PROJECT.md | N/A direto — Change Team filtra por `numero IN (...)`, sem heurística textual. |
| DEC-004 — Single-run + Task Scheduler externo | PROJECT.md | Nenhum loop interno em Python; snapshot por execução. |
| DEC-010 — Defense in Depth (try/except em 4 níveis) | PROJECT.md | Query + persistência Change Team em try/except dedicado. Falha sua não derruba V3.1. |
| DEC-012 — Configurabilidade externa total | PROJECT.md | `CHANGE_TEAM_HABILITADO` (bool env), `TABELA_CHANGE_TEAM`, `TABELA_CHANGE_TEAM_PAINEL` em `config.py`. Sem números mágicos. |
| Postgres 9.2/9.3 compat (`json`, sem `jsonb`, sem `CREATE INDEX IF NOT EXISTS`, sem `IF NOT EXISTS` em colunas) | `sql/motor_tables.sql` cabeçalho | DDL nova segue o mesmo dialeto: `json`, DO blocks com check em `pg_indexes`/`information_schema`. |
| UTF-8 forçado em logs (Windows) | `validar_entregas.py::configurar_logging` + ORCH-03 | Qualquer log novo segue o mesmo formato. |

## Standard Stack

### Core (já presente no projeto — não há nada a instalar)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `psycopg2-binary` | já em produção (versão instalada — não vamos verificar registry porque não estamos adicionando dependência nova) | Driver Postgres síncrono | Já é a stack do motor (PROJECT.md §Context). Transações atômicas via `with conn` + `conn.commit()`. |
| stdlib `dataclasses` | 3.10+ | Modelagem de `PainelChangeTeamRow` | Padrão de `models.py`. |
| stdlib `json` | 3.10+ | Serialização para colunas `json` Postgres | Usado em `notifier_db._jsonb()`. |
| stdlib `logging` | 3.10+ | Logs UTF-8 rotacionados | ORCH-03 LOCKED. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` | já em uso (54+ testes) | Unit tests de `change_team._montar_query`, persistência, ciclo isolado | Sempre antes de commit (DEC-006 implícito). |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Tabela `lwsa.motor_change_team` (D-01) | Arquivo `change_team.txt` em git | **Rejeitado por D-01.** Sem auditoria de quem entrou/saiu da lista, sem soft delete, Superset não lê arquivo. |
| `TRUNCATE + INSERT` (D-04) | `UPSERT (ON CONFLICT)` | **Rejeitado por D-04.** Snapshot completo precisa refletir o estado atual; UPSERT deixaria PRBs órfãos quando saem da lista master. TRUNCATE é mais simples e correto pro modelo de "snapshot completo a cada 6h". |
| Módulo novo `change_team.py` | Estender `validador_entrega.py` | **Discricionário (planner decide).** Recomendação: módulo novo. Validador V3.1 está coeso (~210 linhas) e mexer nele aumenta risco de regredir CON-012. Módulo novo segue Princípio 2 de ARQUITETURA.md (Single Responsibility). |
| Reaproveitar `_avaliar_prb` para PRBs resolvidos da Change Team | Reimplementar sinais pós-resolução só pra Change Team | **Recomendado: reaproveitar.** A função `_avaliar_prb(prb, fonte_inc, fonte_chamados)` em `validador_entrega.py:49-214` aceita qualquer `PRBExistente` com `data_resolucao` e devolve `ValidacaoEntrega` com todos os sinais D-06 já calculados. Zero código novo nesse caminho. |

**Installation:**

Não há `pip install` neste phase. Toda a stack já está em produção.

## Package Legitimacy Audit

Esta phase **não instala dependências novas**. Toda a stack já é a do motor em produção
(`psycopg2-binary`, `pytest`, stdlib). Não há risco de slopsquat/typosquat introduzido por
este phase. Step 1-4 do protocolo: **N/A — nenhum pacote adicionado**.

| Package | Registry | Disposition |
|---------|----------|-------------|
| (nenhum) | — | Phase não adiciona dependência externa |

## Architecture Patterns

### System Architecture Diagram

```
                                   ┌──────────────────────────────┐
                                   │  Windows Task Scheduler      │
                                   │  (Motor-PRB-Validador.bat,   │
                                   │   disparo a cada 6h)         │
                                   └──────────────┬───────────────┘
                                                  │ executa
                                                  ▼
                            ┌───────────────────────────────────────┐
                            │  validar_entregas.py::executar_validacao() │
                            │   (single-run, exit 0/1)              │
                            └──┬─────────────────────────┬──────────┘
                               │                         │
              try/except       │                         │   try/except dedicado
              EXISTENTE        ▼                         ▼   NOVO — Defense in Depth
                  ┌───────────────────────┐   ┌─────────────────────────────────┐
                  │ gerar_validacoes_     │   │ gerar_painel_change_team()      │
                  │ entrega(fonte_inc,    │   │  ├ ler lista master de          │
                  │ fonte_chamados)       │   │  │  lwsa.motor_change_team      │
                  │  (V3.1 — CON-012)     │   │  │  WHERE ativo = true          │
                  │                       │   │  ├ SELECT FROM                  │
                  │                       │   │  │  service_now_problems        │
                  │                       │   │  │  WHERE numero IN (...)       │
                  │                       │   │  │  (SEM janela — D-03)         │
                  │                       │   │  ├ separar abertos vs.          │
                  │                       │   │  │  resolvidos                  │
                  │                       │   │  ├ p/ resolvidos: reaproveitar  │
                  │                       │   │  │  _avaliar_prb()              │
                  │                       │   │  └ devolver List[Painel...Row]  │
                  └─────────┬─────────────┘   └─────────────┬───────────────────┘
                            │                               │
                            ▼                               ▼
                  ┌───────────────────────┐   ┌─────────────────────────────────┐
                  │ persistir_execucao()  │   │ persistir_painel_change_team()  │
                  │ (motor_execucao +     │   │ TRUNCATE lwsa.motor_change_team │
                  │  motor_validacao_*)   │   │ _painel; INSERT N rows;         │
                  │                       │   │ commit ATÔMICO                  │
                  └───────────────────────┘   └─────────────┬───────────────────┘
                                                            │
                                                            ▼
                                              ┌─────────────────────────────────┐
                                              │ Apache Superset (corporativo)   │
                                              │  Chart "PRB Change Team"        │
                                              │   SELECT ... FROM               │
                                              │   lwsa.motor_change_team_painel │
                                              └─────────────────────────────────┘
```

**Leitura do diagrama:** o fluxo padrão do validador (left side) **permanece intacto**.
A integração Change Team (right side) é um **caminho paralelo independente** dentro
do mesmo ciclo de 6h, com try/except próprio que isola falhas.

### Recommended Project Structure (estendendo o existente, sem refactor)

```
Motor PRB-INC/
├── change_team.py             # NOVO — módulo Nível 3 Domínio:
│                              #   gerar_painel_change_team(fonte_inc, fonte_chamados)
│                              #   _separar_abertos_vs_resolvidos(prbs)
│                              #   _row_para_painel_aberto(prb) / _row_para_painel_resolvido(validacao)
├── validar_entregas.py        # EDIT — adiciona 3º bloco try/except em executar_validacao()
├── extractor.py               # EDIT — adiciona método novo na ABC FonteIncidentes:
│                              #   listar_prbs_por_numero(numeros: Sequence[str]) -> List[PRBExistente]
│                              #   + implementação real + mock + carrega lista master via
│                              #   _ler_lista_change_team_ativa() (helper auxiliar ou em change_team.py)
├── models.py                  # EDIT — adiciona dataclass PainelChangeTeamRow
├── notifier_db.py             # EDIT — adiciona persistir_painel_change_team(rows)
├── config.py                  # EDIT — adiciona:
│                              #   CHANGE_TEAM_HABILITADO (bool, default true)
│                              #   TABELA_CHANGE_TEAM = "motor_change_team"
│                              #   TABELA_CHANGE_TEAM_PAINEL = "motor_change_team_painel"
├── sql/
│   ├── motor_tables.sql       # EDIT — adiciona DDL das 2 tabelas novas
│   └── seed_change_team.sql   # NOVO — INSERT ... ON CONFLICT DO NOTHING dos 88 PRBs
└── tests/
    └── test_change_team.py    # NOVO — unit tests do módulo
```

### Pattern 1: Transação atômica TRUNCATE+INSERT (snapshot completo)

**What:** num único ciclo, limpa a tabela materializada e popula tudo de novo, garantindo que ou tudo grava ou nada grava — sem estado intermediário visível para o Superset.
**When to use:** D-04 LOCKED. Snapshot completo a cada 6h.

**Reference implementation pattern:** seguir o padrão de `notifier_db.persistir_execucao` (linhas 294-341), que já faz transação única envolvendo múltiplos INSERTs com `conn.commit()` no final.

**Example:**

```python
# Source: padrão estabelecido em notifier_db.py:319-327
def persistir_painel_change_team(rows: List[PainelChangeTeamRow]) -> int:
    """TRUNCATE + INSERT atômico do painel Change Team.

    Padrão D-04 (snapshot completo). Mesmo idioma de `notifier_db.persistir_execucao`:
    `with conectar() as conn` + cursor manual + commit explícito ao final.
    Sem TRUNCATE ... CASCADE — não há FK apontando pra essa tabela.
    """
    if not config.PERSISTIR_NO_BANCO:
        log.info("Persistência Postgres desabilitada — pulando painel Change Team.")
        return 0
    try:
        from db import conectar
        with conectar() as conn:
            with conn.cursor() as cur:
                # 1) Limpa snapshot anterior. RESTART IDENTITY zera o serial do PK.
                cur.execute(
                    f"TRUNCATE TABLE lwsa.{config.TABELA_CHANGE_TEAM_PAINEL} RESTART IDENTITY"
                )
                # 2) Insere snapshot novo em batch.
                sql = """
                    INSERT INTO lwsa.motor_change_team_painel (
                        prb_id, descricao_curta, produto, servidor,
                        status_snow, prioridade_atual, dias_em_aberto,
                        grupo_designado, ultima_atualizacao,
                        veredicto, data_resolucao, dias_pos_resolucao,
                        qtd_incs_pos_resolucao, qtd_incs_pre_resolucao,
                        delta_chamados_pct, qtd_prbs_novos_pos_resolucao,
                        snapshot_em
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s)
                """
                cur.executemany(sql, [
                    (r.prb_id, r.descricao_curta, r.produto, r.servidor,
                     r.status_snow, r.prioridade_atual, r.dias_em_aberto,
                     r.grupo_designado, r.ultima_atualizacao,
                     r.veredicto, r.data_resolucao, r.dias_pos_resolucao,
                     r.qtd_incs_pos_resolucao, r.qtd_incs_pre_resolucao,
                     r.delta_chamados_pct, r.qtd_prbs_novos_pos_resolucao,
                     r.snapshot_em)
                    for r in rows
                ])
                conn.commit()  # ATÔMICO: ou ambos rodam ou rollback automático.
        log.info("Painel Change Team gravado: %d rows.", len(rows))
        return len(rows)
    except Exception as exc:
        log.exception("Falha ao persistir painel Change Team: %s", exc)
        return 0
```

**Por que `TRUNCATE` em vez de `DELETE`:**

- `TRUNCATE` é DDL: mais rápido, não gera WAL row-by-row, libera espaço imediatamente.
- `TRUNCATE ... RESTART IDENTITY` reseta o `serial` PK (pequeno conforto operacional).
- Sem FK apontando pra essa tabela (é folha do modelo), então `CASCADE` é desnecessário.
- `TRUNCATE` dentro de transação **é seguro em Postgres** — se a transação der rollback, o TRUNCATE também é desfeito. Confirmação: Postgres manual oficial, comportamento padrão. [VERIFIED: postgresql.org/docs — TRUNCATE é transacional em Postgres ≥ 8.4]

### Pattern 2: Defense in Depth no entry-point do validador

**What:** adicionar a etapa Change Team como 3º bloco `try/except` em `executar_validacao()` — falhas dela **não derrubam** a V3.1.
**When to use:** sempre que se adiciona feature opcional a um pipeline crítico (Princípio 1 — Defense in Depth, DEC-010).

**Example:**

```python
# Source: padrão de validar_entregas.py:69-101
def executar_validacao() -> ExecucaoMotor:
    log = logging.getLogger("validador")
    inicio = time.monotonic()

    fonte_inc = criar_fonte_incidentes()
    fonte_chamados = criar_fonte_chamados()
    execucao = ExecucaoMotor(timestamp=time_utils.agora_utc())

    # --- BLOCO EXISTENTE: V3.1 (CON-012 — não tocar) -----------------------
    try:
        execucao.validacoes_entrega = gerar_validacoes_entrega(
            fonte_inc, fonte_chamados
        )
    except Exception as exc:
        log.exception("Falha no ValidadorEntrega: %s", exc)
        execucao.erros.append(f"validador_entrega: {exc}")

    # --- BLOCO NOVO: Painel Change Team (defense in depth) ------------------
    if config.CHANGE_TEAM_HABILITADO:
        try:
            from change_team import gerar_painel_change_team
            from notifier_db import persistir_painel_change_team
            rows = gerar_painel_change_team(fonte_inc, fonte_chamados)
            persistir_painel_change_team(rows)
        except Exception as exc:
            log.exception("Falha no Painel Change Team: %s", exc)
            execucao.erros.append(f"change_team: {exc}")
    # ------------------------------------------------------------------------

    # --- Restante intocado: JSON, persistência V3.1, Slack ------------------
    try:
        gravar_payload_dashboard(execucao, caminho=JSON_OUTPUT_PATH)
    except Exception as exc:
        log.exception("Falha ao gravar JSON: %s", exc)
        execucao.erros.append(f"json_dashboard: {exc}")

    execucao.duracao_ciclo_ms = int((time.monotonic() - inicio) * 1000)
    persistir_execucao(execucao)
    disparar_alertas_criticos(execucao)
    return execucao
```

**Chaves desse pattern:**

1. **Import lazy** (`from change_team import ...` **dentro** do `if`) — se o módulo
   tiver bug de import, isso não derruba o entry-point. (Mesma técnica usada com
   `from db import conectar` em `notifier_db.py` — lazy imports são padrão do projeto.)
2. **Flag `CHANGE_TEAM_HABILITADO` em config** — desligamento operacional sem deploy.
3. **try/except COM `log.exception`** — preserva traceback completo no log
   (mesmo padrão de `notifier_db.persistir_execucao`).
4. **`execucao.erros.append(...)`** — sinaliza falha no JSON do dashboard mas
   continua o ciclo (mesmo padrão dos outros blocos).

### Pattern 3: Reaproveitar o motor V3.1 para PRBs resolvidos (sem duplicação)

**What:** para os PRBs Change Team que estão resolvidos (status em `STATUS_PRB_ENCERRADOS`), usar **o mesmo** `_avaliar_prb(prb, fonte_inc, fonte_chamados)` que o validador V3.1 usa. Sem reimplementar volumetria pré, Δ chamados, PRBs novos pós.
**When to use:** PRBs Change Team resolvidos (D-06 colunas pós-resolução).

**Example:**

```python
# Source: change_team.py NOVO — chama validador_entrega._avaliar_prb diretamente
from validador_entrega import _avaliar_prb, VEREDICTO_REINCIDENCIA, VEREDICTO_VALIDADA, VEREDICTO_INCONCLUSIVO

def _row_para_painel_resolvido(prb: PRBExistente, fonte_inc, fonte_chamados) -> PainelChangeTeamRow:
    validacao = _avaliar_prb(prb, fonte_inc, fonte_chamados)
    return PainelChangeTeamRow(
        prb_id=prb.prb_id,
        descricao_curta=prb.descricao_curta,
        produto=prb.produto,
        servidor=prb.servidor,
        status_snow=prb.status,
        prioridade_atual=prb.prioridade_atual,
        dias_em_aberto=(validacao.data_resolucao - prb.aberto_em).days if prb.aberto_em else None,
        grupo_designado=prb.grupo_designado,
        ultima_atualizacao=prb.data_resolucao,  # PRB encerrado: última atualização ≈ data_encerrado
        veredicto=validacao.veredicto,
        data_resolucao=validacao.data_resolucao,
        dias_pos_resolucao=validacao.dias_pos_resolucao,
        qtd_incs_pos_resolucao=validacao.qtd_incs_pos_resolucao,
        qtd_incs_pre_resolucao=validacao.qtd_incs_pre_resolucao,
        delta_chamados_pct=validacao.delta_chamados_pct,
        qtd_prbs_novos_pos_resolucao=validacao.qtd_prbs_novos_pos_resolucao,
        snapshot_em=time_utils.agora_utc(),
    )
```

**Por que isso é seguro:** `_avaliar_prb` é função pura sobre `PRBExistente` (não depende de janela ou lista específica). Ela já tem try/except internos (linhas 99-109, 121-167, 178-188) que zeram sinais em falha sem propagar exceção. Reaproveitamento honra o **Princípio 2 — Single Responsibility** (V3.1 calcula sinais; Change Team apenas seleciona quais PRBs e onde gravar).

### Anti-Patterns to Avoid

- **Acoplar a query Change Team dentro de `gerar_validacoes_entrega`:** quebra Princípio 2 e
  arrisca regressar CON-012. **Não fazer.** Manter os dois fluxos como módulos separados
  que partilham `_avaliar_prb` por composição.
- **Usar `DELETE` + `INSERT` em transações separadas:** abre janela em que o Superset pode
  ler tabela vazia/parcial. **Não fazer.** TRUNCATE+INSERT na mesma transação resolve.
- **Hardcoded `WHERE numero IN ('PRB001', 'PRB002', ...)` em Python:** quebra D-01 (lista
  mora em tabela, não em código). **Não fazer.** Sempre ler de `lwsa.motor_change_team
  WHERE ativo = true`.
- **TRUNCATE sem RESTART IDENTITY com FK CASCADE em tabela com filhas:** não se aplica
  aqui (tabela é folha), mas mencionado para evitar pattern errado em phases futuras.
- **Refazer o cálculo dos sinais pós-resolução em `change_team.py`:** duplicação que vai
  divergir do validador V3.1 ao longo do tempo. **Não fazer.** Reaproveitar `_avaliar_prb`.
- **Usar JSON paralelo em `output/change_team_painel.json` SEM o usuário pedir:** D-07
  LOCKED é Superset SQL direto. O CONTEXT.md menciona o JSON paralelo como
  "decisão do planner, não obrigatório" — recomendação desta research é **NÃO** criar
  o JSON paralelo. Se Postgres cair, o painel do Superset fica defasado por até 6h —
  aceitável dado D-07. Cria um JSON desnecessário se sempre rodar Postgres OK.

## Don't Hand-Roll

| Problema | Don't Build | Use Instead | Why |
|----------|-------------|-------------|-----|
| Cálculo de sinais pós-resolução (Δ chamados, volumetria pré, PRBs novos) | Reimplementar SQL de volumetria, vinculação inc/prb, etc. | `validador_entrega._avaliar_prb(prb, fonte_inc, fonte_chamados)` | A função já existe, é testada em `tests/test_validador_entrega.py` e tem defesa em camadas interna. Duplicar é introduzir bugs sutis. |
| Parser SNow row → `PRBExistente` | Mapear colunas manualmente | `ServiceNowExtractor._row_para_prb(row)` (extractor.py:461-478) | Já lida com `_parse_datetime`, `_parse_prioridade`, COALESCE de campos nulos. |
| Filtro de organização nas queries | Concatenar string SQL | `_filtro_orgs_sni()` (extractor.py:240-251) | Já está parametrizado contra SQL injection e usa `config.ORGANIZACOES_ATIVAS`. |
| Transação atômica multi-INSERT | Implementar BEGIN/COMMIT/ROLLBACK manual | `with conectar() as conn` + `with conn.cursor() as cur` + `conn.commit()` | Padrão de `notifier_db.persistir_execucao`. psycopg2 abre transação implícita no primeiro execute() e faz rollback automático se a exception escapar do context manager. |
| Conexão Postgres | `psycopg2.connect(...)` solto | `db.conectar()` context manager | Já lê config.ini, fecha conexão em qualquer caminho (try/finally). |
| Serialização JSON pra colunas `json` | `json.dumps(...)` manual | `notifier_db._jsonb(valor)` | Já lida com `default=str` defensivo (datetime/Decimal). |
| Conversão BRT↔UTC | `datetime.now()` ou tz manual | `time_utils.agora_utc()` + `time_utils.utc_para_string_banco(dt)` | Princípio 4 — UTC interno, fronteiras locais. Bug histórico já corrigido. |
| Logging UTF-8 no Windows | `print(...)` ou setup ad-hoc | Reaproveitar `validar_entregas.configurar_logging()` (já é chamado pelo entry-point) | ORCH-03 + bug histórico de console Windows. |
| Idempotência de DDL em Postgres 9.2/9.3 | `CREATE INDEX IF NOT EXISTS` (não existe em 9.2-9.4) | `DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_indexes ...) THEN ... END IF; END $$;` | Padrão estabelecido em `sql/motor_tables.sql:37-42, 71-85, 110-121` etc. |
| Mock para a Fonte | Estender ServiceNowExtractorMock manualmente | Adicionar método `listar_prbs_por_numero` + `_ler_lista_change_team_ativa` mock no mesmo arquivo | Factory `criar_fonte_incidentes()` já alterna mock vs real via `USAR_MOCKS`. |

**Key insight:** o motor já tem **TODOS** os blocos de Lego necessários. O trabalho desta phase é
**composição** — adicionar uma orquestração nova (`change_team.py`) e dois containers Postgres
novos (`motor_change_team`, `motor_change_team_painel`). Zero algoritmo novo precisa ser inventado.

## Runtime State Inventory

> Phase é **rename / refactor / migration?** Não. É greenfield aditivo (cria 2 tabelas
> novas + 1 módulo novo + 1 script de seed). Sem renomeação de strings, sem migração
> de dados existentes, sem mudança de identificadores em runtime cacheados.

| Categoria | Items Found | Action Required |
|-----------|-------------|------------------|
| Stored data | Nenhum — a tabela `lwsa.motor_change_team` será criada por esta phase. PRBs no SNow continuam tendo o mesmo `numero` (sem renomeação). | None — verified by inexistência da tabela no `sql/motor_tables.sql` atual. |
| Live service config | Nenhum — não há n8n, Datadog tags, Tailscale ACL, Cloudflare Tunnel envolvidos. Superset é configurado manualmente (D-07) — entendido como ação manual do humano, não cache automatizado. | Phase 2 abre **ação aberta para humano**: criar o chart "PRB Change Team" no Superset apontando para a nova tabela. |
| OS-registered state | Task Scheduler já registrou `Motor-PRB-Validador.bat` (6h). O entry-point é o mesmo — **NÃO** precisa re-registrar a task. | None — verified by `validar_entregas.py` continuar sendo o entry-point. |
| Secrets/env vars | Nenhum novo. `config.ini` compartilhado já tem a credencial Postgres. Novas flags `CHANGE_TEAM_HABILITADO` são opcionais e têm default sensato. | None. |
| Build artifacts / installed packages | Nenhum. Sem `pip install`, sem `npm install`, sem .egg-info, sem container rebuild. | None. |

**Conclusão da inventory:** esta phase é **purely additive**. Não há estado quente
para invalidar. A única ação manual fora do código é a criação do chart no Superset
(D-07) — registrada como ação aberta.

## Common Pitfalls

### Pitfall 1: TRUNCATE silenciosamente bloqueado por LOCK pesado

**What goes wrong:** `TRUNCATE` requer `ACCESS EXCLUSIVE` lock — se outra
sessão estiver lendo `motor_change_team_painel` no momento exato do ciclo
(ex.: Superset abrindo o chart), TRUNCATE espera (até `lock_timeout`) ou bloqueia.
**Why it happens:** Postgres trata `TRUNCATE` como DDL; readers ativos do Superset
mantêm `ACCESS SHARE`, que conflita com `ACCESS EXCLUSIVE`.
**How to avoid:**
1. Snapshot a cada 6h (D-04) — não é frequência crítica, alguns segundos de espera
   são aceitáveis.
2. **Não** usar `lock_timeout` zero (default Postgres). Manter o default (sem timeout)
   ou definir `SET LOCAL lock_timeout = '30s'` na transação. Se estourar, o try/except
   externo em `executar_validacao` captura e o snapshot fica defasado por 6h —
   degradação suave (Princípio 7).
3. Documentar no comentário do código: "TRUNCATE pode aguardar leitores Superset
   no momento do ciclo — não é um bug."

**Warning signs:** logs com `Falha ao persistir painel Change Team: deadlock detected`
ou `canceling statement due to lock timeout`.

### Pitfall 2: Lista master desatualizada (PRBs que saíram da Change Team continuam aparecendo)

**What goes wrong:** o snapshot reflete fielmente quem tem `ativo = true` na master
tabela. Se Emerson esquecer de marcar um PRB removido como `ativo = false`, ele
continua no painel.
**Why it happens:** D-01 LOCKED a soft delete via tabela com gestão manual. Sem
sync com SNow.
**How to avoid:**
1. O `seed_change_team.sql` (Phase 2) deve incluir um comentário explícito no
   topo: "Para remover um PRB, NÃO delete a linha — atualize `ativo = false,
   removido_em = NOW(), observacao = '...'`."
2. Phase 3+ pode opcionalmente adicionar uma view `lwsa.motor_change_team_ativos`
   com `SELECT * WHERE ativo = true`. Mas para o MVP, basta o WHERE explícito
   na query do extractor (`listar_prbs_por_numero` só recebe os ativos).
3. Considerar adicionar um índice parcial:
   `CREATE INDEX idx_motor_change_team_ativos ON lwsa.motor_change_team (numero)
   WHERE ativo = true;` (mas só vale a pena se a tabela crescer muito; 88 rows
   não justifica nada).

**Warning signs:** Emerson reportar "esse PRB já saiu da Change Team mas continua
no chart"; SQL `SELECT numero, ativo, removido_em FROM lwsa.motor_change_team
WHERE numero IN (...)` retorna PRBs marcados como removidos.

### Pitfall 3: PRBs Change Team SEM `produto` ou `servidor` (CI) e SEM `data_encerrado`

**What goes wrong:** PRBs com `produto IS NULL` ou `servidor IS NULL` viram `INCONCLUSIVO`
direto em `_avaliar_prb` (linhas 73-90) — sem cálculo de sinais pós. PRBs com `status
= 'Aguardando Validação da Resolução'` no DW da Locaweb **sempre** têm `data_encerrado
NULL` (decisão registrada em 2026-05-28, `config.STATUS_PRB_ENCERRADOS`).
**Why it happens:** `lwsa.service_now_problems` tem campos nullable; CTs reais nem
sempre preenchem CI antes de encerrar; status intermediário do SNow não popula a
data no DW da Locaweb.
**How to avoid:**
1. No `change_team.py`, separar PRBs em 3 grupos:
   - **Abertos** (status ∈ `STATUS_PRB_ATIVOS` OU `data_encerrado IS NULL`): D-05 colunas só.
   - **Resolvidos com data + CI** (status ∈ `STATUS_PRB_ENCERRADOS` E `produto` E
     `servidor` truthy): D-06 colunas completas.
   - **Resolvidos sem CI**: aparecem como "Abertos" com `status_snow` reportado
     fielmente — ou aparecem em D-06 com veredicto `INCONCLUSIVO` e sinais zerados.
     **Recomendação:** tratar como D-06 com sinais zerados — Emerson saberá visualmente
     que o PRB tem dado faltando (`produto = NULL` no chart).
2. Documentar no Slack/Superset: "PRBs sem CI viram INCONCLUSIVO eterno — pedir
   ao Change Team pra preencher produto/servidor."

**Warning signs:** chart "PRB Change Team" com colunas `produto`/`servidor` vazias;
log com `_avaliar_prb: PRB %s sem produto/servidor — pulando match de reincidência.`

### Pitfall 4: Query Change Team duplica round-trips ao SNow

**What goes wrong:** ingênuo, `gerar_painel_change_team` faz 1 query para a lista
master + 1 query para o SNow + N queries por PRB (1 por sinal de cada PRB resolvido).
Para 88 PRBs com ~30 resolvidos, isso são ~120-150 queries.
**Why it happens:** `_avaliar_prb` chama várias sub-fontes (`listar_incidentes_por_produto_servidor`
×2, `contar_incidentes_no_ci_periodo` ×1, `contar_chamados_vinculados` ×2,
`listar_prbs_novos_no_ci_periodo` ×1, etc.).
**How to avoid:** **aceitar** isso no MVP. O validador V3.1 já faz o mesmo padrão
para os ~10 PRBs do fluxo normal (~50 queries) e leva ~20-30s. Para 88 PRBs Change
Team, espera-se ~3× isso (~60-90s). Continua aceitável dentro do ciclo de 6h.
Otimização (bulk via CTE) **fica para Phase futura** se medirmos lentidão real.

**Warning signs:** `duracao_ciclo_ms` do validador subindo de ~30s para >5min;
DBA reclamando de carga em horários de pico.

### Pitfall 5: Inconsistência entre "ativo na master" e "encontrado no SNow"

**What goes wrong:** se um PRB está em `lwsa.motor_change_team` como `ativo = true`
mas o SNow não devolve esse `numero` (digitação errada, PRB deletado no SNow), o
painel vai ter "buraco". Pior: Emerson não vai saber qual PRB sumiu.
**Why it happens:** tabela master pode divergir do SNow.
**How to avoid:**
1. No `change_team.py`, computar `prbs_ativos_master - prbs_retornados_pelo_snow`
   e logar como warning: `log.warning("PRBs Change Team na master mas não no SNow:
   %s", missing)`.
2. Considerar incluir esses PRBs no painel com `status_snow = 'NÃO ENCONTRADO NO SNOW'`
   e demais campos NULL — torna o problema visível no chart.

**Warning signs:** "Esperava 88 PRBs no chart mas só apareceram 86".

### Pitfall 6: `_avaliar_prb` exige `prb.aberto_em` populado mas D-05 pede `dias_em_aberto`

**What goes wrong:** o campo `dias_em_aberto` (D-05) é definido como `(NOW() -
prb.aberto_em).days` para PRBs abertos OU `(data_resolucao - prb.aberto_em).days`
para resolvidos. Se `prb.aberto_em IS NULL` (`_parse_datetime` devolveu None
silenciosamente), o cálculo crasha com `TypeError`.
**Why it happens:** `service_now_problems.data_abertura` pode estar vazio em
edge cases — `_parse_datetime` retorna `None` defensivamente.
**How to avoid:** `dias_em_aberto = (ref - prb.aberto_em).days if prb.aberto_em
else None`. Coluna SQL aceita NULL (`int NULL`). No chart, NULL aparece como vazio
— ainda mais visível que valor errado.

**Warning signs:** stacktrace `TypeError: unsupported operand type(s) for -:
'datetime.datetime' and 'NoneType'`.

## Code Examples

Padrões verificados a partir dos arquivos do projeto.

### Exemplo 1 — DDL idempotente das 2 tabelas novas

```sql
-- Source: padrão de sql/motor_tables.sql:23-91 (Postgres 9.2/9.3 compat)

-- ----------------------------------------------------------------------------
-- N. motor_change_team — lista master soft-deleted (D-01)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lwsa.motor_change_team (
    id              serial PRIMARY KEY,
    numero          varchar(20) NOT NULL UNIQUE,
    ativo           boolean NOT NULL DEFAULT true,
    adicionado_em   timestamp with time zone NOT NULL DEFAULT NOW(),
    removido_em     timestamp with time zone,
    observacao      text
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='lwsa' AND indexname='idx_motor_change_team_numero') THEN
        CREATE INDEX idx_motor_change_team_numero ON lwsa.motor_change_team(numero);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='lwsa' AND indexname='idx_motor_change_team_ativos') THEN
        CREATE INDEX idx_motor_change_team_ativos ON lwsa.motor_change_team(numero) WHERE ativo = true;
    END IF;
END $$;

COMMENT ON TABLE  lwsa.motor_change_team IS 'Lista master da force-task Change Team — PRBs sob acompanhamento dedicado. Soft delete via ativo/removido_em.';
COMMENT ON COLUMN lwsa.motor_change_team.numero IS 'Identificador do PRB no ServiceNow (ex.: "PRB0072001"). UNIQUE — uma linha por PRB.';
COMMENT ON COLUMN lwsa.motor_change_team.ativo IS 'true = aparece no painel; false = histórico (mantém auditoria de quem foi Change Team em algum momento).';
COMMENT ON COLUMN lwsa.motor_change_team.observacao IS 'Texto livre — motivo da entrada/saída, link interno, etc.';

-- ----------------------------------------------------------------------------
-- N+1. motor_change_team_painel — snapshot materializado (D-04 / D-05 / D-06)
-- ----------------------------------------------------------------------------
-- Reescrita inteira a cada execução do ValidadorEntrega (6h) via TRUNCATE+INSERT
-- atômico. Sem FK pra motor_execucao porque snapshot é independente do ciclo
-- (sem chave de versionamento — só o estado atual interessa).
CREATE TABLE IF NOT EXISTS lwsa.motor_change_team_painel (
    id                              serial PRIMARY KEY,
    prb_id                          varchar(20) NOT NULL,
    descricao_curta                 varchar(500),
    produto                         varchar(255),
    servidor                        varchar(255),
    status_snow                     varchar(100),
    prioridade_atual                varchar(5),
    dias_em_aberto                  int,
    grupo_designado                 varchar(255),
    ultima_atualizacao              timestamp with time zone,
    -- Campos só preenchidos quando PRB está resolvido (D-06):
    veredicto                       varchar(30),       -- NULL para abertos
    data_resolucao                  timestamp with time zone,
    dias_pos_resolucao              int,
    qtd_incs_pos_resolucao          int,
    qtd_incs_pre_resolucao          int,
    delta_chamados_pct              numeric(8,3),
    qtd_prbs_novos_pos_resolucao    int,
    -- Auditoria:
    snapshot_em                     timestamp with time zone NOT NULL DEFAULT NOW()
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='lwsa' AND indexname='idx_motor_ct_painel_prb') THEN
        CREATE INDEX idx_motor_ct_painel_prb ON lwsa.motor_change_team_painel(prb_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='lwsa' AND indexname='idx_motor_ct_painel_status') THEN
        CREATE INDEX idx_motor_ct_painel_status ON lwsa.motor_change_team_painel(status_snow);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='lwsa' AND indexname='idx_motor_ct_painel_veredicto') THEN
        CREATE INDEX idx_motor_ct_painel_veredicto ON lwsa.motor_change_team_painel(veredicto) WHERE veredicto IS NOT NULL;
    END IF;
END $$;

COMMENT ON TABLE  lwsa.motor_change_team_painel IS 'Snapshot materializado dos PRBs Change Team. Reescrito inteiro a cada 6h pelo ValidadorEntrega (TRUNCATE+INSERT atômico). Consumido pelo chart "PRB Change Team" no Superset.';
COMMENT ON COLUMN lwsa.motor_change_team_painel.veredicto IS 'NULL para PRBs ainda abertos; REINCIDENCIA/ENTREGA_VALIDADA/INCONCLUSIVO para resolvidos.';
COMMENT ON COLUMN lwsa.motor_change_team_painel.snapshot_em IS 'Timestamp de quando este snapshot foi gravado — monitora frescor do painel.';
```

### Exemplo 2 — Método novo no extractor (`listar_prbs_por_numero`)

```python
# Source: padrão de extractor.py:538-601 (listar_prbs_abertos, listar_prbs_novos_no_ci_periodo)

# Em FonteIncidentes (ABC):
@abstractmethod
def listar_prbs_por_numero(self, numeros: Sequence[str]) -> List[PRBExistente]:
    """PRBs por número exato (sem janela temporal — D-03).

    Aceita qualquer status. Devolve um PRBExistente por número encontrado
    no SNow. Números fornecidos que não baterem no SNow são silenciosamente
    omitidos — chamador deve comparar input vs output para detectar misses.
    """
    ...

# Em ServiceNowExtractor:
def listar_prbs_por_numero(self, numeros: Sequence[str]) -> List[PRBExistente]:
    """Implementação real — sem janela, sem filtro de status.

    Aplica filtro de organização (mesmo padrão de listar_prbs_abertos) para
    coerência com o resto do extractor. Edge case: lista vazia → retorna [].
    """
    if not numeros:
        return []
    placeholders = ",".join(["%s"] * len(numeros))
    filtro_org, params_org = _filtro_orgs_sni()
    sql = f"""
        SELECT numero, descricao_curta, descricao, produto, servidor,
               prioridade, status, solucao_alternativa, categoria, subcategoria,
               grupo_designado, atualizacoes, data_abertura, data_encerrado
        FROM {config.SCHEMA_BANCO}.{config.TABELA_PROBLEMAS}
        WHERE numero IN ({placeholders})
          {filtro_org}
    """
    rows = self._query(sql, tuple(numeros) + params_org)
    return [self._row_para_prb(r) for r in rows]
```

### Exemplo 3 — Helper para ler a lista master (com filtro `ativo = true`)

```python
# Source: change_team.py NOVO — função interna

def _ler_lista_change_team_ativa() -> List[str]:
    """Lê os PRBs com ativo = true da master tabela. Retorna lista de 'numero'.

    Falha graciosamente: erro de conexão → retorna [] e loga warning. Caller
    (`gerar_painel_change_team`) detecta lista vazia e pula sem persistir.
    """
    sql = "SELECT numero FROM lwsa.motor_change_team WHERE ativo = true ORDER BY numero"
    try:
        from db import conectar
        with conectar() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                return [row[0] for row in cur.fetchall()]
    except Exception as exc:
        log.warning("Falha ao ler lista Change Team master: %s", exc)
        return []
```

### Exemplo 4 — `seed_change_team.sql` idempotente (Phase 2)

```sql
-- Source: padrão idiomático Postgres 9.5+ (UPSERT)
-- Postgres 9.2/9.3 NÃO TEM ON CONFLICT — verificar versão real antes!
-- Fallback para 9.2/9.3: usar PL/pgSQL com IF NOT EXISTS por linha.

-- Para Postgres >= 9.5 (preferido se disponível):
INSERT INTO lwsa.motor_change_team (numero, ativo, observacao) VALUES
    ('PRB0050001', true, 'Lote inicial Change Team — 2026-06-05'),
    ('PRB0050002', true, 'Lote inicial Change Team — 2026-06-05'),
    -- ... os outros ~86 PRBs ...
    ('PRB0072088', true, 'Lote inicial Change Team — 2026-06-05')
ON CONFLICT (numero) DO NOTHING;
```

**Atenção crítica:** Postgres 9.2/9.3 (versão da Locaweb conforme PROJECT.md §Context)
**não suporta `ON CONFLICT`** — só foi introduzido em 9.5. **Ação aberta para o
planner:** descobrir a versão exata do Postgres da Locaweb antes de fechar o
seed (rodar `SELECT version();` ou perguntar ao DBA). Fallbacks:

- **Se Postgres >= 9.5:** `INSERT ... ON CONFLICT (numero) DO NOTHING` (padrão limpo).
- **Se Postgres < 9.5:** loop PL/pgSQL com `IF NOT EXISTS (SELECT 1 FROM ... WHERE numero=...)
  THEN INSERT ...`. Mais verboso mas funciona.

Esta é uma **assunção [ASSUMED]** que precisa virar **decisão do planner** em Phase 2.

### Exemplo 5 — Teste unitário do módulo

```python
# Source: tests/test_change_team.py NOVO
# Padrão de tests/test_validador_entrega.py (Fake fonte sem rede)
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import List

import config
from models import PRBExistente
from tests.builders import make_prb  # já existe; faz PRBExistente padronizado
from change_team import gerar_painel_change_team


class _FakeFonteCT:
    """Fake fonte que implementa apenas o que change_team precisa."""
    def __init__(self, prbs_por_numero: dict[str, PRBExistente]):
        self._prbs = prbs_por_numero
    def listar_prbs_por_numero(self, numeros):
        return [self._prbs[n] for n in numeros if n in self._prbs]
    # ... outros métodos abstract: raise NotImplementedError


def test_painel_separa_abertos_de_resolvidos(monkeypatch):
    monkeypatch.setattr(
        "change_team._ler_lista_change_team_ativa",
        lambda: ["PRB0000001", "PRB0000002"],
    )
    fonte = _FakeFonteCT({
        "PRB0000001": make_prb("PRB0000001", status="Em Análise", data_resolucao=None),
        "PRB0000002": make_prb("PRB0000002", status="Concluído",
                               data_resolucao=datetime(2026, 5, 30, tzinfo=timezone.utc)),
    })
    rows = gerar_painel_change_team(fonte, fonte_chamados=None)
    assert len(rows) == 2
    aberto = next(r for r in rows if r.prb_id == "PRB0000001")
    resolvido = next(r for r in rows if r.prb_id == "PRB0000002")
    assert aberto.veredicto is None
    assert resolvido.veredicto in ("REINCIDENCIA", "ENTREGA_VALIDADA", "INCONCLUSIVO")


def test_painel_lista_vazia_nao_quebra(monkeypatch):
    monkeypatch.setattr("change_team._ler_lista_change_team_ativa", lambda: [])
    rows = gerar_painel_change_team(fonte_inc=None, fonte_chamados=None)
    assert rows == []
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| (N/A — feature nova) | Tabela `lwsa.motor_change_team_painel` materializada via TRUNCATE+INSERT | Phase 1 (a ser implementada) | Substitui o "nada" — sem alternativa anterior. |

**Deprecated / outdated no contexto desta phase:**

- **`contar_chamados_por_produto` (extractor.py:1147-1193)** — marcado como `[DEPRECATED]`
  na própria função. **NÃO usar.** Para qualquer cálculo de delta de chamados pré/pós
  no Change Team, usar `contar_chamados_vinculados` (V3). Já era o padrão da V3.1.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Postgres da Locaweb é 9.2 ou 9.3 (conforme PROJECT.md §Context). Implica que `ON CONFLICT (...)` no `seed_change_team.sql` **não funciona** sem fallback PL/pgSQL. | Code Examples §4 | Se for 9.5+, o seed simples com `ON CONFLICT` funciona e o fallback é desnecessário. Risco operacional: tentar rodar `ON CONFLICT` em 9.4 ou menor e falhar. **Recomenda-se rodar `SELECT version()` no banco em Phase 2 antes de fechar o seed.** [ASSUMED] |
| A2 | A função `_avaliar_prb` em `validador_entrega.py` aceita PRBs com `data_resolucao = None` e devolve veredicto INCONCLUSIVO sem crash (linhas 67-90 + 49). Verifiquei a função; ela tem defesa interna. | Pattern 3 + Pitfall 3 | Se algum edge case crashar (PRB sem `prb.aberto_em`), o try/except em `gerar_painel_change_team` captura — não derruba o validador, só zera essa row. | [VERIFIED: validador_entrega.py:49-214] |
| A3 | Não há trigger BEFORE/AFTER em `lwsa.motor_change_team_painel` (não existe ainda) que possa quebrar o TRUNCATE. | Pattern 1 | Como tabela é criada por esta phase, esse risco é zero. | [VERIFIED] |
| A4 | O Superset corporativo aceita SQL apontando para `lwsa.motor_change_team_painel` SEM configuração de driver/conexão adicional (a conexão Postgres lwsa já existe no Superset porque outros charts já usam `lwsa.motor_*`). | D-07 + Open Question 1 | Se a conexão não estiver lá, Phase 2 precisa abrir ticket DBA antes do go-live. | [ASSUMED] |
| A5 | A estrutura exata do chart "PRB em Vigilância" (D-06 quer espelhar) **não é investigável pelo agent** — Superset é externo. Estamos assumindo que as colunas propostas em D-06 cobrem ~80% do que o chart existente mostra. | Open Question 2 | Se faltarem colunas, planner precisa adicionar em Phase 2 (DDL ALTER + Python). Risco: re-trabalho. | [ASSUMED — verificação humana necessária] |
| A6 | Volume de ~88 PRBs Change Team somando ~3× o tempo do validador V3.1 (~60-90s adicionais) é aceitável dentro do ciclo de 6h. | Pitfall 4 | Se na prática der >5min o validador pode bater timeout do Task Scheduler. **Recomenda-se monitorar `duracao_ciclo_ms` após primeiro deploy.** | [ASSUMED] |
| A7 | A versão `psycopg2-binary` em produção já suporta `with conn` (context manager) — usada extensivamente em `notifier_db.py`. | Pattern 1 | Se versão for muito antiga, ajustar pra `try/finally` manual. Improvável dado que o motor já está em produção usando esse pattern. | [VERIFIED: notifier_db.py:73-77, 319-327] |
| A8 | O chart "PRB Change Team" no Superset pode ser criado **manualmente pelo usuário** — não está no escopo automatizado da Phase 2. CONTEXT.md confirma: "Setup do chart é manual no Superset (não automatizado por enquanto)." | D-07 + Environment Availability | Sem risco — explicitamente ação humana fora do código. | [VERIFIED: CONTEXT.md `<code_context>` §Integration Points] |

## Open Questions

1. **Qual é a versão exata do Postgres da Locaweb?**
   - What we know: PROJECT.md menciona "9.2/9.3"; DDL em `sql/motor_tables.sql` usa
     `json` (não `jsonb`) e DO blocks com check em `pg_indexes` (compat 9.2+).
   - What's unclear: se é 9.2, 9.3, ou já foi atualizado pra 9.4/9.5+. `ON CONFLICT`
     (preferido para o seed) exige 9.5+.
   - Recommendation: planner abre task "rodar `SELECT version()` no banco antes do
     deploy" como subtask de "criar seed_change_team.sql". Default safe: usar
     fallback PL/pgSQL idempotente (funciona em qualquer versão ≥ 9.2).

2. **Qual a estrutura exata do chart "PRB em Vigilância" no Superset corporativo?**
   - What we know: CONTEXT.md §Specifics menciona que o chart existe e D-06 quer
     espelhar suas colunas pós-resolução.
   - What's unclear: nome SQL exato das colunas no Superset, ordem visual, filtros
     pré-configurados, paleta de cores. Como o Superset é externo, nem o agent
     nem o código Python conseguem inspecionar.
   - Recommendation: **ação humana para Phase 2** — Emerson ou outro responsável
     manda screenshot do chart "PRB em Vigilância" + SQL exportado. Planner usa
     isso para refinar a DDL de `motor_change_team_painel` ANTES do deploy. Se
     não vier a tempo, ir com as colunas de D-06 e adicionar mais via ALTER TABLE
     em phase futura (DDL já é idempotente, dá pra adicionar coluna sem dor).

3. **Quando uma reincidência é detectada para um PRB Change Team, dispara Slack
   dedicado ou usa o canal geral?**
   - What we know: CONTEXT.md §Specific Ideas explicitamente difere essa decisão.
     Default proposto: usar o canal existente `#prb-alertas` igual ao fluxo V3.1.
   - What's unclear: se Emerson/Change Team prefere canal/mention dedicado.
   - Recommendation: **diferir** — Phase 1 não emite Slack novo. Já existe o
     Slack do V3.1 que cobre reincidências de QUALQUER PRB (Change Team inclusive,
     porque o fluxo V3.1 lê PRBs encerrados na janela 14d e Change Team são
     PRBs encerrados em geral). Em outras palavras: PRB Change Team com `data_encerrado`
     ∈ últimos 14d **já recebe Slack hoje** pelo V3.1. Apenas se o PRB foi encerrado
     há mais de 14d (fora da janela) é que entraria num "Slack novo" — adiar pra
     phase futura conforme CONTEXT.md §Specific Ideas.

4. **CRUD da lista master — vai virar ferramenta CLI agora ou Phase 2 vive só
   com SQL direto?**
   - What we know: CONTEXT.md §Specific Ideas marca como **ação aberta**. Default
     operacional proposto: SQL direto + `seed_change_team.sql` para o lote inicial.
   - What's unclear: se Emerson quer um `gerenciar_change_team.py add/remove`
     já nesta phase.
   - Recommendation: ficar com SQL direto neste Phase 1. Adicionar CLI é uma
     extensão Phase 2/3 — não bloqueia o painel funcionar.

## Environment Availability

| Dependência | Required By | Available | Version | Fallback |
|-------------|------------|-----------|---------|----------|
| Postgres `lwsa` (mesma conexão atual) | DDL + queries + persistência | ✓ (já em uso por todo o motor) | 9.2 / 9.3 (assumido — A1) | — (sem fallback; sem Postgres a feature não existe) |
| `psycopg2-binary` (já instalado) | Conexão Postgres | ✓ (motor já roda em prod com esta lib) | confirmado em uso | — |
| Conexão Postgres do Superset corporativo apontando para `lwsa.*` | Chart "PRB Change Team" (D-07) | ? (assumida A4) | — | Em caso de não estar configurada: planner abre ticket DBA antes do go-live. |
| Acesso humano para gerenciar a lista master via SQL ad-hoc | Operação contínua | ✓ (Emerson tem acesso ao Postgres) | — | — |
| Permissões: SELECT/INSERT/TRUNCATE em `lwsa.motor_change_team*` | Motor + seed | Provável (a conta atual já faz SELECT/INSERT em `lwsa.motor_*`); TRUNCATE pode exigir permissão adicional | — | Se TRUNCATE estiver bloqueada, fallback é `DELETE FROM ... WHERE true` (mesmo efeito semântico, mais lento, sem RESTART IDENTITY). Mais provável que esteja OK porque o motor é owner das tabelas `lwsa.motor_*`. |
| Task Scheduler já registrado para `Motor-PRB-Validador.bat` | Cadência 6h (D-02) | ✓ | — | — |

**Missing dependencies with no fallback:** nenhum — Phase é purely additive sobre a stack existente.

**Missing dependencies with fallback:**
- TRUNCATE bloqueada por permissão → `DELETE FROM ...` (funciona, performance um pouco pior).
- Postgres `< 9.5` no seed → fallback PL/pgSQL (já documentado em Code Examples §4).

## Validation Architecture

> Configuração GSD não tem `.planning/config.json` neste projeto (verificado).
> Trato como `nyquist_validation` enabled (default).

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `pytest` 9.0.2 (visto em `tests/__pycache__/__init__.cpython-313-pytest-9.0.2.pyc`) |
| Config file | nenhum `pytest.ini` / `pyproject.toml` formal visto — pytest descobre `tests/` por convenção; provavelmente há um `conftest.py` (visto em `tests/conftest.py`) |
| Quick run command | `pytest tests/test_change_team.py -x` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PNCT-01 | DDL idempotente das 2 tabelas novas — rodar `sql/motor_tables.sql` 2× sem erro | manual-only (SQL no banco) | (não há SQL test runner no projeto) | ❌ Wave 0 — abrir docstring no .sql explicando idempotência |
| PNCT-01 | `gerar_painel_change_team` com lista master vazia retorna `[]` sem crash | unit | `pytest tests/test_change_team.py::test_painel_lista_vazia_nao_quebra -x` | ❌ Wave 0 |
| PNCT-01 | `gerar_painel_change_team` separa abertos (sem veredicto) vs. resolvidos (com veredicto) corretamente | unit | `pytest tests/test_change_team.py::test_painel_separa_abertos_de_resolvidos -x` | ❌ Wave 0 |
| PNCT-01 | `gerar_painel_change_team` quando `fonte_chamados=None` ainda retorna rows válidas (delta zerado) | unit | `pytest tests/test_change_team.py::test_painel_sem_fonte_chamados -x` | ❌ Wave 0 |
| PNCT-01 | `gerar_painel_change_team` detecta PRBs na master mas ausentes do SNow e loga warning | unit | `pytest tests/test_change_team.py::test_painel_detecta_prbs_faltantes -x` | ❌ Wave 0 |
| PNCT-01 | `persistir_painel_change_team` faz TRUNCATE+INSERT atômico (não há estado parcial visível) | integration | (test com mock de cursor; sem rede real) `pytest tests/test_change_team.py::test_persistir_atomico -x` | ❌ Wave 0 |
| PNCT-01 | `executar_validacao` em modo `CHANGE_TEAM_HABILITADO=false` ignora o módulo e termina sem erro | integration | `pytest tests/test_validador_integration.py::test_change_team_off -x` | ❌ Wave 0 |
| PNCT-01 | `executar_validacao` em modo `USAR_MOCKS=true` + `CHANGE_TEAM_HABILITADO=true` produz rows mock sem rede | smoke | `USAR_MOCKS=true CHANGE_TEAM_HABILITADO=true python validar_entregas.py` | ❌ Wave 0 |
| PNCT-01 | Falha simulada em `gerar_painel_change_team` **NÃO** muda o resultado de `gerar_validacoes_entrega` (Defense in Depth) | unit | `pytest tests/test_change_team.py::test_falha_change_team_nao_derruba_validador -x` | ❌ Wave 0 |
| PNCT-01 | Smoke real: após 1 ciclo do validador em produção, `SELECT COUNT(*) FROM lwsa.motor_change_team_painel` retorna N ≈ tamanho da lista ativa | manual-only | Emerson roda `SELECT COUNT(*), MAX(snapshot_em) FROM lwsa.motor_change_team_painel;` após primeiro disparo agendado | ❌ — documentar no docs/ |

### Sampling Rate

- **Per task commit:** `pytest tests/test_change_team.py -x` (rápido, ~5s).
- **Per wave merge:** `pytest tests/ -v` (todos os 54+ testes + novos).
- **Phase gate:** suite completa verde + smoke `USAR_MOCKS=true python validar_entregas.py`
  produzindo `output/validacoes_entrega.json` + log do bloco Change Team sem erro.

### Wave 0 Gaps

- [ ] `tests/test_change_team.py` — cobre PNCT-01 (unit + integration).
- [ ] `tests/test_validador_integration.py` — verifica que CHANGE_TEAM_HABILITADO toggle
      funciona sem afetar V3.1 (ou estender `tests/test_validador_entrega.py`).
- [ ] `tests/builders.py` (já existe) — extensão opcional: helper `make_change_team_row(...)`.
- [ ] Sem framework install necessário — `pytest` já está em uso.

## Security Domain

> `security_enforcement` não está configurado em `.planning/config.json` (arquivo
> ausente). Tratando como **enabled** por default. Stack: Python/Postgres in-house,
> sem exposição HTTP, sem auth de usuário final.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Conexão Postgres usa `config.ini` compartilhado (já em produção). Sem novos endpoints/auth. |
| V3 Session Management | no | Sem sessão de usuário — single-run batch. |
| V4 Access Control | yes (mínimo) | A conta do motor precisa SELECT/INSERT/TRUNCATE em `lwsa.motor_change_team*`. Manter least-privilege: motor NÃO deve ter DELETE/UPDATE nas tabelas do SNow (já é assim). |
| V5 Input Validation | yes | Lista master vem de `lwsa.motor_change_team.numero`. O extractor usa `WHERE numero IN (%s, %s, ...)` com placeholders parametrizados — sem string concatenation. Padrão já usado em `extractor.py:540, 547, 568`. |
| V6 Cryptography | no | Sem criptografia nova; credencial Postgres já gerenciada por `config.ini`. |

### Known Threat Patterns for Python + Postgres stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via lista de PRBs | Tampering | **Já mitigado pelo padrão do projeto:** placeholders `%s` sempre; nunca f-string interpolando valores de usuário. Validar em code review que `listar_prbs_por_numero` segue o padrão (`tuple(numeros)` em `cur.execute(sql, params)`, NÃO `f"WHERE numero IN ({','.join(numeros)})"`). |
| Lista master adulterada via SQL direto | Tampering / Repudiation | **Aceito:** D-01 estabelece gestão manual via SQL direto. O campo `observacao` + `adicionado_em` + `removido_em` provê auditoria mínima. Para auditoria forte, ativar `pgaudit` no DBA (fora do escopo desta phase). |
| Snapshot inconsistente lido pelo Superset | Information Disclosure (parcial) | **Mitigado por D-04** — TRUNCATE+INSERT em transação única; readers MVCC do Superset veem o snapshot anterior até o COMMIT, nunca um estado parcial. |
| Negação de serviço pelo TRUNCATE travando Superset | Denial of Service (leve) | **Pitfall 1 mitigation:** `SET LOCAL lock_timeout = '30s'` na transação + try/except externo que tolera falha — degradação suave. |
| Vazamento de descricao_curta com dados sensíveis no chart Superset | Information Disclosure | **Aceito:** o chart Superset corporativo já é restrito a quem tem acesso ao Superset (mesmo modelo dos outros charts `motor_*`). Sem cliente final como audiência. |

## Sources

### Primary (HIGH confidence)

- `Motor PRB-INC/validar_entregas.py` (entry-point V3.1 atual) — leitura completa
- `Motor PRB-INC/validador_entrega.py` (`_avaliar_prb` + `gerar_validacoes_entrega`) — leitura completa
- `Motor PRB-INC/notifier_db.py` (padrão de persistência atômica) — leitura completa
- `Motor PRB-INC/extractor.py` (FonteIncidentes + FonteChamados + mocks) — leitura completa
- `Motor PRB-INC/models.py` (dataclasses do domínio) — leitura completa
- `Motor PRB-INC/config.py` (configurabilidade externa, padrões de env var) — leitura completa
- `Motor PRB-INC/sql/motor_tables.sql` (DDL idempotente Postgres 9.2/9.3) — leitura completa
- `Motor PRB-INC/db.py` (context manager `conectar()`) — leitura completa
- `Motor PRB-INC/docs/VALIDADOR_ENTREGA.md` (processo completo V3.1) — leitura completa
- `Motor PRB-INC/docs/ARQUITETURA.md` (4 níveis + 7 princípios + 12 módulos) — leitura completa
- `Motor PRB-INC/.planning/PROJECT.md` (CON-001 a CON-013 LOCKED + DEC-001 a DEC-021) — leitura completa
- `Motor PRB-INC/.planning/REQUIREMENTS.md` (PNCT-01) — leitura completa
- `Motor PRB-INC/.planning/STATE.md` — leitura completa
- `Motor PRB-INC/.planning/phases/01-painel-change-team-discovery/01-CONTEXT.md` (D-01 a D-08) — leitura completa
- `Motor PRB-INC/tests/test_validador_entrega.py` (padrão de Fake fonte) — leitura parcial (header + Fake fonte)

### Secondary (MEDIUM confidence)

- Postgres TRUNCATE em transação é seguro (rollback funciona) — documentação oficial Postgres
  conhecida + consistente com uso em `sql/motor_tables.sql` (que assume idempotência transacional).

### Tertiary (LOW confidence — `[ASSUMED]`)

- Versão exata do Postgres da Locaweb (9.2/9.3 vs 9.5+) — depende de inspeção humana
  (Open Question 1).
- Estrutura visual exata do chart "PRB em Vigilância" no Superset — externo ao agent
  (Open Question 2).
- Conexão do Superset corporativo aponta para `lwsa.*` com permissões suficientes —
  assumido por extrapolação dos charts existentes.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — toda a stack é reaproveitada de código em produção verificado.
- Architecture: HIGH — segue padrões já estabelecidos no projeto (ARQUITETURA.md §4-5).
- Pitfalls: HIGH — todos os 6 pitfalls derivam de comportamento concreto de psycopg2 + Postgres + código existente.
- Integration plan: HIGH — pontos de extensão em `validar_entregas.py` e `notifier_db.py` são claros.
- Postgres version assumption (A1): LOW — precisa verificação humana em Phase 2.
- Superset chart structure (A5): LOW — precisa ação humana em Phase 2.

**Research date:** 2026-06-05
**Valid until:** 2026-07-05 (30 dias — stack do motor é estável; única razão pra revalidar
seria upgrade do Postgres da Locaweb ou refactor grande no `validador_entrega.py`).

## RESEARCH COMPLETE
