# ValidadorEntrega — Processo Completo (V3.1)

> **Audiência:** Change Team, PO, coordenadores, analistas que vão consumir
> os veredictos. Para detalhe de implementação ver [ARQUITETURA.md](ARQUITETURA.md).
> Para regras de thresholds ver [REGRAS.md](REGRAS.md). Para termos
> técnicos ver [../GLOSSARIO.md](../GLOSSARIO.md).

Este documento descreve **ponta a ponta** como o motor avalia retrospectivamente
PRBs entregues pelo Change Team — fechando o loop de qualidade do fix.

---

## Sumário

1. [O que é](#1-o-que-é)
2. [Por que existe (preventivo vs retrospectivo)](#2-por-que-existe-preventivo-vs-retrospectivo)
3. [Fluxo do processo](#3-fluxo-do-processo)
4. [Quais PRBs entram](#4-quais-prbs-entram)
5. [Os 5 sinais coletados por PRB](#5-os-5-sinais-coletados-por-prb)
6. [Veredicto (REINCIDENCIA / ENTREGA_VALIDADA / INCONCLUSIVO)](#6-veredicto-reincidencia--entrega_validada--inconclusivo)
7. [Volumetria pré-resolução](#7-volumetria-pré-resolução)
8. [Δ chamados vinculados (V3)](#8-δ-chamados-vinculados-v3)
9. [PRBs novos pós-resolução](#9-prbs-novos-pós-resolução)
10. [Times impactados (V3.1)](#10-times-impactados-v31)
11. [O que aparece no dashboard / banco / Slack](#11-o-que-aparece-no-dashboard--banco--slack)
12. [Como interpretar (operacional)](#12-como-interpretar-operacional)
13. [Cadência e agendamento](#13-cadência-e-agendamento)
14. [Como ajustar](#14-como-ajustar)
15. [Histórico de versões (V1 → V2 → V3 → V3.1)](#15-histórico-de-versões-v1--v2--v3--v31)
16. [Limitações conhecidas](#16-limitações-conhecidas)

---

## 1. O que é

Módulo automático que, a cada **6 horas** (entry-point separado do motor
preventivo), lista os PRBs **encerrados pelo Change Team nos últimos 14
dias** e emite um **veredicto** sobre cada um:

- `REINCIDENCIA` — o problema voltou (≥3 INCs novas no mesmo CI)
- `ENTREGA_VALIDADA` — o fix segurou (0 INCs novas + ≥7 dias decorridos)
- `INCONCLUSIVO` — ainda cedo pra decidir (janela curta, sinais ambíguos)

Além do veredicto, cada PRB carrega **4 sinais adicionais** (V3.1):
volumetria pré-resolução, Δ de chamados vinculados pré/pós, lista de
PRBs novos abertos no mesmo CI, e **times internos Locaweb impactados**
(top N equipes proprietárias dos chamados vinculados + % de redução pós-fix).

**Implementação:**
- Módulo: [validador_entrega.py](../validador_entrega.py)
- Entry-point: [validar_entregas.py](../validar_entregas.py)
- Wrapper Windows: [Motor-PRB-Validador.bat](../Motor-PRB-Validador.bat)
- Persistência: tabela `lwsa.motor_validacao_entrega` (24 colunas)

---

## 2. Por que existe (preventivo vs retrospectivo)

O motor opera em **2 prismas independentes**:

| Prisma | Quando olha | Pergunta que responde |
|---|---|---|
| **Preventivo** (`main.py` + `rules_engine.py`) | INCs ativas das últimas 24h | "**Quais PRBs eu deveria abrir AGORA?**" |
| **Retrospectivo** (`validar_entregas.py` + `validador_entrega.py`) | PRBs já entregues nos últimos 14d | "**Os PRBs que o CT entregou realmente resolveram?**" |

**Por que separar:** se o CT fecha um PRB hoje, é cedo demais pra saber se
o fix segurou. Olhar uma vez ao dia (na verdade, a cada 6h) basta. Já o
preventivo precisa rodar com cadência menor (1h em PROD desde 2026-06-09)
pra capturar escaladas em janela ainda útil.

**Requisito original:** a Diretoria/PO queria saber "**dos PRBs que abrimos,
quantos realmente resolveram o problema?**" Essa pergunta é o coração do
ValidadorEntrega.

> **Nota (2026-06-09):** o entry-point `validar_entregas.py` também executa
> o **Painel Change Team** (Phase 1 GSD) em um 3º bloco try/except — Defense
> in Depth. Falha do Change Team **não afeta** este V3.1 (CON-012 LOCKED).
> Detalhes em [DASHBOARD_CHANGE_TEAM.md](DASHBOARD_CHANGE_TEAM.md) e
> [REGRAS.md §15](REGRAS.md#15-painel-change-team--força-tarefa).

---

## 3. Fluxo do processo

```
┌─────────────────────────────────────────────────────────────────────┐
│  FASE 1 — Listar PRBs candidatos                                     │
└─────────────────────────────────────────────────────────────────────┘

  fonte_inc.listar_prbs_para_validacao(dias=14)
        ↓
  SELECT ... FROM lwsa.service_now_problems
  WHERE status IN ('Encerrado Automaticamente', 'Concluído')
    AND data_encerrado IS NOT NULL
    AND data_encerrado >= NOW() - INTERVAL '14 days'
    AND organizacao IN ('Locaweb')
        ↓
  ~10 PRBs candidatos

┌─────────────────────────────────────────────────────────────────────┐
│  FASE 2 — Avaliar cada PRB (5 sinais)                                │
└─────────────────────────────────────────────────────────────────────┘

  para cada PRB:
    ├─ SINAL 1: Veredicto
    │     INCs no (produto, servidor) com data_abertura >= data_encerrado
    │     _classificar(qtd_pos, dias_pos) → REINCIDENCIA/VALIDADA/INCONCLUSIVO
    │
    ├─ SINAL 2: Volumetria pré-resolução (60 dias antes)
    │     contar_incidentes_no_ci_periodo
    │     → {qtd, clientes_unicos, categorias}
    │
    ├─ SINAL 3: Δ chamados VINCULADOS (V3)
    │     listar_incidentes_por_produto_servidor(janela_pre)  → incs_pre
    │     listar_incidentes_por_produto_servidor(janela_pos)  → incs_pos
    │     contar_chamados_vinculados(prb_id, incs_pre, ...)   → chamados_pre
    │     contar_chamados_vinculados(prb_id, incs_pos, ...)   → chamados_pos
    │     delta_chamados_pct = (pos - pre) / pre
    │
    ├─ SINAL 4: PRBs novos pós-resolução
    │     listar_prbs_novos_no_ci_periodo(produto, servidor,
    │                                      desde=data_resolucao,
    │                                      ignorar_prb_id=prb.prb_id)
    │     → ["PRB0012345", ...]
    │
    └─ SINAL 5: Times impactados (V3.1)
          agrupar_chamados_vinculados_por_equipe(prb_id, incs_pre, janela_pre)
                → ranking_pre (top N por chamados)
          agrupar_chamados_vinculados_por_equipe(prb_id, incs_pos, janela_pos)
                → ranking_pos
          Para cada equipe do TOP_EQUIPES_IMPACTADAS do pré:
                pct = (qtd_pos - qtd_pre) / qtd_pre
          → {equipe: qtd_pre}, {equipe: qtd_pos}, {equipe: pct}

┌─────────────────────────────────────────────────────────────────────┐
│  FASE 3 — Saída (3 destinos, defesa em camadas)                      │
└─────────────────────────────────────────────────────────────────────┘

  ┌── output/validacoes_entrega.json (JSON do dashboard)
  ├── lwsa.motor_validacao_entrega   (24 colunas persistidas)
  └── Slack                           (1 mensagem POR REINCIDENCIA detectada)
```

**Tempo medido:** ~20-30s para 10 PRBs (com índices no DW).

---

## 4. Quais PRBs entram

Os PRBs candidatos atendem **4 critérios cumulativos**:

| Critério | Configuração | Por quê |
|---|---|---|
| Status encerrado | `STATUS_PRB_ENCERRADOS = ("Encerrado Automaticamente", "Concluído")` | Outros status como "Aguardando Validação" têm `data_encerrado` NULL no DW |
| `data_encerrado` não nula | implícito | Sem data confiável não dá pra calcular janela |
| Janela de 14 dias | `JANELA_VALIDACAO_ENTREGA_DIAS = 14` | PRB de mais de 14d já foi avaliado em ciclos anteriores |
| Organização ativa | `ORGANIZACOES_ATIVAS = ("Locaweb",)` | Foco atual; KingHost desligado |

PRBs **sem `produto` ou sem `servidor`** entram, mas viram `INCONCLUSIVO`
direto (sem `CI` confiável não dá pra match).

---

## 5. Os 5 sinais coletados por PRB

Cada `ValidacaoEntrega` carrega:

### Sinal 1 — Veredicto (campo `veredicto`)

`REINCIDENCIA`, `ENTREGA_VALIDADA` ou `INCONCLUSIVO` — ver §6.

### Sinal 2 — Volumetria pré-resolução

3 campos: `qtd_incs_pre_resolucao`, `clientes_unicos_pre`, `categorias_pre`.
Ver §7.

### Sinal 3 — Δ chamados vinculados

3 campos: `chamados_pre`, `chamados_pos`, `delta_chamados_pct`. Ver §8.

### Sinal 4 — PRBs novos pós-resolução

2 campos: `qtd_prbs_novos_pos_resolucao`, `prbs_novos` (lista de
`numero`). Ver §9.

### Sinal 5 — Times impactados (V3.1)

3 campos (dicts `{equipe: valor}`): `equipes_impactadas_pre`,
`equipes_impactadas_pos`, `equipes_delta_pct`. Ver §10.

---

## 6. Veredicto (REINCIDENCIA / ENTREGA_VALIDADA / INCONCLUSIVO)

Classificação aplicada via `_classificar(qtd_incs, dias_pos)`:

```python
if qtd_incs >= LIMIAR_INCS_REINCIDENCIA:          # 3
    return "REINCIDENCIA"
if qtd_incs == 0 and dias_pos >= MIN_DIAS_PARA_VALIDAR:  # 7
    return "ENTREGA_VALIDADA"
return "INCONCLUSIVO"
```

| Veredicto | Condição | Slack? |
|---|---|---|
| `REINCIDENCIA` | ≥ 3 INCs novas em `(produto, servidor)` após `data_encerrado` | ✅ |
| `ENTREGA_VALIDADA` | 0 INCs novas E ≥ 7 dias decorridos desde resolução | ❌ |
| `INCONCLUSIVO` | Casos intermediários (janela < 7d, INCs sub-limiar) | ❌ |

**Reincidência tem precedência sobre tempo:** se aparecem 3+ INCs no 2º dia,
ainda é reincidência. O time precisa ver isso rápido.

### O match (produto, servidor)

INC nova é detectada via:

```sql
SELECT * FROM lwsa.service_now_incidentes
WHERE produto = %s    -- prb.produto
  AND servidor = %s   -- prb.servidor
  AND data_abertura >= %s   -- data_encerrado do PRB
  AND organizacao IN ('Locaweb');
```

Match **exato**. PRB e INC compartilham o mesmo schema, então a taxonomia
bate. Sem fuzzy matching.

---

## 7. Volumetria pré-resolução

**Janela:** `JANELA_VOLUMETRIA_PRE_DIAS = 60` dias **antes** de `data_encerrado`.

```sql
SELECT
    COUNT(*) AS qtd,
    COUNT(DISTINCT login_cliente) AS clientes_unicos,
    COUNT(DISTINCT categoria) AS categorias
FROM lwsa.service_now_incidentes
WHERE produto = %s AND servidor = %s
  AND data_abertura >= %s   -- data_encerrado - 60d
  AND data_abertura <  %s   -- data_encerrado
  AND organizacao IN ('Locaweb');
```

**Por que esse sinal:** diferencia "PRB que apagou 50 INCs em 60 dias" de
"PRB que apagou 2 INCs". O tamanho do problema resolvido é uma métrica de
**impacto** do Change Team.

**Como interpretar:**

| qtd_incs_pre | clientes_unicos_pre | Leitura |
|---|---|---|
| Alto (≥ 20) + alta diversidade de clientes | ≥ 10 | Problema **sistêmico** — afetava muitos clientes |
| Alto (≥ 20) + poucos clientes | < 5 | Cliente específico ruidoso (1-2 enterprise rebobinando) |
| Baixo (< 5) | qualquer | PRB pequeno — pouco impacto |

---

## 8. Δ chamados vinculados (V3)

**Janela:** `JANELA_CHAMADOS_DELTA_DIAS = 14` dias em cada lado de
`data_encerrado` (simétrica).

### O match (V3 — substituiu V2)

```sql
SELECT COUNT(*) FROM dynamics.chamados
WHERE datacriacao >= %s            -- início da janela (pré OU pós)
  AND datacriacao <  %s            -- fim da janela
  AND (
        prb = %s                       -- chamado vinculado direto ao PRB
        OR (
            inc IS NOT NULL
            AND inc IN (%s, %s, ...)   -- vinculado a INC do CI no período
        )
      );
```

### Por que esse match e não outro

| Estratégia | Cobertura | Precisão | Decisão |
|---|---|---|---|
| Match por palavra-chave no produto | Alta | Baixa (falsos positivos) | V2 original — descartada |
| Match exato `chamados.produto = prb.produto` | Alta | Média (taxonomia raramente bate) | V2 (2026-06-02 cedo) — substituída |
| `chamados.prb = prb.numero` apenas | Baixa (1.4%) | Alta | Descartada (muitos `0/0`) |
| **`chamados.prb` OR `chamados.inc IN(...)`** | Média (~5%) | **Alta** | **V3 (atual)** |

O **OR** é importante: captura chamados rotulados explicitamente com o PRB
(`prb = 'PRB0070000'`) **e** chamados que falam de qualquer INC do CI no
período (`inc IN (incs_pre)`).

### Anatomia da fórmula

```python
# Em validador_entrega._avaliar_prb:
delta_pct = (chamados_pos - chamados_pre) / chamados_pre if chamados_pre > 0 else 0.0
delta_chamados_pct = round(delta_pct, 3)
```

`Δ` (delta) é a notação universal pra **"variação relativa entre dois
momentos"**. Aqui: quanto o volume de chamados vinculados mudou pós-fix em
relação ao volume pré-fix.

#### Por que dividir pelo PRÉ (e não pelo pós)

O **pré é o baseline** — a pergunta é _"em relação ao que existia ANTES,
quanto mudou DEPOIS?"_. Isso garante que:

- `pre=10, pos=5` → `(5-10)/10 = -0.5` → caiu metade ✅
- `pre=10, pos=20` → `(20-10)/10 = +1.0` → dobrou ✅
- `pre=10, pos=0` → `(0-10)/10 = -1.0` → zerou ✅

Dividir pelo pós inverteria o sentido em casos de variação grande e ficaria
contra-intuitivo.

#### Range de valores possíveis

| Valor de Δ | Significa | Conversão pra % | Marcador Slack |
|---|---|---|---|
| `-1.000` | Zerou (`pos == 0`) | -100% | ↓ |
| `-0.500` a `-0.999` | Caiu 50% a 99% | -50% a -99% | ↓ |
| `-0.001` a `-0.499` | Caiu 0% a 49% | -0% a -49% | (sem marcador) |
| `0.000` | Pós igual ao pré, OU pré era zero | 0% | (sem marcador) |
| `+0.001` a `+0.499` | Subiu 0% a 49% | +0% a +49% | (sem marcador) |
| `+0.500` ou mais | Subiu ≥ 50% | +50%+ | ↑ |

> **Conversão simples:** `pct × 100`. `-0.875` → `-87.5%`.

#### Edge cases (decisões do código)

1. **`pre == 0`:** divisão por zero seria erro. Motor reporta `0.0`
   (e não `+inf`/`null`) — escolha conservadora pra evitar disparar
   "alerta de aumento explosivo" quando não havia base de comparação.
   Você ainda vê `chamados_pre=0, chamados_pos=8` nos campos brutos,
   mas o **%** fica neutro.
2. **`pre == 0` e `pos == 0`:** trivialmente `0.0`. PRB sem nenhuma
   cobertura no Dynamics — sinal totalmente neutro (ver "0/0 é
   informação válida" abaixo).
3. **Arredondamento a 3 casas:** `round(delta_pct, 3)` — evita ruído
   tipo `-0.8750000003`. Persistido no banco como `numeric(8,3)`.

#### Limiares de destaque no Slack

| Quando | Configuração | Marcador |
|---|---|---|
| `Δ ≤ LIMIAR_REDUCAO_CHAMADOS_PCT` (default `-0.5`) | queda ≥ 50% | ↓ |
| `Δ ≥ LIMIAR_AUMENTO_CHAMADOS_PCT` (default `+0.5`) | subida ≥ 50% | ↑ |
| Entre os dois | variação ≤ 50% em qualquer direção | (sem marcador) |

Os **dois limiares são simétricos por default** (`±0.5`) e ficam em
`config.py` — podem ser calibrados independentemente. Ex.: se quiser
alertar subida mais cedo, baixe `LIMIAR_AUMENTO_CHAMADOS_PCT` pra `0.3`.

> Os mesmos limiares valem pro Δ por equipe (V3.1, §10).

**`0/0` é informação válida:** indica que esse PRB não tem chamados
vinculados explícitos — o que pode significar "fix sem ruído" OU "ETL não
está rotulando bem". Não tente "encher" o sinal com match aproximado.

### Exemplo real (execução do DB de produção)

```
PRB0055135 (REINCIDENCIA, 13 INCs novas):
  chamados_pre = 6, chamados_pos = 8, delta = +33%
  → fix falhou DUPLAMENTE (volume de INCs + contato subindo)
```

Esse é o tipo de sinal que justifica **reabrir o caso** com o CT.

---

## 9. PRBs novos pós-resolução

**Janela:** mesma do veredicto (de `data_encerrado` até `NOW()`).

```sql
SELECT numero FROM lwsa.service_now_problems
WHERE produto = %s AND servidor = %s
  AND data_abertura >= %s   -- data_encerrado do PRB original
  AND numero <> %s          -- defensivo: não conta o próprio PRB
  AND organizacao IN ('Locaweb')
ORDER BY data_abertura DESC;
```

### Por que esse sinal

Reincidência por INCs já é capturada no Sinal 1. Mas se o problema voltou
**como um PRB novo** (em vez de só INCs soltas), é um **sinal mais grave**:
indica que o Change Team teve que reabrir o caso formalmente — provavelmente
porque o fix original tratou sintoma, não causa raiz.

### Como o coordenador usa

| Situação | Leitura |
|---|---|
| `qtd_prbs_novos = 0` | Bom. Nenhum PRB reaberto pro mesmo CI |
| `qtd_prbs_novos = 1` | Atenção. Problema voltou em outra forma |
| `qtd_prbs_novos ≥ 2` | **Alerta.** Padrão de fix falho — investigar causa raiz |

No Slack: `*PRBs novos no CI:* N (PRB123, PRB456)` quando ≥ 1.

---

## 10. Times impactados (V3.1)

**Janela:** mesma do Δ chamados V3 — `JANELA_CHAMADOS_DELTA_DIAS = 14`
em cada lado de `data_encerrado`.

**Top N:** `TOP_EQUIPES_IMPACTADAS = 7` (default).

### O que responde

Pedido do coordenador (2026-06-03): _"Quem o PRB impactava? ex.: time
cobrança. Valida se o time parou de abrir chamados sobre o assunto do PRB."_

A V3.1 detalha o Δ chamados V3 (§8) **por time interno da Locaweb** —
identifica quem ESTAVA chamando antes do fix e mede a redução de cada um
pós-resolução.

### O match

```sql
SELECT COALESCE(NULLIF(TRIM(equipeproprietaria), ''), '<sem-equipe>') AS equipe,
       COUNT(*) AS qtd
FROM dynamics.chamados
WHERE datacriacao >= %s            -- início da janela (pré OU pós)
  AND datacriacao <  %s            -- fim da janela
  AND (
        prb = %s                       -- mesmo critério V3
        OR (inc IS NOT NULL AND inc IN (%s, %s, ...))
      )
GROUP BY 1
ORDER BY qtd DESC;
```

Roda 2× por PRB: uma na janela pré, outra na pós.

### Lógica de comparação

1. **Pré:** roda a query e pega o **top `TOP_EQUIPES_IMPACTADAS`** por
   volume de chamados → `equipes_impactadas_pre`.
2. **Pós:** roda a mesma query na janela pós; para cada equipe do top
   pré, lê `qtd_pos = ranking_pos.get(equipe, 0)`. Equipes que sumiram
   pós ficam com 0 explícito → `equipes_impactadas_pos`.
3. **Δ por equipe:** `pct = (qtd_pos - qtd_pre) / qtd_pre`, arredondado
   pra 3 casas → `equipes_delta_pct`.

**Importante:** só rastreamos quem ESTAVA chamando antes do fix.
Equipes novas que aparecem só no pós (mas não estavam no pré) são
ignoradas — não são "times impactados pelo PRB original".

### Campos no modelo

```python
equipes_impactadas_pre: Dict[str, int]    # {equipe: qtd_pre}
equipes_impactadas_pos: Dict[str, int]    # {equipe: qtd_pos}, mesmas keys
equipes_delta_pct: Dict[str, float]       # {equipe: pct}, mesmas keys
```

### Como interpretar

| Δ por equipe | Significado | Marcador Slack |
|---|---|---|
| `qtd_pos == 0` | Time deixou de chamar — fix segurou pra essa equipe | ✅ zerou |
| `pct ≤ -0.5` (queda ≥ 50%) | Forte redução — fix funcionou bem | ↓ |
| `-0.5 < pct < 0.5` | Mudança pequena ou ruído | (sem marcador) |
| `pct ≥ 0.5` (subida ≥ 50%) | Time CONTINUA ou AUMENTOU chamados — fix falhou pra eles | ↑ |

### Edge cases

- **`equipeproprietaria` NULL/vazia:** agrupada como `'<sem-equipe>'` —
  aparece como um time com nome literal `<sem-equipe>`. Útil pra debug
  (sinaliza chamados sem time atribuído no Dynamics).
- **PRB sem chamados vinculados:** todos os 3 dicts ficam `{}`. O bloco
  "Times impactados" simplesmente não aparece no Slack.
- **`ranking_pre` vazio mas `ranking_pos` cheio:** dicts ficam `{}` —
  intencionalmente não rastreamos equipes que só apareceram pós.

### Exemplo

Hipótese: PRB resolveu um bug na ferramenta de cobrança que afetava
internamente o time de Cobrança e o de Faturamento, com algum chamado de
overflow indo pra Suporte Geral.

```
equipes_impactadas_pre = {
    "Cobrança":         12,
    "Faturamento":       8,
    "Suporte Geral":     3,
}
equipes_impactadas_pos = {
    "Cobrança":          0,    # ← zerou! :white_check_mark:
    "Faturamento":       1,    # caiu 87%
    "Suporte Geral":     2,    # caiu 33%
}
equipes_delta_pct = {
    "Cobrança":      -1.0,
    "Faturamento":   -0.875,
    "Suporte Geral": -0.333,
}
```

Leitura: fix excelente pro time de Cobrança (zerou), bom pra Faturamento
(forte queda), discreto pra Suporte Geral (queda moderada, talvez ruído
não relacionado).

---

## 11. O que aparece no dashboard / banco / Slack

### `lwsa.motor_validacao_entrega` (24 colunas)

| Grupo | Colunas |
|---|---|
| Identificação | `id`, `execucao_id`, `prb_id`, `descricao_curta`, `produto`, `servidor`, `status_prb`, `data_resolucao` |
| Veredicto | `dias_pos_resolucao`, `qtd_incs_pos_resolucao`, `veredicto`, `incs_reincidentes` (JSON) |
| Contexto PRB | `grupo_designado`, `data_abertura_prb` |
| **Volumetria pré** | `qtd_incs_pre_resolucao`, `clientes_unicos_pre`, `categorias_pre` |
| **Δ chamados V3** | `chamados_pre`, `chamados_pos`, `delta_chamados_pct` |
| **PRBs novos** | `qtd_prbs_novos_pos_resolucao`, `prbs_novos` (JSON) |
| **Times impactados (V3.1)** | `equipes_impactadas_pre` (JSON), `equipes_impactadas_pos` (JSON), `equipes_delta_pct` (JSON) — **espelhados em `motor_validacao_entrega_equipe`** |

### `lwsa.motor_validacao_entrega_equipe` (V3.1 — relacional)

Espelho **relacional** das 3 colunas JSON `equipes_*`. 1 linha por (validação,
equipe). Pensada para consumo de dashboards (Superset, Power BI) que preferem
SQL relacional puro a explosão de JSON em runtime.

| Coluna | Tipo | Conteúdo |
|---|---|---|
| `id` | serial PK | — |
| `validacao_id` | int FK → `motor_validacao_entrega(id)` | ON DELETE CASCADE |
| `equipe` | varchar(255) | `dynamics.chamados.equipeproprietaria` (ou `'<sem-equipe>'`) |
| `qtd_pre` | int | chamados na janela pré (14d) |
| `qtd_pos` | int | chamados na janela pós (14d) — `0` = parou de chamar |
| `delta_pct` | numeric(8,3) | `(pos - pre) / pre`, -1.0 = zerou |

**Volume:** até `TOP_EQUIPES_IMPACTADAS = 7` linhas por PRB validado. Em um
ciclo típico (10 PRBs), gera ~70 linhas.

**Por que coexistir com o JSON:** o JSON é fonte da verdade pro Slack e pro
`output/dashboard_state.json` (consumido em memória pelo dataclass
`ValidacaoEntrega`). A tabela filha é fonte da verdade pra dashboards SQL.

**Query típica para Superset:**

```sql
SELECT
    e.timestamp_utc      AS detectado_em,
    v.prb_id, v.descricao_curta, v.produto, v.veredicto,
    v.grupo_designado, v.data_resolucao,
    eq.equipe, eq.qtd_pre, eq.qtd_pos, eq.delta_pct
FROM lwsa.motor_validacao_entrega v
JOIN lwsa.motor_execucao e ON e.id = v.execucao_id
JOIN lwsa.motor_validacao_entrega_equipe eq ON eq.validacao_id = v.id
WHERE v.veredicto = 'REINCIDENCIA';
```

### `output/validacoes_entrega.json`

Mesma estrutura, em JSON. Consumido pelo front-end / Power BI.

### Slack (quando habilitado)

```
⚠️🔁 PRB PRB0055135 — REINCIDÊNCIA DETECTADA
Descrição: Ações do Post-Mortem INC4629249 - RITM0296949
Produto: Locaweb - Email
Servidor/CI: Email Locaweb
Grupo designado: NOC
Resolvido em: 2026-05-28 (5d atrás)
Pré-resolução (60d): 25 INCs · 8 clientes · 3 categorias
Pós-resolução: 13 novas INCs no mesmo (produto, servidor)
Δ Chamados vinculados (14d): 6 → 8 (+33.3%) ↑
PRBs novos no CI: 1 (PRB0072001)
Times impactados (top 3 — 14d pré → pós):
    • Cobrança: 12 → 0 (-100.0%) ✅ zerou
    • Faturamento: 8 → 1 (-87.5%) ↓
    • Suporte Geral: 3 → 2 (-33.3%)
INCs: INC8847001 (P3), INC8847002 (P3), INC8847005 (P2) (+10)
_Change Team: validar se o fix entregue cobre os novos casos._
```

Disparo somente para `veredicto = REINCIDENCIA`. Validações OK ou
inconclusivas não geram Slack (evita ruído).

---

## 12. Como interpretar (operacional)

| Cenário | Volumetria pré | Δ chamados | PRBs novos | Times impactados | Veredicto | Leitura |
|---|---|---|---|---|---|---|
| Fix excelente — grande problema resolvido | Alta (50+ INCs) | ↓ (>50%) | 0 | Todos ✅ zerou ou ↓ | ENTREGA_VALIDADA | **Modelo a replicar.** |
| Fix limpo de PRB pequeno | Baixa (2-5 INCs) | 0/0 | 0 | `{}` (sem cobertura) | ENTREGA_VALIDADA | OK. Sem cobertura no Dynamics, mas sem reincidência. |
| Problema voltou em outra forma | Qualquer | Qualquer | ≥ 1 PRB | Qualquer | REINCIDENCIA OU INCONCLUSIVO | **Reabrir/investigar causa raiz.** |
| Fix piorou (contato subiu) | Qualquer | ↑ (>50%) | 0 | ≥ 1 equipe com ↑ | REINCIDENCIA | **Re-investigar URGENTE.** |
| Fix beneficiou alguns times e não outros | Qualquer | ~0 (média) | 0 | Misto (✅ + ↑) | qualquer | Detalhar: fix resolveu uma classe de chamado mas criou outra. Conversar com equipes ↑. |
| Janela curta, sem dado | — | — | 0 | `{}` | INCONCLUSIVO | Aguardar próximo ciclo. |
| Fix segurou as INCs mas contato subiu | Qualquer | ↑ (>50%) | 0 | ≥ 1 equipe com ↑ | ENTREGA_VALIDADA | Estranho. Identificar EQUIPE específica com ↑ — auditar manualmente. |

---

## 13. Cadência e agendamento

### Cadência default

`DEFAULT_INTERVALO_HORAS = 6` em [validar_entregas.py](../validar_entregas.py).

Disparos sugeridos no Task Scheduler: **00:05, 06:05, 12:05, 18:05** (fora
do horário de pico).

### Por que 6h e não 15min como o preventivo

| Motivo | Detalhe |
|---|---|
| **PRBs mudam devagar** | Status de PRB resolvido não vira hora em hora — olhar a cada 6h é o suficiente |
| **Janela de 14d é grande** | Mesmo PRB candidato sai do ciclo 14 dias depois — variações entre olhares de 6h são desprezíveis |
| **Performance** | Avaliar 10 PRBs com 4 sinais leva ~20-30s; pagar isso 96×/dia (a cada 15min) é desperdício |
| **Isolamento de falha** | Se ValidadorEntrega bugar, o preventivo (`main.py`) continua intacto |

### Como agendar (Windows Task Scheduler)

Ver passo a passo completo em **[MANUAL.md §2.7](MANUAL.md#27-agendamento-do-validadorentrega-prisma-retrospectivo)**.

Resumo: criar 2ª task no Task Scheduler apontando para
`Motor-PRB-Validador.bat`, disparo `Daily 00:05` com `Repeat every 6 hours`.

---

## 14. Como ajustar

Todos os ajustes em [config.py](../config.py):

### Mais sensível a reincidência

```python
LIMIAR_INCS_REINCIDENCIA = 2   # antes: 3
```

Cuidado: pode aumentar muito o volume de alertas Slack.

### Janela maior pra "validar" um PRB

```python
MIN_DIAS_PARA_VALIDAR = 14   # antes: 7
```

Útil se sentir que 7d é cedo demais pra confirmar que o fix segurou.

### Janela de visibilidade de PRBs

```python
JANELA_VALIDACAO_ENTREGA_DIAS = 30   # antes: 14
```

PRBs mais antigos voltam a ser avaliados todo ciclo. Cuidado com volume.

### Janela maior pra volumetria pré

```python
JANELA_VOLUMETRIA_PRE_DIAS = 90   # antes: 60
```

Pra capturar PRBs lentos (problema crescendo por meses antes do fix).

### Janela do Δ chamados

```python
JANELA_CHAMADOS_DELTA_DIAS = 7   # antes: 14
```

Janela menor é mais sensível a mudança imediata pós-fix.

### Limiares de variação pra mostrar ↓ / ↑ no Slack

```python
LIMIAR_REDUCAO_CHAMADOS_PCT = -0.3   # antes: -0.5
LIMIAR_AUMENTO_CHAMADOS_PCT =  0.3   # antes: +0.5
```

Defaults conservadores (variação ≥ 50% em qualquer direção pra marcar
seta). Reduzir os módulos pra `±0.3` deixa as setas aparecerem com
variação ≥ 30%. **Valem tanto pro Δ global quanto pro Δ por time** (§10).

Os dois são **independentes** — pode querer alertar subida mais cedo do
que reconhecer queda. Ex.: `LIMIAR_REDUCAO=-0.5, LIMIAR_AUMENTO=+0.2`
sinaliza qualquer aumento >= 20% mas só destaca quedas >= 50%.

### Top N de times impactados

```python
TOP_EQUIPES_IMPACTADAS = 10  # antes: 7
```

Aumentar pra ver cauda longa (ex.: 10+ pra debug ou análises mais
amplas); reduzir pra mostrar só os mais relevantes (ex.: 3 pra Slack
mais conciso). Não afeta a query — apenas o quanto entra em
`equipes_impactadas_pre` (e por consequência o Slack/banco).

### Status considerados "encerrados"

```python
STATUS_PRB_ENCERRADOS = (
    "Encerrado Automaticamente",
    "Concluído",
    "Aguardando Validação da Resolução",   # adicionar se DW começar a popular data_encerrado
)
```

Verificar se o status tem `data_encerrado` confiável no DW antes de
adicionar — senão vira INCONCLUSIVO eterno.

---

## 15. Histórico de versões (V1 → V2 → V3 → V3.1)

### V1 (motor original)

- Apenas veredicto (`REINCIDENCIA` / `ENTREGA_VALIDADA` / `INCONCLUSIVO`)
- 11 colunas em `motor_validacao_entrega`

### V2 (2026-06-02, ValidadorEntrega V2)

- Adiciona contexto enriquecedor:
  - Volumetria pré-resolução (60d antes)
  - Δ chamados pré/pós (14d simétrico) com match por `produto`
- Adiciona `grupo_designado` e `data_abertura_prb`
- 19 colunas em `motor_validacao_entrega` (+8 da V2)
- **Limitação observada:** match por produto trazia ruído (falsos positivos
  de chamados em outros assuntos do mesmo produto)

### V3 (2026-06-02, ValidadorEntrega V3)

- Substitui match por produto: agora `chamados.prb = prb_id` **OU**
  `chamados.inc IN (incs)` — match explícito via vínculo
- Adiciona rastreamento de **PRBs novos pós-resolução** (`qtd_prbs_novos_pos_resolucao`,
  `prbs_novos`)
- 21 colunas em `motor_validacao_entrega` (+2 da V3)
- **Ganho mensurado:** `0/0` honesto quando não há vínculo (em vez de
  inflar com ruído). PRBs com vínculo real revelam Δ preciso (ex.:
  PRB0055135 mostrou +33% com 13 INCs reincidentes — sinal duplo de falha).

### V3.1 (2026-06-03, ValidadorEntrega V3.1 atual)

- Adiciona **Times impactados** (§10): top N equipes
  proprietárias dos chamados vinculados (pré e pós) + % de redução por
  time. Usa `dynamics.chamados.equipeproprietaria`.
- Detalha o Δ chamados V3 por equipe interna Locaweb — responde
  diretamente ao pedido do coordenador: _"quem o PRB impactava e deixou
  de chamar?"_
- 24 colunas em `motor_validacao_entrega` (+3 JSON da V3.1)
- Novo threshold em config: `TOP_EQUIPES_IMPACTADAS` (introduzido como `5`,
  ajustado pra `7` ainda em 2026-06-03 a pedido — equipes com cauda longa
  cabem no recorte)
- **Ganho operacional:** Slack agora identifica EXATAMENTE quais times
  internos beneficiaram do fix e quais ainda chamam — coordenador pode
  conversar direto com o time específico que ainda tem dor.

### Versão "Radar CT" (revertida)

Tentamos uma V2 antes com heurística de palavra-chave pra delta de chamados
e outras métricas complementares. Revertida em commit `b0ff9c4` —
heurística era frágil. Snapshot preservado no commit `6f0d783` se quiser
recuperar.

---

## 16. Limitações conhecidas

### Match de chamados depende do ETL

O Δ chamados V3 só funciona se `dynamics.chamados.prb` e
`dynamics.chamados.inc` estiverem preenchidos no DW. Cobertura observada:
~1.4% dos chamados têm `prb`, ~5.4% têm `inc`. Pra PRBs sem nenhum chamado
vinculado, o sinal fica `0/0`.

**Mitigação:** o **OR** entre `prb` e `inc` amplia a recuperação. Mas
sempre haverá PRBs sem chamados vinculados.

### Sem relação direta INC→PRB no DW

O DW não tem coluna que liga uma INC ao PRB que a consolidou. Por isso o
match `(produto, servidor)` é a única forma de "INC pertence ao escopo
deste PRB" — pode levar falsos positivos quando 2 PRBs cobrem o mesmo CI
ao mesmo tempo.

### Match exato produto/servidor (sem fuzzy)

Se o CT cria o PRB com produto/servidor ligeiramente diferente das INCs
originais, o validador não encontra reincidência. Aplicação real funciona
porque a taxonomia do SNow é consistente, mas casos limite existem.

### PRBs sem `data_encerrado` confiável ficam fora

Status como "Aguardando Validação da Resolução" no DW da Locaweb sempre
têm `data_encerrado` NULL. Ficam fora da janela de avaliação por design
(`STATUS_PRB_ENCERRADOS` exclui esse status).

### Volumetria pré não considera PRBs anteriores

Se um PRB anterior já tratou parte das INCs no período de 60d antes do
fix, a volumetria pré conta TODAS as INCs do CI no período — pode
**inflar** o sinal de "tamanho do problema". Não diferencia "INCs que
o PRB anterior já resolveu" de "INCs que este PRB resolveu".

**Mitigação:** olhar `data_abertura_prb` (idade do PRB) ajuda a contextualizar.

### Sem feedback do Change Team

O motor emite veredicto, mas não recebe retroalimentação ("foi falso
positivo", "este PRB é especial"). Não aprende. Pra calibrar é preciso
ajustar thresholds no `config.py` manualmente.

### Times impactados dependem de `equipeproprietaria` preenchida

O sinal V3.1 (§10) só é útil se `dynamics.chamados.equipeproprietaria`
estiver preenchida no DW. Chamados sem time atribuído caem em
`'<sem-equipe>'` — se a maioria dos chamados vinculados não tem time,
o bloco "Times impactados" vira pouco informativo.

**Mitigação:** o `<sem-equipe>` no Slack já sinaliza visualmente o
problema de qualidade do dado.

### Equipes que mudaram de nome no Dynamics

Se uma equipe foi renomeada entre a janela pré e a pós (ex.: "Cobrança"
virou "Cobrança e Faturamento"), o validador trata como equipes distintas
— o pré aparece como "ainda chamando" (não bate) e o pós com nova chave
é ignorado (porque não estava no top do pré). Esse caso é raro mas vale
saber.

---

## Referências cruzadas

- **[REGRAS.md §14](REGRAS.md#14-validadorentrega--prisma-retrospectivo):** matriz operacional resumida
- **[ARQUITETURA.md](ARQUITETURA.md):** detalhes de implementação (`validador_entrega.py`)
- **[MANUAL.md §2.7](MANUAL.md#27-agendamento-do-validadorentrega-prisma-retrospectivo):** como agendar via Task Scheduler
- **[../GLOSSARIO.md](../GLOSSARIO.md):** termos técnicos (veredictos, volumetria, Δ chamados)
- **`config.py`:** todos os thresholds em um lugar
- **`sql/motor_tables.sql`:** DDL completa da `motor_validacao_entrega`

---

_Documento mantido por contribuidores do motor. Última atualização: 2026-06-09
(V3.1 + integração Painel Change Team no entry-point, CON-012 LOCKED preserva
veredicto)._
