# Synthesis Summary — Motor PRB-INC GSD bootstrap

> Entry point para `gsd-roadmapper`. Resume o que foi sintetizado a partir de
> 7 documentos classificados, derivados via `gsd-doc-classifier` em
> `.planning/intel/classifications/`. Modo: `new`. Sem EXISTING_CONTEXT.

---

## Doc counts by type

- **ADR:** 0 (nenhum ADR formal existe — decisoes mineradas implicitamente).
- **SPEC:** 1 (docs/REGRAS.md — tratado como LOCKED por diretiva do ingest).
- **PRD:** 0.
- **DOC:** 6 (APRESENTACAO, GLOSSARIO, ARQUITETURA, MANUAL, SAUDE_DO_CLIENTE,
  VALIDADOR_ENTREGA).
- **UNKNOWN low-confidence:** 0.

Todos os 7 com `confidence: high`. Nenhum `manifest_override` aplicado.

---

## Decisions extracted

- **Total:** 21 entradas em `.planning/intel/decisions.md` (DEC-001 ... DEC-021).
- **LOCKED:** 0 (nenhuma decisao explicitamente locked — vinda de DOC, nao ADR).
- **Origem:** ARQUITETURA.md secao 6 ("Decisoes importantes") + secao 5
  (principios) + descricao de modulos.
- **Coverage:** algoritmos (TF-IDF/DBSCAN), persistencia, cadencia,
  orquestracao, integracoes (Slack, Postgres, DW), principios transversais.

---

## Requirements extracted

- **Total:** 19 entradas em `.planning/intel/requirements.md`.
- **Existing (em producao):** 18 (REQ-extracao-snow-incidentes, ...,
  REQ-modo-mock) — comportamento ja implementado, acceptance = "as-built".
- **Upcoming (novo):** 1 (REQ-painel-change-team) — acceptance em aberto,
  precisa de PRD/ADR antes de routing.

---

## Constraints extracted

- **Total:** 17 entradas em `.planning/intel/constraints.md`.
- **Business-rules (LOCKED):** 13 (CON-001 a CON-013 — matriz P1-P5, gatilho
  proativo, repriorizacao, Saude do Cliente, ValidadorEntrega, clusterizacao,
  filtros, termos heuristicos).
- **Infra/runtime (nao-locked):** 4 (CON-014 permissoes, CON-015 Postgres
  json vs jsonb, CON-016 runtime Python/deps, CON-017 cadencia jobs).
- **Origem:** docs/REGRAS.md (SPEC).

---

## Context notes captured

- **Topicos:** 15 (visao executiva, arquitetura, fluxo de dados, principios,
  limitacoes, pontos de extensao, setup, dashboard/Slack, queries, login
  canonico, evolucao ValidadorEntrega, glossario, projetos relacionados,
  resultados, painel Change Team).
- **Localizacao:** `.planning/intel/context.md`.

---

## Conflicts summary

- **BLOCKERS:** 0.
- **WARNINGS:** 1 — REQ-painel-change-team sem fonte documental (precisa de
  PRD/ADR antes de routing).
- **INFO:** 3 — REGRAS.md tratada como LOCKED por diretiva; decisoes
  implicitas de ARQUITETURA tratadas como ADR-equivalentes (nao-locked);
  cross-refs DOC↔DOC sao navegacionais, nao bloqueantes.
- **Detail:** `.planning/INGEST-CONFLICTS.md`.

---

## Per-type intel files (downstream entry points)

| Arquivo | Conteudo |
|---|---|
| `.planning/intel/decisions.md` | 21 decisoes (mineradas de ARQUITETURA.md) |
| `.planning/intel/requirements.md` | 19 requisitos (18 existing + 1 upcoming) |
| `.planning/intel/constraints.md` | 17 constraints (13 LOCKED business-rules + 4 infra) |
| `.planning/intel/context.md` | 15 topicos contextuais de fundo |
| `.planning/INGEST-CONFLICTS.md` | Relatorio de conflitos (0 BLOCKER, 1 WARN, 3 INFO) |

---

## Pointers for `gsd-roadmapper`

1. **Start with REQ-painel-change-team** — unica feature `upcoming`. Resolver
   o WARNING antes de prescrever implementacao (precisa de PRD ou ADR para
   definir escopo dos 88 PRBs + fronteira tecnologica + cadencia).
2. **Tratar 18 requirements `existing` como linha de base** — sao
   comportamento ja em producao. Roadmap deve capturar isso como STATE atual
   (Done) ao montar ROADMAP.md.
3. **Constraints LOCKED nao podem ser violadas** — qualquer evolucao futura
   da matriz P1-P5 exige passar por revisao do PO (Jessica/Victor/Bruno) e
   atualizacao da SPEC.
4. **Sugestao de formalizacao futura:**
   - Adicionar cabecalho `Status: Locked` em REGRAS.md para que o
     classificador detecte sem precisar do override.
   - Promover decisoes-chave (TF-IDF, Postgres json, cadencia 15min,
     stateless) a ADRs formais em `docs/adr/` caso pretenda blindar contra
     mudancas futuras.
5. **Roadmap context:** projeto em producao na Locaweb (lwsa.motor_*), motor
   preventivo (15min) + validador retrospectivo (6h) + Saude do Cliente.
   Stack: Python 3.10+, Postgres, scikit-learn, Slack SDK.
