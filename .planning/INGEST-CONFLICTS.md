## Conflict Detection Report

Modo: new (net-new bootstrap, sem EXISTING_CONTEXT).
Precedence aplicada: ["ADR", "SPEC", "PRD", "DOC"] (default).
Docs sintetizados: 7 (1 SPEC + 6 DOC). Sem ADRs, sem PRDs.

---

### BLOCKERS (0)

Nenhum conflito bloqueante detectado.

- Sem ADRs LOCKED-vs-LOCKED em contradicao (nenhum ADR formal existe).
- Sem ADR de ingest contradizendo CONTEXT.md existente (modo `new`).
- Sem ciclo de referencia ADR/PRD/SPEC que impeca sintese (REGRAS.md como
  unico SPEC nao participa de ciclo de precedencia — apenas e referenciada
  por DOCs).
- Sem docs `UNKNOWN` confidence `low` (todos os 7 sao `confidence: high`).
- Sem traversal exceeding cap (graph depth ~3 entre DOCs).

---

### WARNINGS (1)

[WARNING] Requisito upcoming sem fonte documental
  Found: "Painel Change Team" foi descrito no prompt do ingest como nova
    feature alvo, capturado como `REQ-painel-change-team` (status: upcoming)
    em `.planning/intel/requirements.md`.
  Source: prompt do usuario (nao consta em nenhum arquivo classificado em
    `CLASSIFICATIONS_DIR`).
  Impact: o requirement existe sem PRD/ADR/SPEC formal. Acceptance criteria
    estao em aberto (escopo dos 88 PRBs, fronteira tecnologica do painel,
    cadencia, consumidores). Roadmapper nao tem como prescrever
    implementacao sem refinamento.
  → Resolver com 1 das opcoes antes de routing/implementacao:
    (a) Criar PRD curto em `docs/prd/painel-change-team.md` definindo
        escopo (criterio dos 88 PRBs), consumidores e acceptance.
    (b) Criar ADR em `docs/adr/000X-painel-change-team-arquitetura.md`
        decidindo: dashboard novo (Streamlit/HTML) vs. extensao do JSON
        existente; cadencia; tabela vs. config para a lista dos 88 PRBs.
    (c) Roadmapper abrir explicitamente uma "discovery thread" no
        ROADMAP.md sinalizando que o requirement esta em descoberta.

---

### INFO (3)

[INFO] Auto-resolved: REGRAS.md tratada como LOCKED SPEC por diretiva do ingest
  Note: O classificador (`docs/REGRAS.json`) marcou `locked: false` por
    ausencia de cabecalho "Status: Locked" no documento. O prompt do ingest
    explicitamente instruiu: *"Treat regras P1-P5 from REGRAS.md as locked
    SPEC"*. Aplicado override: as 17 constraints derivadas (CON-001 a CON-013
    em `.planning/intel/constraints.md`) foram registradas com `locked:
    true`. Constraints de infra/runtime (CON-014 a CON-017) ficaram
    `locked: false` por nao serem regra de negocio.
  Source: docs/REGRAS.md (SPEC, precedencia 2 default) + diretiva do prompt
    do ingest.
  Rationale: SPEC > DOC pela precedencia default. Override de LOCKED foi
    deliberado pelo PO no momento do ingest — proxima evolucao deveria
    adicionar cabecalho `Status: Locked` ao proprio REGRAS.md para que
    classificadores futuros nao precisem do override.

[INFO] Auto-resolved: decisoes implicitas extraidas de ARQUITETURA.md tratadas
  como ADR-equivalentes (com ressalvas de locking)
  Note: O projeto nao tem ADRs formais. A secao 6 da ARQUITETURA.md
    ("Decisoes importantes e por que") foi minerada para produzir 21
    entradas em `.planning/intel/decisions.md` (DEC-001 a DEC-021).
    Todas registradas como `status: Aceita (implicita)` e `locked: false`.
  Source: docs/ARQUITETURA.md secao 6, modulos do `4. Os 12 modulos abertos`,
    secao `5. 7 principios transversais`.
  Rationale: a precedencia formal `ADR > SPEC > PRD > DOC` nao se aplica aqui
    porque a fonte e DOC. Portanto, ANY futuro ADR formal pode override
    estas decisoes sem conflito. Caso queira congelar uma destas decisoes,
    promove-la a ADR formal (`docs/adr/000X-*.md` com Status: Locked).

[INFO] Cross-refs entre DOCs formam grafo nao-aciclico mas nao bloqueante
  Note: ARQUITETURA ↔ MANUAL ↔ REGRAS ↔ GLOSSARIO ↔ SAUDE_DO_CLIENTE ↔
    VALIDADOR_ENTREGA possuem links mutuos (cada doc referencia os outros
    no rodape "Referencias cruzadas"). Algoritmo de deteccao de ciclos
    detectaria, mas estes links sao **navegacionais**, nao de precedencia.
    Sem ADR/PRD na cadeia, nao ha risco de loop de sintese.
  Source: cross_refs de cada um dos 7 JSONs em
    `.planning/intel/classifications/`.
  Rationale: regra de cycle-detection do `doc-conflict-engine` visa cadeias
    de decisao (ADR cita ADR cita ADR). Cross-refs DOC↔DOC sao seguros
    para sintese. Nenhum bucket de unresolved-blockers necessario.
