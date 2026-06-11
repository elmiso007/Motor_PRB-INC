# Saúde do Cliente — Processo Completo

> **Audiência:** PO, coordenadores, analistas que vão consumir o sinal. Para
> detalhe de implementação ver [ARQUITETURA.md](ARQUITETURA.md). Para regras
> de thresholds ver [REGRAS.md](REGRAS.md). Para termos técnicos ver
> [../GLOSSARIO.md](../GLOSSARIO.md).

Este documento descreve **ponta a ponta** como o motor identifica clientes
com recorrência alta de incidentes e disponibiliza essa informação para o
plantão e a coordenação.

---

## Sumário

1. [O que é](#1-o-que-é)
2. [Por que existe](#2-por-que-existe)
3. [Fluxo do processo](#3-fluxo-do-processo)
4. [Os 4 filtros que delimitam quem entra](#4-os-4-filtros-que-delimitam-quem-entra)
5. [Como o motor identifica candidatos](#5-como-o-motor-identifica-candidatos)
6. [Como o histórico é montado (bulk + slim)](#6-como-o-histórico-é-montado-bulk--slim)
7. [O veredicto (`alerta_recorrencia_alta`)](#7-o-veredicto-alerta_recorrencia_alta)
8. [O que aparece no dashboard / banco / Slack](#8-o-que-aparece-no-dashboard--banco--slack)
9. [Como interpretar (operacional)](#9-como-interpretar-operacional)
10. [Como ajustar](#10-como-ajustar)
11. [Limitações conhecidas](#11-limitações-conhecidas)

---

## 1. O que é

Módulo automático que, **a cada ciclo do motor preventivo** (cadência 1h em
PROD desde 2026-06-09), identifica clientes Locaweb que estão **abrindo muitos
incidentes** e consolida o histórico de cada um (INCs do ServiceNow + chamados
Dynamics/KingHost) numa linha do tempo cronológica.

**Output principal:** uma tabela `lwsa.motor_saude_cliente` (e o JSON do
dashboard) com 1 linha por cliente em alerta. Quando o cliente bate critério
de **recorrência alta**, o motor sinaliza com `alerta_recorrencia_alta = true`.

**Implementação:** módulo [customer_monitor.py](../customer_monitor.py),
funções `gerar_saude_clientes` e `_clientes_com_volume`.

---

## 2. Por que existe

Requisito original (Emerson/Bruno):

> *"No plantão noturno, quando um cliente liga reclamando, o analista
> precisa abrir ServiceNow, exportar INCs do cliente, abrir Dynamics, exportar
> chamados, intercalar tudo num Excel pra entender o histórico. Demora
> 10-15 minutos por cliente."*

O motor faz esse trabalho **antes** de o cliente ligar — quando o coordenador
abre o dashboard de manhã, já tem o card pronto com o histórico consolidado.

Inspirado em "customer health score" de plataformas de CSM (Gainsight,
HubSpot), mas adaptado ao contexto operacional de TI (não comercial).

---

## 3. Fluxo do processo

```
┌─────────────────────────────────────────────────────────────────────┐
│  FASE 1 — Identificar candidatos (1 query SQL agregada)              │
└─────────────────────────────────────────────────────────────────────┘

  fonte_incidentes.contar_clientes_com_inc_recente(
      horas=30*24,                       (config.JANELA_CANDIDATOS_SAUDE_DIAS)
      tipos_usuario=("Nominal",)         (config.TIPOS_USUARIO_SAUDE_CLIENTE)
  )
        ↓ SQL com 4 filtros + login efetivo via JOIN dynamics
  ~1.300 clientes Nominais distintos com >= 1 INC nos últimos 30d
        ↓ filtro qtd >= LIMIAR_INCS_SAUDE_CLIENTE (3)
  ~10-15 candidatos com login canônico limpo

┌─────────────────────────────────────────────────────────────────────┐
│  FASE 2 — Hidratar histórico (3 queries bulk)                        │
└─────────────────────────────────────────────────────────────────────┘

  ┌─ BULK 1: listar_incidentes_para_saude(candidatos, 6 meses)
  │     1 SELECT em lwsa.service_now_incidentes com login canônico IN (...)
  │     Colunas SLIM: numero, descricao_curta, prioridade, produto,
  │     data_abertura, servidor, tem_contorno (regex SQL)
  │
  ├─ BULK 2: listar_chamados_para_saude(candidatos, 6 meses)
  │     1 query em dynamics.chamados (Locaweb)
  │     com WHERE logincliente IN (...)
  │     [KingHost desligado hoje via config.ORGANIZACOES_ATIVAS]
  │
  └─ Para cada candidato (em memória, sem mais SQL):
        ├─ _calcular_severidade_media     (P1=1.0 ... P5=0.0)
        ├─ _tem_inc_recente(7 dias)       (anti alert-fatigue)
        └─ _montar_linha_do_tempo          (mescla INCs + chamados,
                                            ordenado decrescente)

┌─────────────────────────────────────────────────────────────────────┐
│  FASE 3 — Saída (3 destinos em paralelo, defesa em camadas)          │
└─────────────────────────────────────────────────────────────────────┘

  ┌── output/dashboard_state.json (sempre primeiro — fallback robusto)
  ├── lwsa.motor_saude_cliente   (persistência Postgres, mesma transação
  │                                que clusters/prescrições)
  └── Slack                       (1 mensagem por cliente em
                                   `alerta_recorrencia_alta`)
```

**Tempo medido em produção:** ~5-10 segundos para 12 clientes (com índices
no DW). Sem os índices, levava ~80 minutos.

---

## 4. Os 4 filtros que delimitam quem entra

O SQL agregado de `contar_clientes_com_inc_recente` aplica **4 filtros
encadeados** antes de devolver o `Counter` por cliente. Isso explica por que
o número final de candidatos é tão menor que o total de INCs do DW.

### Filtro 1 — Janela temporal

```sql
WHERE data_abertura >= NOW() - INTERVAL '30 days'
```

Configurado em `JANELA_CANDIDATOS_SAUDE_DIAS = 30`. Em janelas menores
(24h), cliente real raramente acumula 3 INCs — pra capturar recorrência
natural, **30 dias é o ponto de inflexão observado** (em 7d aparecem 0
candidatos; em 30d aparecem ~10-15).

### Filtro 2 — Organização ativa

```sql
AND organizacao IN ('Locaweb')
```

Configurado em `ORGANIZACOES_ATIVAS = ("Locaweb",)`. Hoje o motor está
focado em Locaweb — KingHost é pulada inteira. Pra incluir: editar config.

### Filtro 3 — Tipo de usuário

```sql
AND tipo_usuario IN ('Nominal')
```

Configurado em `TIPOS_USUARIO_SAUDE_CLIENTE = ("Nominal",)`. Por design do
ServiceNow, INCs `tipo_usuario = 'Integração'` (~92% do volume) são abertas
por **monitoração automatizada** (Zabbix, Nagios) — `login_cliente` vem
vazio por design. Não fazem sentido para Saúde do Cliente.

### Filtro 4 — Login não-vazio e não-KingHost-residual

```sql
AND login_cliente IS NOT NULL
AND TRIM(login_cliente) <> ''
AND login_cliente NOT ILIKE '%kinghost%'
```

Casos cobertos:
- **Vazio:** algumas INCs Nominais ainda vêm com login em branco
- **URL KingHost residual:** algumas INCs classificadas como
  `organizacao = 'Locaweb'` no DW têm login `intranet.kinghost.com.br/.../ficha=NNN`
  — controlado por `LOGIN_CLIENTE_PADROES_EXCLUIDOS = ("kinghost",)`

### Após os filtros: limiar de volume

```sql
GROUP BY login_canonico HAVING COUNT(*) >= 3
```

Configurado em `LIMIAR_INCS_SAUDE_CLIENTE = 3`. Cliente precisa de pelo
menos 3 INCs no período pra entrar.

---

## 5. Como o motor identifica candidatos

A query agregada usa **2 transformações de domínio** críticas:

### Login canônico

O `login_cliente` no DW vem em **5 formatos diferentes** para o mesmo
cliente. A função `sql_normalizar_login_cliente` (port literal do projeto
irmão `locapredict`) unifica:

| Formato no banco | Canônico |
|---|---|
| `govonifelipe` | `govonifelipe` |
| `govonifelipe (Cód. 1100035861)` | `1100035861` |
| `1100035861` (dígitos puros) | `1100035861` |
| `https://intranet.../ficha=424593` | `424593` |
| `MZ-Viagens.Br` | `mzviagensbr` |

Sem isso, o mesmo cliente apareceria em 2 candidatos diferentes.

### Login efetivo (enriquecimento via dynamics.chamados)

Quando uma INC do ServiceNow tem chamado correspondente em
`dynamics.chamados.inc`, o motor **prefere** o `logincliente` da Dynamics
em vez do `login_cliente` do SNow:

```sql
login_efetivo = COALESCE(
    NULLIF(TRIM(dynamics.chamados.logincliente), ''),
    service_now_incidentes.login_cliente
)
```

**Por quê:** o `logincliente` da Dynamics é sempre **limpo** (`trieste1`,
`webcolors3`, `dougdonda` — sem URL, sem `(Cód.)`). O `login_cliente` do
SNow pode vir vazio, com URL ou com formato `(Cód. NNN)`. Cobertura: ~5-10%
das INCs cruzam com chamados. Onde cruza, ganhamos login real.

**Efeito mensurado:** passou de 9 → 12 candidatos com login real legível
(`novon`, `doverroll`, `webcolors3`, `diegopdias`, `dmsolucoestec`
apareceram com login limpo; `737287` e `1100035861` foram substituídos
pelos logins reais).

---

## 6. Como o histórico é montado (bulk + slim)

Depois de identificar os candidatos, o motor precisa carregar o **histórico
de 6 meses** de cada um (`JANELA_SAUDE_CLIENTE_MESES = 6`). Antes da
calibração, isso eram **N×3 queries em série** (~80 min para 12 clientes).
Hoje são **3 queries em bulk** (~5-10 s).

### Bulk 1 — INCs históricas (slim)

```sql
WITH chamados_por_inc AS (
    SELECT DISTINCT ON (inc) inc, logincliente
    FROM dynamics.chamados
    WHERE inc IS NOT NULL
      AND datacriacao >= NOW() - INTERVAL '187 days'
    ORDER BY inc, datacriacao DESC
)
SELECT
    sni.numero,
    sni.descricao_curta,
    sni.prioridade,
    sni.produto,
    sni.data_abertura,
    sni.servidor,
    {LOGIN_NORM_EFETIVO} AS login_cliente,
    (COALESCE(sni.descricao,'')||' '||COALESCE(sni.fechamento,''))
        ~* 'contorno|workaround|...' AS tem_contorno
FROM lwsa.service_now_incidentes sni
LEFT JOIN chamados_por_inc c ON c.inc = sni.numero
WHERE {LOGIN_NORM_EFETIVO} IN (%s, %s, ...)   -- candidatos canônicos
  AND sni.data_abertura >= NOW() - INTERVAL '6 months'
  AND sni.organizacao IN ('Locaweb');
```

**Slim:** só puxa colunas usadas pra montar linha do tempo (sem `descricao`
longa, sem `atualizacoes` de texto). `tem_contorno` é **pré-computado**
no SQL via regex POSIX.

### Bulk 2 — Chamados Locaweb (Dynamics)

Análogo: `WHERE logincliente IN (...)` com normalização SQL aplicada.

### Cálculos em memória (sem mais SQL)

Para cada candidato com seus INCs + chamados, o motor calcula:

| Cálculo | Fórmula |
|---|---|
| `severidade_media` | `mean(PESO[prioridade])` onde P1=1.0, P2=0.75, P3=0.50, P4=0.25, P5=0.00 |
| `_tem_inc_recente` | `True` se houver INC com `data_abertura ≥ NOW() - 7d` |
| `linha_do_tempo` | INCs + chamados mesclados, ordenado por `data` desc |

---

## 7. O veredicto (`alerta_recorrencia_alta`)

Disparado **se ambas** as condições:

```python
alerta_recorrencia_alta = (
    qtd_incs_periodo >= LIMIAR_INCS_SAUDE_CLIENTE   # 3 INCs em 6 meses
    AND _tem_inc_recente(JANELA_RECENCIA_ALERTA_DIAS)  # INC nos últimos 7 dias
)
```

### Por que o critério de recência

**Sem recência:** cliente que teve 5 INCs em janeiro continuaria sendo
alertado todo dia até julho — 6 meses de alertas idênticos. Slack inutilizado.

**Com recência:**
- Cliente com 5 INCs em janeiro e **sem nova INC em fevereiro** → para de
  alertar
- Cliente abre nova INC em março → alerta volta automaticamente

**Operacional:** "cliente acalmou" não enche Slack. "Cliente voltou a abrir
incidente" volta a alertar.

---

## 8. O que aparece no dashboard / banco / Slack

### `lwsa.motor_saude_cliente`

1 linha por cliente em alerta. Colunas:

| Coluna | Significado |
|---|---|
| `execucao_id` | FK pra `motor_execucao` |
| `cliente_login` | Login canônico (sempre limpo após calibração) |
| `qtd_incs_periodo` | Total de INCs nos 6 meses |
| `qtd_chamados_periodo` | Total de chamados Dynamics/KingHost |
| `severidade_media` | 0.0 (P5) a 1.0 (P1) — média ponderada |
| `alerta_recorrencia_alta` | `true` quando dispara o veredicto |
| `linha_do_tempo` | JSON com eventos cronológicos |

### `output/dashboard_state.json`

Mesma estrutura, em JSON, gravado a cada ciclo. Consumido pelo front-end
(ou diretamente em Power BI / Streamlit).

### Slack (quando habilitado)

```
🌡️ Saúde do Cliente — Recorrência Alta
Cliente: `govonifelipe`
INCs em 6 meses: 11
Chamados em 6 meses: 25
Severidade média: 0.25
Total de eventos consolidados: 36
_Use o dashboard para ver a linha do tempo completa._
```

**Importante:** desde 2026-06-02, `SLACK_HABILITADO` default é `false`.
O motor prepara e **loga** a mensagem mas não envia. Pra ativar:
`$env:SLACK_HABILITADO = "true"`.

---

## 9. Como interpretar (operacional)

| Volume (INCs em 6m) | Severidade | Interpretação |
|---|---|---|
| Alto (≥ 10) | Alta (≥ 0.5) | **Atenção do gerente de conta + suporte premium** |
| Alto (≥ 10) | Baixa (< 0.5) | "Cliente ruidoso" — alto contato mas tudo P3-P5. Acompanhar mas sem urgência |
| Baixo (3-5) | Alta (≥ 0.5) | Casos isolados graves — monitorar tendência |
| Baixo (3-5) | Baixa (< 0.5) | Não dispara alerta (mesmo se entrou nos candidatos) |

A **linha do tempo** mostra padrão de contato — útil pra detectar:
- Cliente que abre INCs sempre no mesmo CI → problema sistêmico no produto
- Cliente que tem chamados crescendo antes da próxima INC → escalada visível
- Cliente que ficou semanas sem contato e voltou em massa → mudança no
  ambiente dele

---

## 10. Como ajustar

Todos os ajustes em [config.py](../config.py):

### Mais clientes no alerta (relaxar limiar)

```python
LIMIAR_INCS_SAUDE_CLIENTE = 2   # antes: 3
```

### Janela maior de candidatos

```python
JANELA_CANDIDATOS_SAUDE_DIAS = 60   # antes: 30
```

### Histórico maior

```python
JANELA_SAUDE_CLIENTE_MESES = 12   # antes: 6
```

**Cuidado:** isso aumenta o resultado da query bulk e pode pesar.
Recomendo medir tempo de ciclo antes/depois.

### Janela de recência (anti alert-fatigue)

```python
JANELA_RECENCIA_ALERTA_DIAS = 14   # antes: 7
```

### Incluir INCs de monitoração na contagem

```python
TIPOS_USUARIO_SAUDE_CLIENTE = ("Nominal", "Integração")   # antes: ("Nominal",)
```

Atenção: a maioria das INCs de Integração vem com `login_cliente` vazio,
então o efeito prático é pequeno — mas inflaria o `qtd_incs_periodo` dos
clientes que aparecem.

### Adicionar outro padrão de login a excluir

```python
LOGIN_CLIENTE_PADROES_EXCLUIDOS = ("kinghost", "outro-tenant")
```

Aplicado via `NOT ILIKE '%padrão%'`.

### Incluir KingHost no escopo

```python
ORGANIZACOES_ATIVAS = ("Locaweb", "KingHost")
```

Requer também adicionar mapeamento de KingHost no
`TABELAS_CHAMADOS_POR_ORGANIZACAO` e validar que `kinghost.chamados` tem
as colunas equivalentes.

---

## 11. Limitações conhecidas

### Limiar único independente de porte do cliente

Cliente pequeno (1 servidor) e cliente enterprise (50 servidores) usam o
mesmo `LIMIAR_INCS_SAUDE_CLIENTE = 3`. Para enterprise, 3 INCs em 6 meses
é proporcionalmente trivial.

**Mitigação atual:** o sinal `severidade_media` ajuda a separar — cliente
enterprise com 3 INCs P5 (severidade 0.0) provavelmente não é problema.

**Solução real:** segmentar limiar por porte (exige dado de porte/MRR no
banco — não temos).

### Cobertura parcial do enriquecimento via dynamics

Apenas ~5-10% das INCs em 24h cruzam com `dynamics.chamados.inc`. O resto
continua usando o `login_cliente` do SNow direto. Quando esse vem ruim
(URL, vazio), o cliente fica invisível pra Saúde.

**Solução real:** ETL upstream popular `login_cliente` mais consistentemente,
ou expandir o cruzamento via outras tabelas.

### Sem detecção de cliente que reincide silenciosamente

Se um cliente abre INCs **só uma vez por mês**, ele nunca atinge 3 INCs
na janela de 30d. Acaba ficando invisível mesmo com padrão claro de
recorrência crônica.

**Solução real:** olhar janela maior (90-180d) com limiar diferente
(`5 INCs em 180d`). Não implementado.

### Histórico recalculado a cada ciclo (sem persistência de tendência)

Cada ciclo recalcula tudo do zero. Não detecta "severidade subindo nas
últimas semanas" automaticamente.

**Mitigação:** o banco persiste cada ciclo — analista pode rodar query
comparando ciclos (`SELECT ... GROUP BY DATE_TRUNC('week', timestamp_utc)`).

---

## Referências cruzadas

- **[REGRAS.md §9](REGRAS.md#9-saúde-do-cliente):** matriz operacional resumida
- **[ARQUITETURA.md](ARQUITETURA.md):** detalhes de implementação (`customer_monitor.py`)
- **[MANUAL.md](MANUAL.md):** como rodar e operar o motor
- **[../GLOSSARIO.md](../GLOSSARIO.md):** termos técnicos
- **`config.py`:** todos os thresholds em um lugar

---

_Documento mantido por contribuidores do motor. Última atualização: 2026-06-09
(cadência do motor preventivo revista para 1h em PROD; comportamento da
Saúde do Cliente inalterado)._
