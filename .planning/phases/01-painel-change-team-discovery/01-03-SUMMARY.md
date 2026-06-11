---
phase: 01-painel-change-team-discovery
plan: 03
type: execute
wave: 2
status: complete
date_completed: 2026-06-05
requirements_addressed:
  - PNCT-01
commits:
  - 6da6b24
  - 18e4281
  - 50aabee
---

# Plan 01-03 SUMMARY — extractor.py: listar_prbs_por_numero (ABC + Real + Mock)

**Executado inline pelo orquestrador** após dois subagentes retry baterem em
restrição de permissão Bash/Write (sessão GSD desta data). Mesmo resultado
funcional do que teriam entregue subagentes — 3 commits atômicos, código
seguindo PATTERNS.md exatamente.

## O que foi entregue

### Task 1 — `FonteIncidentes.listar_prbs_por_numero` (ABC) [commit `6da6b24`]

Novo `@abstractmethod` em `extractor.py` linhas 124-132, inserido após
`listar_prbs_novos_no_ci_periodo` (último método abstrato da ABC) e antes
da classe `FonteChamados`.

**Assinatura:**
```python
@abstractmethod
def listar_prbs_por_numero(self, numeros: Sequence[str]) -> List[PRBExistente]:
    """PRBs por número exato (sem janela temporal — D-03 Phase 1 Change Team)."""
    ...
```

Docstring documenta D-03 (sem janela), contrato silencioso sobre números
ausentes (chamador compara input vs output para detectar misses).

### Task 2 — `ServiceNowExtractor.listar_prbs_por_numero` (real) [commit `18e4281`]

Implementação real em `extractor.py` linhas 590-609, posicionada após
`listar_prbs_para_validacao` (analog primário). 22 linhas, idioma EXATO de
`listar_prbs_para_validacao`:

- **Early return** `if not numeros: return []` — evita SQL inválido `WHERE numero IN ()`
- **Placeholders parametrizados** `placeholders = ",".join(["%s"] * len(numeros))` — anti-SQL-injection (PATTERN 5)
- **Filtro de organização** `_filtro_orgs_sni()` aplicado (coerência com restante do extractor)
- **Mapper único** `self._row_para_prb(r)` reutilizado (anti-DRY)
- **`self._query(sql, params)`** — try/except + cursor handling encapsulados

**SQL (sem janela, sem filtro de status — D-03):**
```sql
SELECT numero, descricao_curta, descricao, produto, servidor,
       prioridade, status, solucao_alternativa, categoria, subcategoria,
       grupo_designado, atualizacoes, data_abertura, data_encerrado
FROM lwsa.service_now_problemas
WHERE numero IN (%s, %s, ...)
  AND organizacao IN (...)  -- filtro_org
```

### Task 3 — `ServiceNowExtractorMock.listar_prbs_por_numero` [commit `50aabee`]

Implementação mock em `extractor.py` linhas 1537-1547, posicionada após
`listar_prbs_para_validacao` mock. 11 linhas, espelhando comportamento real:

- **Early return** lista vazia
- **`set(numeros)` para lookup O(1)** (analog usa mesma técnica)
- **Concatena** `_gerador.gerar_prbs()` (ativos) + `_gerador.gerar_prbs_para_validacao()` (encerrados na janela mock) — coerente com "sem janela" do D-03
- **List comprehension** com filtro por `prb_id in alvos`

## Verificação automática

| Check | Resultado |
|---|---|
| ABC declara método e está `@abstractmethod` | ✅ |
| ServiceNowExtractor usa placeholders + `_row_para_prb` + `_filtro_orgs_sni` + sem string concat | ✅ |
| ServiceNowExtractorMock retorna `[]` para vazio/missing, encontra PRB sintético existente | ✅ |
| `grep -c "def listar_prbs_por_numero" extractor.py` | **3** (ABC + Real + Mock) |
| Nenhum método pré-existente alterado (CON-012 LOCKED respeitado) | ✅ |

## Artifacts this phase produces

- **Método ABC** `FonteIncidentes.listar_prbs_por_numero(numeros: Sequence[str]) -> List[PRBExistente]`
- **Implementação real** `ServiceNowExtractor.listar_prbs_por_numero` (placeholders parametrizados)
- **Implementação mock** `ServiceNowExtractorMock.listar_prbs_por_numero`

## Consumed by

- Plan 01-04 (próximo, mesma Wave 2): `change_team.py::gerar_painel_change_team()` vai chamar `fonte_inc.listar_prbs_por_numero(numeros_ativos)`
- Plan 01-05 (Wave 3): fake fonte em `tests/test_change_team.py` implementa este método

## Threat model dispositions

- **T-03-01 (SQL injection)** mitigated via placeholders %s parametrizados — verificação automática garante zero `','.join(numeros)` no source
- **T-03-02 (Information disclosure)** mitigated via `_filtro_orgs_sni()` aplicado (PRBs de organizações fora de `config.ORGANIZACOES_ATIVAS` não vazam)
- **T-03-03 (DoS por lista grande)** accepted — lista master é controlada (~84 entradas hoje)

## Sem desvios

Implementação seguiu PATTERNS.md linhas 236-299 EXATAMENTE — copiou idioma de
`listar_prbs_para_validacao` e seu mock análogo.
