---
phase: 01-painel-change-team-discovery
plan: "02"
subsystem: dataclass
tags: [python, dataclass, config, change_team, models, toggle, env-var]

# Dependency graph
requires: []
provides:
  - "models.PainelChangeTeamRow: dataclass com 7 campos obrigatórios D-05 + 2 opcionais D-05 + 7 D-06 + auditoria"
  - "config.TABELA_CHANGE_TEAM = motor_change_team"
  - "config.TABELA_CHANGE_TEAM_PAINEL = motor_change_team_painel"
  - "config.CHANGE_TEAM_HABILITADO: bool (default True, env var override)"
affects:
  - 01-03-extractor
  - 01-04-change_team
  - 01-04-notifier_db
  - 01-05-validar_entregas

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dataclass com campos obrigatórios primeiro, opcionais com default depois (regra @dataclass Python)"
    - "Toggle env var idiomático: os.environ.get(NAME, default_str).lower() == 'true' (DEC-012)"
    - "Constantes de tabela como string literal UPPER_SNAKE_CASE em config.py"

key-files:
  created: []
  modified:
    - models.py
    - config.py

key-decisions:
  - "PainelChangeTeamRow criada como dataclass independente (NÃO estendendo ValidacaoEntrega) — respeita Single Responsibility e evita ALTER TABLE em motor_validacao_entrega (CON-012 LOCKED)"
  - "delta_chamados_pct e qtd_* como int/float com default 0 (não Optional) — espelha comportamento de _avaliar_prb que sempre retorna valor numérico"
  - "dias_em_aberto como Optional[int] — PRBs sem aberto_em geram NULL em vez de TypeError (Pitfall 6 do RESEARCH)"
  - "CHANGE_TEAM_HABILITADO default 'true' (feature ligada em produção) — safe default per T-02-01"

patterns-established:
  - "Adicionar novas features como dataclasses separadas em models.py — não alterar classes existentes"
  - "Novos toggles seguem idioma exato de USAR_MOCKS/PERSISTIR_NO_BANCO no bloco 'Modo de operação'"
  - "Novos nomes de tabela seguem idioma de TABELA_INCIDENTES/TABELA_PROBLEMAS — string literal, comentário inline"

requirements-completed:
  - PNCT-01

# Metrics
duration: 8min
completed: 2026-06-05
---

# Phase 01 Plan 02: Painel Change Team — Models e Config Summary

**Dataclass PainelChangeTeamRow (16 campos D-05/D-06 + auditoria) e constantes TABELA_CHANGE_TEAM / CHANGE_TEAM_HABILITADO adicionadas em models.py e config.py, habilitando imports downstream para Plans 03-05**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-06-05T00:00:00Z
- **Completed:** 2026-06-05T00:08:00Z
- **Tasks:** 2/2
- **Files modified:** 2

## Accomplishments

- Dataclass `PainelChangeTeamRow` com 7 campos obrigatórios D-05, 2 opcionais D-05, 7 campos D-06 e auditoria `snapshot_em` — espelho 1:1 das colunas da tabela `lwsa.motor_change_team_painel` criada em Plan 01-01
- Constantes `TABELA_CHANGE_TEAM` e `TABELA_CHANGE_TEAM_PAINEL` em config.py seguindo idioma de `TABELA_INCIDENTES`/`TABELA_PROBLEMAS`
- Toggle `CHANGE_TEAM_HABILITADO: bool` com default `True` lido via env var (idioma idêntico a `USAR_MOCKS`/`PERSISTIR_NO_BANCO`), conforme mitigação T-02-01

## Task Commits

Cada task foi comitada atomicamente:

1. **Task 1: Adicionar dataclass PainelChangeTeamRow em models.py** - `966a4d9` (feat)
2. **Task 2: Adicionar constantes de tabela + toggle env var em config.py** - `8f91cd0` (feat)

## Files Created/Modified

- `models.py` — Nova dataclass `PainelChangeTeamRow` inserida após `ValidacaoEntrega` (antes de `ExecucaoMotor`), 33 linhas adicionadas. Nenhuma classe existente alterada.
- `config.py` — 2 constantes de tabela + 1 toggle env var adicionados, 12 linhas adicionadas. Todos os toggles existentes intocados.

## Decisions Made

- **Dataclass independente, não herança:** `PainelChangeTeamRow` é uma dataclass separada. Estender `ValidacaoEntrega` forçaria `ALTER TABLE` em `motor_validacao_entrega` (CON-012 LOCKED) e violaria Single Responsibility.
- **delta_chamados_pct como float = 0.0 (não Optional):** espelha o retorno de `_avaliar_prb` que sempre retorna float; mesmo raciocínio para `qtd_*` como int = 0.
- **CHANGE_TEAM_HABILITADO default True:** feature ligada por default em produção — desligar é ação deliberada via `$env:CHANGE_TEAM_HABILITADO = "false"`.

## Deviations from Plan

None — plano executado exatamente como escrito.

## Issues Encountered

None.

## Known Stubs

None — esta plan define apenas o contrato de dados (dataclass + config). Não há dados fluindo para UI ainda.

## Threat Flags

Nenhuma nova superfície de segurança além do mapeado em T-02-01 (env var → bool toggle). Mitigação aplicada: `.lower() == "true"` case-insensitive com default seguro `"true"`.

## Next Phase Readiness

- **Plan 01-03 (extractor):** pode importar `config.TABELA_CHANGE_TEAM` para query SELECT da master list
- **Plan 01-04 (change_team.py + notifier_db.py):** pode importar `PainelChangeTeamRow` como tipo de retorno e usar `config.TABELA_CHANGE_TEAM_PAINEL` no TRUNCATE+INSERT
- **Plan 01-05 (validar_entregas.py):** pode usar `if config.CHANGE_TEAM_HABILITADO:` para o bloco try/except

---
*Phase: 01-painel-change-team-discovery*
*Completed: 2026-06-05*
