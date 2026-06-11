---
phase: 01-painel-change-team-discovery
plan: 04
type: execute
wave: 2
status: complete
date_completed: 2026-06-05
requirements_addressed:
  - PNCT-01
commits:
  - 8728861
  - 0f7e572
---

# Plan 01-04 SUMMARY — change_team.py + notifier_db.persistir_painel_change_team

**Executado inline pelo orquestrador** após restrição de permissão Bash bloquear
subagents. 2 commits feature + smoke tests verificando contrato.

## O que foi entregue

### Task 1 — `change_team.py` (NEW) [commit `8728861`]

Novo módulo em 201 linhas que orquestra o snapshot Change Team. **Não toca**
nenhum arquivo existente — todo o trabalho é por composição.

**API pública:**

```python
from change_team import gerar_painel_change_team
rows: List[PainelChangeTeamRow] = gerar_painel_change_team(fonte_inc, fonte_chamados)
```

**Internals (privadas):**

- `_ler_lista_change_team_ativa() -> List[str]` — lê master via
  `SELECT prb_id FROM lwsa.motor_change_team WHERE ativo = true ORDER BY prb_id`.
  Lazy import de `db.conectar`. Try/except defensivo (qualquer falha → `[]`).
- `_eh_resolvido(prb) -> bool` — heurística que combina status encerrado +
  produto + servidor (Pitfall 3 RESEARCH — PRB sem CI vira aberto pra evitar
  match espúrio).
- `_row_para_painel_aberto(prb, snapshot_em)` — mapeia para D-05.
- `_row_para_painel_resolvido(prb, fonte_inc, fonte_chamados, snapshot_em)` —
  mapeia para D-06 reaproveitando `validador_entrega._avaliar_prb` (Pattern 3
  do RESEARCH, **CON-012 LOCKED protegido**).

**Defesas implementadas:**
- **Pitfall 5 (master ↔ SNow diff):** `log.warning` lista PRBs ativos no master
  mas ausentes do SNow após a query — operador detecta drift sem o snapshot
  cair.
- **Pitfall 6 (aberto_em None):** `dias_em_aberto` fica `None` quando o PRB
  não tem data de abertura (em vez de crashar com TypeError).
- **Try/except por row:** uma row defeituosa não derruba o snapshot inteiro.

### Task 2 — `notifier_db.persistir_painel_change_team` [commit `0f7e572`]

Duas modificações em `notifier_db.py`:

1. **Imports atualizados** — `PainelChangeTeamRow` adicionado em ordem
   alfabética no bloco `from models import (...)` + `List` em typing.

2. **Nova função pública + helper privado:**

```python
def persistir_painel_change_team(rows: List[PainelChangeTeamRow]) -> int:
    """TRUNCATE + INSERT atômico do painel Change Team (D-04)."""

def _insert_painel_change_team(cur, rows: Iterable[PainelChangeTeamRow]) -> None:
    """Batch INSERT — sem RETURNING porque tabela é folha."""
```

**Padrão idiomático seguido** (mesmo de `persistir_execucao` linhas 294-341):
- Toggle `config.PERSISTIR_NO_BANCO` respeitado (retorna 0 se off)
- Lazy import `from db import conectar` dentro da função
- `with conectar() as conn: with conn.cursor() as cur:` + `conn.commit()` explícito
- Try/except retorna 0 em falha (caller propaga para `execucao.erros`)
- `TRUNCATE TABLE ... RESTART IDENTITY` sem CASCADE (tabela é folha)
- `executemany` com 17 colunas (D-05 + D-06 + snapshot_em)

### Task 3 — Smoke tests (sem modificar arquivos)

Validou contrato end-to-end:

| Smoke | Resultado |
|---|---|
| 1. Imports limpos (change_team + notifier_db + validar_entregas) | ✅ sem ciclo |
| 2. Mock com PRB inexistente loga warning Pitfall 5, retorna 0 rows | ✅ |
| 3. Mock com PRB válido (PRB0000123) compõe 1 PainelChangeTeamRow completo | ✅ produto=VPS, dias_em_aberto=3, snapshot_em=2026-06-05 21:03 UTC |
| 4. Toggle PERSISTIR_NO_BANCO=false → retorna 0 sem tocar banco | ✅ |

## Verificação automática

| Check | Resultado |
|---|---|
| `change_team` tem `gerar_painel_change_team` callable | ✅ |
| `change_team` tem `_ler_lista_change_team_ativa` callable | ✅ |
| `change_team.py` contém `from validador_entrega import _avaliar_prb` | ✅ Pattern 3 |
| `change_team.py` contém `log.warning` para Pitfall 5 | ✅ |
| `change_team.py` defende Pitfall 6 (`aberto_em else None`) | ✅ |
| `notifier_db` tem `persistir_painel_change_team` callable | ✅ |
| `notifier_db` tem `_insert_painel_change_team` callable | ✅ |
| SQL TRUNCATE não usa CASCADE | ✅ |
| Lazy import `from db import conectar` presente | ✅ |
| Toggle `PERSISTIR_NO_BANCO` testado funcionalmente | ✅ |
| `PainelChangeTeamRow` importado em ordem alfabética | ✅ |
| Funções pré-existentes intocadas (CON-012 LOCKED) | ✅ |

## Artifacts this phase produces

**Módulo novo:** `change_team.py`
- Funções públicas: `gerar_painel_change_team`
- Funções privadas: `_ler_lista_change_team_ativa`, `_eh_resolvido`, `_row_para_painel_aberto`, `_row_para_painel_resolvido`

**Funções novas em `notifier_db.py`:**
- Pública: `persistir_painel_change_team`
- Privada: `_insert_painel_change_team`

**Imports novos em `notifier_db.py`:**
- `from typing import ... List` (adicionado)
- `from models import ... PainelChangeTeamRow` (adicionado)

## Consumed by

- Plan 01-05 (validar_entregas.py): vai chamar
  ```python
  rows = change_team.gerar_painel_change_team(fonte_inc, fonte_chamados)
  notifier_db.persistir_painel_change_team(rows)
  ```
  Dentro de um terceiro bloco try/except dedicado em `executar_validacao()`.

- Plan 01-05 (tests/test_change_team.py): vai monkeypatch
  `change_team._ler_lista_change_team_ativa` para isolar de banco real.

## Threat model dispositions

- **T-04-01 (Tampering transação):** mitigated — TRUNCATE+INSERT em uma só
  transação. TRUNCATE é transacional no Postgres ≥ 8.4.
- **T-04-02 (DoS por TRUNCATE bloqueado):** mitigated — documentado em
  docstring; caller tem try/except externo (Plan 05).
- **T-04-03 (Repudiation falha silenciosa):** mitigated — `log.info` em
  sucesso, `log.exception` em falha. Sem `pass` mudo.
- **T-04-04 (PII em log):** accepted — só logs internos.
- **T-04-05 (Privilégio TRUNCATE):** mitigated — coberto no Plan 01.
- **T-04-06 (master ↔ SNow diff, Pitfall 5):** mitigated — `log.warning` com
  set difference verificado em smoke test.

## Desvios

Verificação automática `assert 'CASCADE' not in src` do plan original era
demasiado restritiva — a palavra "CASCADE" aparece na docstring explicativa
("Sem CASCADE — tabela é folha"). Refinei a verificação para olhar apenas o
SQL real (entre `cur.execute(` e o fim do statement), confirmando que o
TRUNCATE de fato **não** usa CASCADE. A docstring fica preservada como
documentação da decisão de design.
