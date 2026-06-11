---
phase: 01-painel-change-team-discovery
plan: "01"
subsystem: database
tags:
  - postgres
  - ddl
  - seed
  - change_team
dependency_graph:
  requires: []
  provides:
    - lwsa.motor_change_team
    - lwsa.motor_change_team_painel
    - sql/seed_change_team.sql
  affects:
    - sql/motor_tables.sql
tech_stack:
  added: []
  patterns:
    - "DO block idempotente para DDL (Postgres 9.2/9.3 compat)"
    - "IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team ...) para seed idempotente"
    - "Soft delete via ativo + removido_em + adicionado_em + observacao"
key_files:
  created:
    - sql/seed_change_team.sql
  modified:
    - sql/motor_tables.sql
decisions:
  - "84 PRBs únicos (não 88 como no PLAN.md original) — lista canônica deduplicada pelo orquestrador (CHANGE_TEAM_PRBS.txt)"
  - "Task 3 (checkpoint humano) desbloqueada pelo orquestrador via input pre-preparado (CHANGE_TEAM_PRBS.txt)"
  - "Seed completo gerado diretamente — sem placeholder intermediário"
metrics:
  duration: "~12 min"
  completed: "2026-06-05"
  tasks_completed: 3
  files_modified: 2
---

# Phase 01 Plan 01: DDL + Seed inicial Change Team Summary

DDL idempotente das tabelas `lwsa.motor_change_team` (master soft-deleted) e `lwsa.motor_change_team_painel` (snapshot materializado) em Postgres 9.2/9.3, mais seed inicial dos 84 PRBs únicos da força-tarefa Change Team via DO block PL/pgSQL.

## What Was Built

### Tabelas criadas

| Tabela | Tipo | Colunas | Índices |
|--------|------|---------|---------|
| `lwsa.motor_change_team` | Master soft-deleted (D-01) | 6 (id, numero, ativo, adicionado_em, removido_em, observacao) | 2 (numero, parcial WHERE ativo=true) |
| `lwsa.motor_change_team_painel` | Snapshot materializado (D-04/D-05/D-06) | 17 (id + 9 D-05 + 7 D-06 + snapshot_em) | 3 (prb_id, status_snow, parcial WHERE veredicto IS NOT NULL) |

### Índices criados

| Índice | Tabela | Tipo |
|--------|--------|------|
| `idx_motor_change_team_numero` | motor_change_team | btree (numero) |
| `idx_motor_change_team_ativos` | motor_change_team | btree parcial (numero WHERE ativo=true) |
| `idx_motor_ct_painel_prb` | motor_change_team_painel | btree (prb_id) |
| `idx_motor_ct_painel_status` | motor_change_team_painel | btree (status_snow) |
| `idx_motor_ct_painel_veredicto` | motor_change_team_painel | btree parcial (veredicto WHERE veredicto IS NOT NULL) |

### Seed

- **Arquivo:** `sql/seed_change_team.sql`
- **PRBs inseridos:** 84 únicos (lista canônica de 92 entries com 8 duplicatas removidas)
- **Duplicatas removidas:** PRB0055284, PRB0057465, PRB0064231, PRB0068344, PRB0068880, PRB0068961, PRB0070869, PRB0071758
- **Padrão:** DO block único com 84 blocos `IF NOT EXISTS ... THEN INSERT ... END IF`
- **Compat:** Postgres 9.2+ (sem `ON CONFLICT`, sem `TRUNCATE`)

## Tasks Executadas

| Task | Descrição | Commit | Status |
|------|-----------|--------|--------|
| 1 | DDL idempotente das 2 tabelas em sql/motor_tables.sql | `7d17159` | Completa |
| 2 | Estrutura do seed sql/seed_change_team.sql | `aabda39` | Completa |
| 3 | Checkpoint humano — lista dos PRBs | `aabda39` (desbloqueado) | Completa |

## Deviations from Plan

### Auto-resolved: Task 3 desbloqueada pelo orquestrador

- **Found during:** Início da execução
- **Issue:** O PLAN.md definia Task 3 como `type="checkpoint:human-action"` aguardando a lista dos 88 PRBs do Emerson. O prompt de execução do orquestrador indicou que a lista já havia sido preparada no arquivo `.planning/phases/01-painel-change-team-discovery/CHANGE_TEAM_PRBS.txt`.
- **Fix:** A Task 3 foi executada inline na Task 2 — o seed completo com 84 PRBs foi gerado diretamente, sem placeholder intermediário.
- **Número corrigido:** 88 → 84 (lista canônica deduplicada pelo orquestrador).

### Sem outras deviações — plan executado com um ajuste de número (88 → 84).

## Known Stubs

Nenhum stub. Ambas as tabelas têm DDL completa; o seed tem todos os 84 PRBs.

## Threat Flags

Nenhuma surface nova além do que está documentado no `<threat_model>` do PLAN.md:

- T-01-02 (mitigado): comentário de TRUNCATE ACCESS EXCLUSIVE adicionado no header da seção 8.
- T-01-03 (mitigado): seed usa `IF NOT EXISTS` por linha — idempotente, sem TRUNCATE.
- T-01-05 (accepted): validação de TRUNCATE com DBA documentada no cabeçalho da seção 8.

## Self-Check: PASSED

| Item | Status |
|------|--------|
| `sql/motor_tables.sql` existe | FOUND |
| `sql/seed_change_team.sql` existe | FOUND |
| `01-01-SUMMARY.md` existe | FOUND |
| DDL: 2 tabelas `motor_change_team*` | OK (count=2) |
| Seed: 84 PRBs unicos | OK (count=84) |
| Sem `ON CONFLICT` em codigo executavel | OK |
| Sem `TRUNCATE` no seed | OK |
| Commits `7d17159` e `aabda39` existem | VERIFIED |
