# Phase 1: Painel Change Team — Pattern Map

**Mapped:** 2026-06-05
**Files analyzed:** 9 (3 novos + 6 modificados)
**Analogs found:** 9 / 9 (todos com analog forte no codebase)

> Esta phase é **purely additive**. Cada arquivo novo/modificado tem analog claro
> na árvore atual de `Motor PRB-INC/`. Tudo que segue é "imitar o que já existe e
> está em produção" — zero algoritmo novo.

## File Classification

| Novo/Modificado | Arquivo | Role | Data Flow | Closest Analog | Match Quality |
|-----------------|---------|------|-----------|----------------|---------------|
| NEW | `change_team.py` | service (domínio Nível 3) | request-response (snapshot) | `validador_entrega.py` | role-match (orquestra fontes + monta dataclass) |
| NEW | `sql/seed_change_team.sql` | migration (data seed) | batch one-shot | (sem precedente) | no analog — only DDL patterns para style |
| NEW | `tests/test_change_team.py` | test (unit + integration) | request-response | `tests/test_validador_entrega.py` | exact (mesma forma de Fake fonte) |
| EDIT | `validar_entregas.py` | entry-point (Nível 4 orquestração) | request-response | (próprio arquivo — adicionar 3º try/except) | self |
| EDIT | `extractor.py` | service (Nível 3 acesso a dados) | CRUD-read | `ServiceNowExtractor.listar_prbs_para_validacao` | exact (mesma forma de WHERE numero IN) |
| EDIT | `models.py` | model (dataclass de domínio) | data-shape | `models.ValidacaoEntrega` | exact (mesmo padrão @dataclass) |
| EDIT | `notifier_db.py` | service (persistência atômica) | CRUD-write (TRUNCATE+INSERT) | `notifier_db.persistir_execucao` + `_insert_validacoes_entrega` | exact |
| EDIT | `config.py` | config (env-driven flags + nomes de tabela) | static | bloco "Modo de operação" (linhas 367-389) + `TABELA_PROBLEMAS` (147) | exact |
| EDIT | `sql/motor_tables.sql` | migration (DDL) | batch one-shot | DDL de `motor_validacao_entrega` (linhas 164-200) + `motor_validacao_entrega_equipe` (340-374) | exact |

**Resumo:** 8 arquivos com analog **exact** (mesma forma, role e data flow), 1 sem analog (`seed_change_team.sql` — primeiro SQL de seed deste projeto; segue convenções gerais de SQL idempotente do `motor_tables.sql`).

---

## Pattern Assignments

### `change_team.py` (NEW — service, request-response/snapshot)

**Analog primário:** `validador_entrega.py` (estrutura geral de módulo Nível 3)
**Analog complementar:** `extractor.py::ServiceNowExtractor._query` (forma de helper que abre/fecha conexão para SQL ad-hoc)

**Imports pattern** — segue `notifier_db.py` (linhas 21-37):

```python
# Source: notifier_db.py:21-37 (estilo padrão de módulo persistência/domínio)
from __future__ import annotations

import logging
from typing import List, Optional, Sequence

import config
import time_utils
from extractor import FonteIncidentes, FonteChamados
from models import PRBExistente  # + PainelChangeTeamRow após editar models.py

log = logging.getLogger(__name__)
```

**Helper "ler lista master" pattern** — copiar idioma do `_query` de `extractor.py:480-487` MAS encapsulado como função módulo (não método):

```python
# Source: padrão extractor.py:480-487 (_query) + notifier_db.py:71-83 (purgar_execucoes_antigas)
# Lazy import de db; try/except devolve [] em falha (defense in depth).
def _ler_lista_change_team_ativa() -> List[str]:
    sql = (
        f"SELECT numero FROM {config.SCHEMA_BANCO}.{config.TABELA_CHANGE_TEAM} "
        "WHERE ativo = true ORDER BY numero"
    )
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

**Orquestrador principal** — espelha `gerar_validacoes_entrega` de `validador_entrega.py` (não relido, mas confirmado em RESEARCH.md §Pattern 3):

```python
# Estrutura conceitual — assinatura coerente com `validador_entrega.gerar_validacoes_entrega`
def gerar_painel_change_team(
    fonte_inc: FonteIncidentes,
    fonte_chamados: Optional[FonteChamados] = None,
) -> List["PainelChangeTeamRow"]:
    numeros_ativos = _ler_lista_change_team_ativa()
    if not numeros_ativos:
        log.info("Lista Change Team vazia — pulando snapshot.")
        return []
    prbs = fonte_inc.listar_prbs_por_numero(numeros_ativos)
    # Warning de diff master↔SNow (Pitfall 5 do research)
    encontrados = {p.prb_id for p in prbs}
    faltantes = set(numeros_ativos) - encontrados
    if faltantes:
        log.warning("PRBs Change Team na master mas não no SNow: %s", sorted(faltantes))
    # Separação aberto vs. resolvido (D-05 vs D-06) + montagem das rows
    ...
```

---

### `sql/seed_change_team.sql` (NEW — migration, batch one-shot)

**Analog:** sem precedente direto no projeto (nenhum INSERT inicial em `sql/motor_tables.sql`). Style guide do header é copiado de `sql/motor_tables.sql:1-20` (comentários de compatibilidade + idempotência).

**Header pattern** (copiar de `sql/motor_tables.sql:1-20`):

```sql
-- ============================================================================
-- Motor Prescritivo PRB — Seed inicial Change Team (88 PRBs)
-- ============================================================================
-- Executar UMA VEZ após sql/motor_tables.sql ter criado lwsa.motor_change_team.
-- Schema: lwsa
--
-- COMPATIBILIDADE: Postgres 9.2+
--   - ON CONFLICT só existe em 9.5+. Bloco abaixo usa fallback PL/pgSQL com
--     IF NOT EXISTS por linha, que funciona em qualquer versão >= 9.2.
--   - Confirmar versão real do Postgres antes do go-live (rodar SELECT version()).
--
-- IDEMPOTÊNCIA: arquivo pode ser executado múltiplas vezes sem inserir duplicata.
--
-- GESTÃO: para REMOVER um PRB da Change Team, NÃO delete a linha — atualize:
--   UPDATE lwsa.motor_change_team
--   SET ativo = false, removido_em = NOW(), observacao = 'motivo'
--   WHERE numero = 'PRB0000XXX';
-- ============================================================================
```

**Insert idempotente — fallback Postgres 9.2/9.3** (idioma DO block do `motor_tables.sql:37-42, 207-329`):

```sql
-- Source: padrão DO block usado em sql/motor_tables.sql linhas 37-42 e 207-329
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM lwsa.motor_change_team WHERE numero = 'PRB0050001') THEN
        INSERT INTO lwsa.motor_change_team (numero, ativo, observacao)
        VALUES ('PRB0050001', true, 'Lote inicial Change Team — 2026-06-05');
    END IF;
    -- ... repetir para os outros 87 PRBs ...
END $$;
```

**Alternativa Postgres ≥ 9.5** (se DBA confirmar versão suportar):

```sql
INSERT INTO lwsa.motor_change_team (numero, ativo, observacao) VALUES
    ('PRB0050001', true, 'Lote inicial Change Team — 2026-06-05'),
    -- ... outros 87 ...
    ('PRB0072088', true, 'Lote inicial Change Team — 2026-06-05')
ON CONFLICT (numero) DO NOTHING;
```

**Decisão do planner:** versão real do Postgres é assumption A1 (LOW confidence). Default seguro do planner = DO block (funciona em qualquer versão ≥ 9.2).

---

### `tests/test_change_team.py` (NEW — test, request-response)

**Analog:** `tests/test_validador_entrega.py` (mesma classe de fluxo: módulo de domínio com fonte abstrata; usa Fake fonte + monkeypatch).

**Builders existentes a reusar:** `tests/builders.py` (já tem `make_prb(...)` segundo o research §Code Examples §5).

**Estrutura de Fake fonte** — padrão verificado por research:

```python
# Source: padrão tests/test_validador_entrega.py (Fake fonte sem rede)
from __future__ import annotations
from datetime import datetime, timezone

import config
from models import PRBExistente
from tests.builders import make_prb
from change_team import gerar_painel_change_team


class _FakeFonteCT:
    """Fake fonte mínima — implementa só os métodos que change_team usa."""
    def __init__(self, prbs_por_numero: dict[str, PRBExistente]):
        self._prbs = prbs_por_numero
    def listar_prbs_por_numero(self, numeros):
        return [self._prbs[n] for n in numeros if n in self._prbs]


def test_painel_lista_vazia_nao_quebra(monkeypatch):
    monkeypatch.setattr("change_team._ler_lista_change_team_ativa", lambda: [])
    rows = gerar_painel_change_team(fonte_inc=None, fonte_chamados=None)
    assert rows == []
```

**Cobertura mínima** (RESEARCH.md §Phase Requirements → Test Map): 7 testes — lista vazia, separação abertos/resolvidos, fonte_chamados=None, detecção de PRBs faltantes, persistência atômica (mock cursor), toggle off, defense-in-depth (falha do CT não derruba V3.1).

---

### `validar_entregas.py` (EDIT — entry-point)

**Analog:** o próprio arquivo. Adicionar **3º bloco try/except** entre os existentes nas linhas 80-86 (V3.1) e 89-93 (JSON dashboard).

**Bloco existente referência** (`validar_entregas.py:80-86`):

```python
# Source: validar_entregas.py:80-86 (padrão a copiar)
try:
    execucao.validacoes_entrega = gerar_validacoes_entrega(
        fonte_inc, fonte_chamados
    )
except Exception as exc:
    log.exception("Falha no ValidadorEntrega: %s", exc)
    execucao.erros.append(f"validador_entrega: {exc}")
```

**Bloco novo a adicionar** (Defense in Depth — Pattern 2 do research):

```python
# A INSERIR após linha 86, antes da linha 88. Imports lazy DENTRO do if.
if config.CHANGE_TEAM_HABILITADO:
    try:
        from change_team import gerar_painel_change_team
        from notifier_db import persistir_painel_change_team
        rows = gerar_painel_change_team(fonte_inc, fonte_chamados)
        persistir_painel_change_team(rows)
    except Exception as exc:
        log.exception("Falha no Painel Change Team: %s", exc)
        execucao.erros.append(f"change_team: {exc}")
```

**Chaves desse pattern (verificadas no arquivo):**
1. `log.exception` (não `log.error`) — preserva traceback completo, igual linha 85.
2. `execucao.erros.append(f"<feature>: {exc}")` — formato exato linha 86 e 93.
3. Lazy import dentro do `if` — protege contra erro de import quebrar o ciclo todo (analog: `from db import conectar` lazy em `notifier_db.py:72, 318`).
4. Toggle `config.CHANGE_TEAM_HABILITADO` — analog: `if not config.PERSISTIR_NO_BANCO` em `notifier_db.py:302`.

---

### `extractor.py` (EDIT — service, CRUD-read)

**Analog primário (exact match):** `ServiceNowExtractor.listar_prbs_para_validacao` (linhas 553-578) — mesma forma de WHERE com IN parametrizado.

**Mudanças necessárias** — em 3 lugares:

#### 1. ABC `FonteIncidentes` — adicionar método abstrato (após linha 123, antes da classe `FonteChamados`)

**Imports pattern** (linhas 19-21): já existe `from typing import ... Sequence`.

**Padrão de docstring** (copiar idioma das docstrings em `extractor.py:46-51, 95-108, 112-122`):

```python
# Source: padrão das docstrings ABC em extractor.py:46-51, 95-108
@abstractmethod
def listar_prbs_por_numero(self, numeros: Sequence[str]) -> List[PRBExistente]:
    """PRBs por número exato (sem janela temporal — D-03 Phase 1 Change Team).

    Aceita qualquer status. Devolve um PRBExistente por número encontrado
    no SNow. Números fornecidos que não baterem no SNow são silenciosamente
    omitidos — chamador deve comparar input vs output para detectar misses.
    """
    ...
```

#### 2. `ServiceNowExtractor` — implementação real (adicionar após linha 578)

**Analog exato** (`extractor.py:553-578` — `listar_prbs_para_validacao`):

```python
# Source: extractor.py:553-578 (listar_prbs_para_validacao)
# Mesmas colunas SELECT, mesmo _filtro_orgs_sni(), mesmo _row_para_prb.
# Diferenças: WHERE numero IN (...) em vez de status; sem data_encerrado filter.
def listar_prbs_por_numero(self, numeros: Sequence[str]) -> List[PRBExistente]:
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

**Pontos críticos verificados no analog:**
- Lista de colunas idêntica à linha 543-545 e 565-567 (paridade total — `_row_para_prb` espera essas chaves em `row.get(...)` — extractor.py:461-478).
- `_filtro_orgs_sni()` retorna `("AND organizacao IN (%s,...)", tuple(orgs))` — concatenar via f-string é seguro (whitelist em `config.ORGANIZACOES_ATIVAS`).
- `tuple(numeros) + params_org` — ordem dos params casa com ordem dos placeholders.
- **NUNCA** fazer `f"WHERE numero IN ({','.join(numeros)})"` (SQL injection). Sempre via `%s` parametrizado.

#### 3. `ServiceNowExtractorMock` — implementação mock (adicionar após linha 1503)

**Analog exato** (`extractor.py:1494-1503` — mock de `listar_prbs_para_validacao`):

```python
# Source: extractor.py:1494-1503 (listar_prbs_para_validacao mock)
def listar_prbs_por_numero(self, numeros: Sequence[str]) -> List[PRBExistente]:
    """Mock: pega PRBs sintéticos cujo numero está na lista solicitada."""
    if not numeros:
        return []
    alvos = set(numeros)
    todos = self._gerador.gerar_prbs() + self._gerador.gerar_prbs_para_validacao()
    return [p for p in todos if p.prb_id in alvos]
```

---

### `models.py` (EDIT — dataclass de domínio)

**Analog exato:** `ValidacaoEntrega` (linhas 154-217) — mesma estrutura de campos opcionais com default.

**Pattern de import já presente** (linhas 8-11):

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
```

**Pattern de docstring + campos opcionais** (copiar idioma de `ValidacaoEntrega`, linhas 154-217):

```python
# Source: padrão models.py:154-217 (ValidacaoEntrega)
# Localização sugerida: após ValidacaoEntrega (depois da linha 217).
@dataclass
class PainelChangeTeamRow:
    """Uma linha do painel Change Team materializado em lwsa.motor_change_team_painel.

    Para PRBs abertos (D-05): preenche apenas as colunas até `ultima_atualizacao`
    e deixa os campos de veredicto/sinais pós-resolução como None/0.

    Para PRBs resolvidos (D-06): adiciona veredicto + sinais derivados de
    `validador_entrega._avaliar_prb` (reaproveitamento, sem duplicação).
    """
    # --- Identificação + estado atual (D-05) ----------------------------------
    prb_id: str
    descricao_curta: str
    produto: str
    servidor: str
    status_snow: str
    prioridade_atual: str
    grupo_designado: str
    dias_em_aberto: Optional[int] = None        # NULL se aberto_em ausente (Pitfall 6)
    ultima_atualizacao: Optional[datetime] = None

    # --- Acompanhamento pós-resolução (D-06) — NULL para PRBs abertos ---------
    veredicto: Optional[str] = None             # REINCIDENCIA | ENTREGA_VALIDADA | INCONCLUSIVO
    data_resolucao: Optional[datetime] = None
    dias_pos_resolucao: Optional[int] = None
    qtd_incs_pos_resolucao: int = 0
    qtd_incs_pre_resolucao: int = 0
    delta_chamados_pct: float = 0.0
    qtd_prbs_novos_pos_resolucao: int = 0

    # --- Auditoria do snapshot ------------------------------------------------
    snapshot_em: Optional[datetime] = None      # populado pelo orquestrador
```

**Por que NÃO estender `ValidacaoEntrega` com flag `change_team: bool`:**
- `ValidacaoEntrega` é persistida em `lwsa.motor_validacao_entrega` via `_insert_validacoes_entrega` (notifier_db.py:204-288) — adicionar campo aqui força ALTER TABLE.
- D-05/D-06 têm campos NÃO existentes em `ValidacaoEntrega` (ex.: `prioridade_atual`, `status_snow`, `dias_em_aberto`, `ultima_atualizacao`).
- Separação respeita **Princípio 2 — Single Responsibility** (ARQUITETURA.md §5).

---

### `notifier_db.py` (EDIT — persistência atômica)

**Analog exato (composição de 2 fontes):**
- `notifier_db.persistir_execucao` (linhas 294-341) — estrutura geral try/except + lazy `from db import conectar` + `conn.commit()`.
- Nova função usa **TRUNCATE+INSERT** em vez de INSERT puro porque é snapshot completo (D-04). Pattern do TRUNCATE: research §Pattern 1 (não há analog interno — primeira vez no projeto).

**Imports já presentes** (linhas 21-35) — `PainelChangeTeamRow` precisa ser adicionado ao import de `models`:

```python
# Source: notifier_db.py:29-35 — adicionar PainelChangeTeamRow na lista existente
from models import (
    Cluster,
    ExecucaoMotor,
    PainelChangeTeamRow,    # NOVO
    PrescricaoPRB,
    SaudeCliente,
    ValidacaoEntrega,
)
```

**Pattern do shell de função pública** — espelhar `persistir_execucao` (linhas 294-341):

```python
# Source: notifier_db.py:294-341 (persistir_execucao — toggle, lazy import, log).
# Adicionar como nova função pública DEPOIS de persistir_execucao.
def persistir_painel_change_team(rows: List[PainelChangeTeamRow]) -> int:
    """TRUNCATE + INSERT atômico do painel Change Team.

    Padrão D-04 (snapshot completo). Mesmo idioma de `persistir_execucao`:
    `with conectar() as conn` + cursor manual + `conn.commit()` ao final.
    Sem TRUNCATE ... CASCADE — não há FK apontando pra essa tabela (é folha).
    """
    if not config.PERSISTIR_NO_BANCO:
        log.info("Persistência Postgres desabilitada — pulando painel Change Team.")
        return 0
    try:
        from db import conectar
        with conectar() as conn:
            with conn.cursor() as cur:
                # 1) Limpa snapshot anterior. RESTART IDENTITY zera o serial PK.
                cur.execute(
                    f"TRUNCATE TABLE {config.SCHEMA_BANCO}.{config.TABELA_CHANGE_TEAM_PAINEL} "
                    "RESTART IDENTITY"
                )
                # 2) Insere snapshot novo em batch via executemany.
                if rows:
                    _insert_painel_change_team(cur, rows)
                conn.commit()
        log.info("Painel Change Team gravado: %d rows.", len(rows))
        return len(rows)
    except Exception as exc:
        log.exception("Falha ao persistir painel Change Team: %s", exc)
        return 0
```

**Pattern do `_insert_<table>` privado** — espelhar `_insert_clusters` (linhas 120-151) ou `_insert_saude_clientes` (180-201):

```python
# Source: notifier_db.py:180-201 (_insert_saude_clientes — executemany simples sem RETURNING)
def _insert_painel_change_team(
    cur, rows: Iterable[PainelChangeTeamRow]
) -> None:
    """Batch INSERT — sem RETURNING porque tabela é folha (sem FK para filhos)."""
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
        (
            r.prb_id, r.descricao_curta, r.produto, r.servidor,
            r.status_snow, r.prioridade_atual, r.dias_em_aberto,
            r.grupo_designado, r.ultima_atualizacao,
            r.veredicto, r.data_resolucao, r.dias_pos_resolucao,
            r.qtd_incs_pos_resolucao, r.qtd_incs_pre_resolucao,
            r.delta_chamados_pct, r.qtd_prbs_novos_pos_resolucao,
            r.snapshot_em,
        )
        for r in rows
    ])
```

**Diferenças intencionais frente ao `persistir_execucao`:**
- **Sem `purgar_execucoes_antigas`** — snapshot é always-fresh; sem TTL relevante.
- **Sem `_jsonb(...)` em colunas** — não há campo JSON no schema do painel.
- **Sem loop com `RETURNING id`** — sem tabela filha (≠ `_insert_validacoes_entrega` linhas 242-288).

---

### `config.py` (EDIT — flags + nomes de tabela)

**Analog primário:** bloco "Modo de operação" (linhas 367-389) — toggles via env var com default literal.
**Analog secundário:** linhas 145-147 (`SCHEMA_BANCO`, `TABELA_INCIDENTES`, `TABELA_PROBLEMAS`) — nomes de tabela como constantes string.

**Localização sugerida das adições:** após linha 179 (`STATUS_PRB_ENCERRADOS`), antes da seção "Thresholds do ValidadorEntrega".

**Padrão de constante de tabela** — copiar idioma das linhas 145-147:

```python
# Source: config.py:145-147 (TABELA_INCIDENTES / TABELA_PROBLEMAS)
# Tabelas do motor Change Team (Phase 1 do painel — 2026-06-05).
TABELA_CHANGE_TEAM = "motor_change_team"               # master list soft-deleted
TABELA_CHANGE_TEAM_PAINEL = "motor_change_team_painel"  # snapshot materializado
```

**Padrão de toggle env-var** — copiar idioma das linhas 367-372:

```python
# Source: config.py:367-372 (USAR_MOCKS, PERSISTIR_NO_BANCO)
# Habilita/desabilita o snapshot do painel Change Team dentro do ciclo do
# ValidadorEntrega. Default = true (feature ligada em produção). Para desligar
# temporariamente (ex.: investigação de issue): $env:CHANGE_TEAM_HABILITADO = "false".
CHANGE_TEAM_HABILITADO: bool = (
    os.environ.get("CHANGE_TEAM_HABILITADO", "true").lower() == "true"
)
```

**Chaves do pattern verificadas:**
1. Variável nomeada em UPPER_SNAKE_CASE.
2. Anotação de tipo explícita (`: bool`).
3. Default no segundo argumento de `os.environ.get(...)` — string `"true"`/`"false"` (não booleano nativo — env vars sempre string).
4. Comparação `.lower() == "true"` (case-insensitive) — idioma exato das linhas 338, 367, 372, 383.
5. Comentário inline explicando como desligar via `$env:` (PowerShell).

---

### `sql/motor_tables.sql` (EDIT — DDL)

**Analog primário:** DDL de `motor_validacao_entrega` (linhas 167-200) — exato modelo de 21 colunas + 3 índices em DO block.
**Analog secundário:** DDL de `motor_validacao_entrega_equipe` (linhas 350-373) — tabela folha sem FK pra ela.

**Localização sugerida:** após a seção 6 (`motor_validacao_entrega_equipe`, fim em linha 373), antes do bloco de verificação (linha 396). Adicionar como seções **7** e **8**.

**Pattern de cabeçalho de tabela** — copiar de `motor_tables.sql:163-167`:

```sql
-- ----------------------------------------------------------------------------
-- 7. motor_change_team — lista master soft-deleted (D-01, Phase 1)
-- ----------------------------------------------------------------------------
-- Catálogo dos PRBs da force-task interdisciplinar "Change Team" (~88 entradas
-- no momento). Soft delete via `ativo` + `removido_em` preserva auditoria
-- ("esse PRB foi da Change Team em algum momento?"). Gestão manual via SQL
-- direto até decisão futura sobre CRUD CLI.
CREATE TABLE IF NOT EXISTS lwsa.motor_change_team (
    id              serial PRIMARY KEY,
    numero          varchar(20) NOT NULL UNIQUE,
    ativo           boolean NOT NULL DEFAULT true,
    adicionado_em   timestamp with time zone NOT NULL DEFAULT NOW(),
    removido_em     timestamp with time zone,
    observacao      text
);
```

**Pattern de DO block para índices** — copiar exatamente o idioma de `motor_tables.sql:37-42`:

```sql
-- Source: sql/motor_tables.sql:37-42 (estilo idêntico de DO block para indexes)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='lwsa' AND indexname='idx_motor_change_team_numero') THEN
        CREATE INDEX idx_motor_change_team_numero ON lwsa.motor_change_team(numero);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='lwsa' AND indexname='idx_motor_change_team_ativos') THEN
        CREATE INDEX idx_motor_change_team_ativos ON lwsa.motor_change_team(numero) WHERE ativo = true;
    END IF;
END $$;
```

**Pattern de COMMENT ON** — copiar de `motor_tables.sql:44-47, 87-91, 195-199`:

```sql
COMMENT ON TABLE  lwsa.motor_change_team IS 'Lista master da force-task Change Team — PRBs sob acompanhamento dedicado. Soft delete via ativo/removido_em.';
COMMENT ON COLUMN lwsa.motor_change_team.numero IS 'Identificador do PRB no ServiceNow (ex.: "PRB0072001"). UNIQUE — uma linha por PRB.';
COMMENT ON COLUMN lwsa.motor_change_team.ativo IS 'true = aparece no painel; false = histórico (mantém auditoria).';
COMMENT ON COLUMN lwsa.motor_change_team.observacao IS 'Texto livre — motivo da entrada/saída, link interno, etc.';
```

**Pattern de tabela materializada (motor_change_team_painel)** — copia estrutura exata de `motor_validacao_entrega` (motor_tables.sql:167-200) com colunas D-05/D-06:

```sql
-- ----------------------------------------------------------------------------
-- 8. motor_change_team_painel — snapshot materializado (D-04 / D-05 / D-06)
-- ----------------------------------------------------------------------------
-- Reescrita inteira a cada execução do ValidadorEntrega (6h) via TRUNCATE+INSERT
-- atômico em notifier_db.persistir_painel_change_team. Sem FK para motor_execucao
-- porque snapshot é independente do ciclo (sem versionamento — só estado atual
-- interessa). Consumido pelo chart "PRB Change Team" no Superset corporativo (D-07).
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
    -- Só preenchidos quando PRB está resolvido (D-06):
    veredicto                       varchar(30),
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

**Tipos a copiar exatamente** (verificados em `motor_validacao_entrega` linhas 167-180):
- `prb_id varchar(20)` — não `varchar(50)`. O analog usou 50, mas dado que PRB tem formato `PRB0000000` (10 chars), 20 é mais que suficiente. O analog `service_now_problems` referenciado em `extractor.py` usa `numero` sem tamanho fixo conhecido — usar 20 é seguro e mais ajustado.
- `descricao_curta varchar(500)` — idêntico ao `motor_validacao_entrega.descricao_curta` (171).
- `produto varchar(255)`, `servidor varchar(255)` — idêntico (172-173).
- `veredicto varchar(30)` — idêntico (178). Os valores possíveis são todos < 30 chars.
- `delta_chamados_pct numeric(8,3)` — idêntico ao ALTER em `motor_validacao_entrega` linha 278.
- `snapshot_em timestamp with time zone NOT NULL DEFAULT NOW()` — sem analog direto; segue o idioma de `timestamp_utc` em `motor_execucao` (motor_tables.sql:27) + idioma de `DEFAULT NOW()` em `adicionado_em` da tabela master.

**Por que NÃO usar TTL/CASCADE:**
- Tabela é **folha** (sem outras tabelas com FK apontando pra ela) — confirmado: research Pitfall 1 e §Pattern 1.
- Snapshot é always-fresh — `TRUNCATE` zera tudo a cada ciclo; TTL é desnecessário.

---

## Shared Patterns

Padrões transversais aplicáveis a múltiplos arquivos da phase:

### Defense in Depth (try/except aninhado por feature)
**Source:** `validar_entregas.py:80-93` (3 blocos try/except independentes) + `notifier_db.py:316-340` (try/except em `persistir_execucao`).
**Apply to:** `validar_entregas.py` (3º bloco), `change_team.py` (try/except em `_ler_lista_change_team_ativa`), `notifier_db.py::persistir_painel_change_team`.

```python
# Pattern de log + erro append + execução continua
try:
    <operação>
except Exception as exc:
    log.exception("Falha em <feature>: %s", exc)
    execucao.erros.append(f"<feature>: {exc}")
    # ciclo continua — feature opcional não derruba pipeline
```

### Lazy import de `db.conectar`
**Source:** `notifier_db.py:72, 318` — `from db import conectar` **dentro** da função, não no topo.
**Apply to:** `change_team.py::_ler_lista_change_team_ativa`, `notifier_db.py::persistir_painel_change_team`.
**Por que:** evita que erro de configuração do `config.ini` (lido por `db.py`) quebre o import do módulo todo. Falha controlada via try/except no caller.

### Toggle env-var com default seguro
**Source:** `config.py:367-372, 338, 383`.
**Apply to:** `config.py::CHANGE_TEAM_HABILITADO` (NOVO).
**Idioma exato:**
```python
NOME_FLAG: bool = os.environ.get("NOME_FLAG", "true").lower() == "true"
```

### Placeholders parametrizados em `IN (%s, %s, ...)`
**Source:** `extractor.py:540, 547, 562, 569` (linhas existentes de `listar_prbs_abertos` e `listar_prbs_para_validacao`).
**Apply to:** `extractor.py::listar_prbs_por_numero` (NOVO) — usar exatamente o mesmo `placeholders = ",".join(["%s"] * len(numeros))` e passar `tuple(numeros)` em params.
**ANTI-pattern proibido:** `f"WHERE numero IN ({','.join(numeros)})"` (SQL injection — research §Security V5).

### DO block idempotente para DDL (Postgres 9.2/9.3)
**Source:** `sql/motor_tables.sql:37-42, 71-85, 110-121, 207-329`.
**Apply to:** `sql/motor_tables.sql` (2 tabelas novas + 5 índices), `sql/seed_change_team.sql` (88 INSERTs idempotentes).
**Idioma exato:**
```sql
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='lwsa' AND indexname='<idx>') THEN
        CREATE INDEX <idx> ON lwsa.<table>(<cols>);
    END IF;
END $$;
```

### `COMMENT ON TABLE` + `COMMENT ON COLUMN` obrigatório
**Source:** `sql/motor_tables.sql` — TODAS as 6 tabelas existentes têm COMMENT.
**Apply to:** ambas as tabelas novas — alinhamento com o style guide implícito do projeto.

### `_filtro_orgs_sni()` em toda query de SNow
**Source:** `extractor.py:240-251` + uso em linhas 503, 521, 541, 563.
**Apply to:** `extractor.py::listar_prbs_por_numero` (NOVO).
**Por que:** consistência com `config.ORGANIZACOES_ATIVAS` — futuro multi-org não quebra.

### `_row_para_prb` como mapper único
**Source:** `extractor.py:461-478`.
**Apply to:** `extractor.py::listar_prbs_por_numero` (NOVO) — **NÃO** reimplementar parser; chamar `self._row_para_prb(r)` no list comprehension final.

---

## No Analog Found

| File | Role | Reason |
|------|------|--------|
| `sql/seed_change_team.sql` | data seed | Não há precedente de SQL de seed em `sql/` (`motor_tables.sql` é só DDL). Style guide é herdado do header de `motor_tables.sql` (compatibilidade Postgres, idempotência via DO block). |

**Notas:**
- O TRUNCATE+INSERT em `notifier_db.persistir_painel_change_team` também é **novo na codebase** — `persistir_execucao` é INSERT puro (sem TRUNCATE prévio porque tem TTL via `purgar_execucoes_antigas`). Mas o esqueleto da função (toggle + lazy import + try/except + commit + log) é copiado exatamente do `persistir_execucao` — só a operação SQL interna muda. **Marca-se como "exact role-match"**, não "no analog".

---

## Metadata

**Analog search scope:**
- `Motor PRB-INC/*.py` (14 módulos top-level)
- `Motor PRB-INC/sql/motor_tables.sql` (DDL atual)
- `Motor PRB-INC/tests/*.py` (8 arquivos — verificação de existência apenas)

**Files scanned / read in full:**
- `notifier_db.py` (341 linhas — completo)
- `validar_entregas.py` (127 linhas — completo)
- `sql/motor_tables.sql` (421 linhas — completo)
- `models.py` (242 linhas — completo)
- `config.py` (399 linhas — completo)
- `extractor.py` (1717 linhas — targeted reads: ABC 1-130, helpers 240-264, ServiceNowExtractor 424-603, mock 1475-1594, factory 1700-1717 + Grep do índice de defs)

**Pattern extraction date:** 2026-06-05
**Coverage:** 9/9 arquivos com pattern assignment concreto + 7 shared patterns transversais identificados.

---

## PATTERN MAPPING COMPLETE
