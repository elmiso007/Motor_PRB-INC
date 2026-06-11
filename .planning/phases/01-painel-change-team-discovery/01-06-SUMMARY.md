---
phase: 01-painel-change-team-discovery
plan: 06
type: execute
wave: 3
status: complete
date_completed: 2026-06-05
requirements_addressed:
  - PNCT-01
commits:
  - a9242cc
  - 2c4091d
---

# Plan 01-06 SUMMARY — docs/DASHBOARD_CHANGE_TEAM.md operational guide

**Executado inline pelo orquestrador** após restrição de permissão Bash bloquear
subagents. Wave 3 Plan 06/06 — encerra Phase 1.

## O que foi entregue

### Task 1 — `docs/DASHBOARD_CHANGE_TEAM.md` (NEW) [commit `2c4091d`]

Documento operacional em **324 linhas, 8 seções**, escrito para 3 audiências:
- Force-task Change Team (consumidores do chart)
- Operador do Motor PRB-INC (mantém a lista + troubleshoot)
- DBA/PO (governança do schema lwsa.*)

| § | Seção | Conteúdo |
|---|---|---|
| 1 | Visão Geral | Resumo + tabela com D-01..D-08 |
| 2 | Arquitetura | Diagrama ASCII do pipeline Task Scheduler → ValidadorEntrega → Change Team → Superset |
| 3 | Como Construir o Chart no Superset | 8 passos manuais (D-07 LOCKED — sem automação) |
| 4 | SQL Canônico | Query A (listagem), B (split aberto/resolvido), C (big number "X de Y"), D (health check) |
| 5 | Gestão da Lista Master | INSERT / soft delete / reativar / listar histórico / corrigir engano |
| 6 | Troubleshooting | 6 cenários cobrindo todos os Pitfalls do RESEARCH |
| 7 | Ações Abertas (Phase 2+) | 7 follow-ups priorizáveis |
| Refs | Referências | Links para sql/, change_team.py, .planning/01-CONTEXT, etc. |

**Características críticas:**
- AVISO destacado: **"NUNCA use `DELETE FROM lwsa.motor_change_team`"** — soft delete obrigatório
- Nomes de coluna **verificados contra a DDL real** (master usa `numero`, painel usa `prb_id` — diferença documentada)
- Linkagem com `.md` files relativos (renderiza no GitHub web e VS Code preview)
- Português PT-BR na narrativa; SQL/identifiers em inglês

### Bug colateral encontrado e corrigido [commit `a9242cc`]

Durante a escrita da §3 "Construção Superset", descobri que **`change_team.py`
estava usando coluna errada** no SELECT da master:

```python
# ANTES (errado):
sql = f"SELECT prb_id FROM lwsa.motor_change_team WHERE ativo = true ORDER BY prb_id"

# DEPOIS (correto — alinha com a DDL e o seed):
sql = f"SELECT numero FROM lwsa.motor_change_team WHERE ativo = true ORDER BY numero"
```

**Impacto sem o fix:** em produção (banco real), `_ler_lista_change_team_ativa`
crasharia com `ERROR: column "prb_id" does not exist` → log.warning → snapshot
sempre vazio. O sistema seguiria funcionando (Defense in Depth funcionou), mas
o painel jamais teria dados.

Verificação pós-fix:
- ✅ Suite global: 116 passed (zero regressão)
- ✅ Smoke test (mock): `python validar_entregas.py` exit 0
- ✅ DDL e seed (Plan 01-01) já usavam `numero` corretamente — só o Python tava errado

### Task 2 — Checkpoint humano (aguardando Emerson)

Decisões pendentes do checkpoint:
1. **Leitura do documento** — Emerson valida que o guia faz sentido renderizado
2. **Comparação com "PRB em Vigilância"** — Emerson compara colunas existentes
   no chart de referência e registra eventuais gaps
3. **Naming** — Emerson confirma que "PRB Change Team" é o nome final

## Verificação automática

| Check | Resultado |
|---|---|
| `docs/DASHBOARD_CHANGE_TEAM.md` existe | ✅ |
| Doc com ≥ 80 linhas | ✅ (324) |
| `lwsa.motor_change_team` referenciado ≥ 4 vezes | ✅ (18) |
| `UPDATE lwsa.motor_change_team` com `ativo = false` | ✅ (§5) |
| Aviso "NUNCA delete" | ✅ (§5) |
| `D-01`..`D-08` referenciados | ✅ (§1) |
| Seção "Troubleshooting" | ✅ (§6) |
| ≥ 6 seções (`## `) | ✅ (8) |
| docs/ARQUITETURA.md, MANUAL.md, REGRAS.md, VALIDADOR_ENTREGA.md, SAUDE_DO_CLIENTE.md intocados | ✅ |

## Artifacts this phase produces

**Novo arquivo:**
- `docs/DASHBOARD_CHANGE_TEAM.md` (324 linhas) — guia operacional

**Bug fix colateral em `change_team.py`:**
- `_ler_lista_change_team_ativa` agora usa `SELECT numero` (era `SELECT prb_id`)

## Threat model dispositions

- **T-06-01 (DELETE direto na master):** mitigated — §5 destaca o aviso e
  só mostra UPDATE com soft delete; também mostra exceção controlada
  (DELETE só dentro de 1h e só se ativo=true, para corrigir engano recente).
- **T-06-02 (PII em SQL exemplo):** accepted — esquema `lwsa.motor_*` já é
  conhecido em todo o repositório.

## Sem desvios

Documento seguiu a estrutura proposta no plan, com 1 melhoria: adicionei
Query C (big number agregado "X de Y resolvidos") e Query D (health check
da idade do snapshot), úteis para painéis derivados no Superset além da
Table base.

## Checkpoint humano — pendente da aprovação do Emerson

Phase 1 fica completa após Emerson aprovar:
1. ✅ Smoke tests do Plan 01-05 (esse SUMMARY confirma os resultados)
2. ⏳ Leitura visual do `docs/DASHBOARD_CHANGE_TEAM.md` (Plan 01-06 Task 2)
3. ⏳ Comparação com chart "PRB em Vigilância" existente (opcional — pode
    ficar como Phase 2 follow-up se o chart de referência não estiver
    acessível agora)

Após aprovação, encerro a Phase 1 e marco PNCT-01 como complete em
REQUIREMENTS.md + STATE.md.
