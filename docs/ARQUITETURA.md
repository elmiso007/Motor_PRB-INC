# Arquitetura — Motor Prescritivo PRB

> **Audiência:** desenvolvedores que vão contribuir com o motor, code reviewers,
> mantenedores futuros. Para quem **usa** o motor, veja [MANUAL.md](MANUAL.md).
> Para as **regras de negócio** (matriz P1-P5), veja [REGRAS.md](REGRAS.md).
> Para termos técnicos, veja [../GLOSSARIO.md](../GLOSSARIO.md).

Este documento explica **como o motor foi construído e por quê**. Decisões de
design, padrões adotados, alternativas descartadas. Não é manual de uso — é
documentação técnica para quem precisa **entender o motor por dentro**.

---

## Sumário

1. [Visão de uma página](#1-visão-de-uma-página)
2. [Arquitetura em camadas](#2-arquitetura-em-camadas)
3. [Fluxo de dados end-to-end](#3-fluxo-de-dados-end-to-end)
4. [Os 15 módulos abertos](#4-os-15-módulos-abertos)
5. [Os 7 princípios transversais](#5-os-7-princípios-transversais)
6. [Decisões importantes (e por quê)](#6-decisões-importantes-e-por-quê)
7. [Pontos de extensão](#7-pontos-de-extensão)
8. [Limitações conscientes do MVP](#8-limitações-conscientes-do-mvp)
9. [Como contribuir sem quebrar](#9-como-contribuir-sem-quebrar)

---

## 1. Visão de uma página

### O que o motor faz

**Prisma preventivo** — a cada 1 hora (Windows Task Scheduler, single-run):

1. **Lê do PostgreSQL:** todas as INCs abertas nas últimas 24h, todos os PRBs
   ativos, todos os chamados de suporte das últimas 24h (Locaweb + Kinghost).
2. **Agrupa INCs semanticamente similares** (TF-IDF + DBSCAN do scikit-learn)
   em "clusters" — problemas que falam do mesmo assunto.
3. **Calcula scores** de criticidade e ineficiência para cada cluster.
4. **Aplica a matriz oficial P1-P5** para classificar cada cluster.
5. **Sugere ações:** abrir PRB novo, repriorizar PRB existente, monitorar ou
   nada.
6. **Avalia "Saúde do Cliente":** clientes com ≥3 INCs em 6 meses recebem
   alerta de recorrência alta + linha do tempo consolidada (ServiceNow +
   chamados).
7. **Emite 3 saídas:** JSON em arquivo, persistência em Postgres, alertas
   críticos no Slack.

### Para quem o motor existe

- **Time de plantão:** recebe alertas Slack quando há crise (P1) ou padrão
  preocupante. **Quem age.**
- **Coordenadores:** acompanham dashboard com clusters, prescrições, saúde de
  clientes. **Quem prioriza e calibra.**
- **PO/Liderança:** análise de tendências via SQL no banco. **Quem decide
  rumos.**

### Por que existe

Sem o motor, plantão dependia de **percepção humana** para notar que 5 INCs
isoladas eram, na verdade, o mesmo problema crescendo. O motor faz essa
detecção sistematicamente e **antecipa** crises antes que escalem.

Requisito original levantado em reunião com Jéssica, Victor e Bruno.

---

## 2. Arquitetura em camadas

O motor é organizado em **4 níveis** de dependência. Imports só vão "para baixo"
— nunca para cima. Garantia: **sem ciclos de import**.

```
┌─────────────────────────────────────────────────┐
│  Nível 4 — ORQUESTRAÇÃO                         │
│  main.py, validar_entregas.py, scheduler.py     │
│  (entry points single-run, sem loop interno)    │
└────────────────────┬────────────────────────────┘
                     │ depende de
┌────────────────────┴────────────────────────────┐
│  Nível 3 — DOMÍNIO                              │
│  extractor.py, analyzer.py, rules_engine.py     │
│  customer_monitor.py, notifier.py, notifier_db  │
└────────────────────┬────────────────────────────┘
                     │ depende de
┌────────────────────┴────────────────────────────┐
│  Nível 2 — UTILITÁRIOS                          │
│  time_utils.py, db.py                           │
└────────────────────┬────────────────────────────┘
                     │ depende de
┌────────────────────┴────────────────────────────┐
│  Nível 1 — FUNDAÇÃO                             │
│  config.py, models.py                           │
└─────────────────────────────────────────────────┘
```

### Por que essa organização

**Nível 1 (Fundação)** não importa nada interno — só stdlib. Isso permite:
- Testar `config.py` ou `models.py` sem instalar nada.
- Garantir que mudança aqui não cascateia (poucos têm acesso, mas tudo depende).

**Nível 2 (Utilitários)** importam só de Nível 1. São funções/classes
reutilizáveis sem domínio.

**Nível 3 (Domínio)** é onde mora **a lógica de negócio**. Cada módulo tem
responsabilidade única e pode importar de Níveis 1 e 2.

**Nível 4 (Orquestração)** importa quase tudo — papel é juntar as peças.

### Verificação concreta

Você pode verificar a hierarquia com:

```bash
grep -h "^import\|^from" config.py models.py time_utils.py db.py | grep -v stdlib
```

Resultado esperado: apenas `import config` (do `time_utils.py`). Nenhum import
de Nível 3 ou 4 em Níveis 1-2.

---

## 3. Fluxo de dados end-to-end

Trajeto completo dos dados em um ciclo do prisma preventivo (cadência 1h em
PROD), com volumes reais do mock.

```
┌──────────────────────────────────────────────────────────────────────┐
│  FASE 1: EXTRAÇÃO                                                     │
└──────────────────────────────────────────────────────────────────────┘

  Postgres (lwsa.service_now_incidentes)
        ↓ SELECT WHERE data_abertura >= NOW() - 24h
        ↓
  91 rows (text cru, BRT naive)
        ↓
  extractor._row_para_incidente() × 91
        ↓ (parsers: data BRT→UTC, prioridade "3"→"P3", etc.)
        ↓
  91 objetos Incidente (UTC tz-aware)
        ↓
  + 80 InteracaoChamado (dynamics.chamados + kinghost.chamados)
  + 2 PRBExistente (lwsa.service_now_problemas, status ativos)

┌──────────────────────────────────────────────────────────────────────┐
│  FASE 2: ANÁLISE                                                      │
└──────────────────────────────────────────────────────────────────────┘

  91 Incidentes
        ↓
  analyzer._preparar_textos [normaliza, lowercase, remove acentos via NFKD]
        ↓
  91 strings limpas
        ↓
  analyzer._clusterizar [TF-IDF + DBSCAN cosine, eps=0.55]
        ↓
  91 labels
        ↓
  Agrupa por label, singletons viram clusters próprios
        ↓
  5 clusters formados
        ↓
  Para cada cluster:
    ├─ _score_criticidade (4 componentes ponderados: 0.35+0.30+0.25+0.10)
    ├─ _score_ineficiencia (0.6 volume + 0.4 velocidade)
    ├─ detectar_cis_recorrentes (CIs que se repetem em 15 dias)
    └─ contar chamados Locaweb/Kinghost relacionados (por produto)
        ↓
  5 objetos Cluster (ordenados por criticidade DESC)

┌──────────────────────────────────────────────────────────────────────┐
│  FASE 3: REGRAS                                                       │
└──────────────────────────────────────────────────────────────────────┘

  5 Cluster + 2 PRBExistente
        ↓
  rules_engine.prescrever_lote [defesa por cluster]
        ↓ Para cada cluster:
        ↓
  ├─ _avaliar_cascata (P1 → P2 → P3 → P4 → P5)
  │  (primeira regra que casar vence)
  │
  ├─ _gatilho_proativo_p3 (≥5 INCs P3 idênticas → promove para P2)
  │
  ├─ _sugerir_repriorizacao (match cluster ↔ PRB por produto+servidor)
  │
  └─ _determinar_acao (ABRIR_PRB | REPRIORIZAR_PRB | MONITORAR | NENHUMA)
        ↓
  5 objetos PrescricaoPRB (com justificativas auditáveis em texto livre)

┌──────────────────────────────────────────────────────────────────────┐
│  FASE 4: SAÚDE DO CLIENTE  (bulk + slim — 3 queries totais)           │
└──────────────────────────────────────────────────────────────────────┘

  fonte_incidentes.contar_clientes_com_inc_recente(30 dias, ("Nominal",))
        ↓ SQL agregado (GROUP BY login_canonico)
  ~1.400 clientes Nominais (Integração filtrada no banco)
        ↓ filtro qtd >= 3
  ~13 candidatos canônicos (após sql_normalizar_login_cliente)

  ┌─ BULK 1: listar_incidentes_para_saude(candidatos, 6m)
  │     SQL único: WHERE login_canonico IN (...) AND data_abertura >= ...
  │     Colunas slim: numero, descricao_curta, prioridade, produto,
  │     data_abertura, servidor, tem_contorno (pré-computado via regex SQL)
  │     → Dict[login → List[Incidente]]
  │
  └─ BULK 2+3: listar_chamados_para_saude(candidatos, 6m)
        ├─ 1 query Dynamics (Locaweb)  com login_canonico IN (...)
        └─ 1 query KingHost            com login_canonico IN (...)
        → Dict[login → List[InteracaoChamado]]
        ↓
  Para cada candidato (em memória, sem mais SQL):
    ├─ _calcular_severidade_media [P1=1.0 ... P5=0.0]
    ├─ _tem_inc_recente(7 dias) [anti alert-fatigue]
    └─ _montar_linha_do_tempo [INCs + chamados ordenados cronologicamente]
        ↓
  13 objetos SaudeCliente (ordenados por volume DESC)

  Performance medida: ~30s (vs ~80min antes do bulk+slim+índices).

┌──────────────────────────────────────────────────────────────────────┐
│  AGREGAÇÃO                                                            │
└──────────────────────────────────────────────────────────────────────┘

  ExecucaoMotor consolidado:
    ├─ timestamp_utc
    ├─ clusters: 5
    ├─ prescricoes: 5
    ├─ saude_clientes: 13
    ├─ total_incs_lidas: 91
    ├─ total_chamados: 80
    ├─ duracao_ciclo_ms (medido até FASE 5b)
    └─ erros: []

┌──────────────────────────────────────────────────────────────────────┐
│  FASE 5: SAÍDAS (3 paralelas, defesa independente)                    │
└──────────────────────────────────────────────────────────────────────┘

  5a. JSON   (sempre primeiro — fallback robusto)
      ↓ notifier.gravar_payload_dashboard(execucao)
      ↓
      ./output/dashboard_state.json

  5b. POSTGRES (lwsa.motor_*)
      ↓ notifier_db.persistir_execucao(execucao)
      ↓ Transação atômica:
      ↓   INSERT motor_execucao → execucao_id
      ↓   INSERT motor_cluster × 5
      ↓   INSERT motor_prescricao × 5
      ↓   INSERT motor_saude_cliente × 13
      ↓
      24 rows persistidas

  5c. SLACK (apenas alertas críticos)
      ↓ notifier.disparar_alertas_criticos(execucao)
      ↓ Filtra: prescricoes.urgencia=CRITICA + saude.alerta_recorrencia_alta
      ↓ Rate limit 1s entre envios (se webhook configurado)
      ↓
      N mensagens enviadas
```

### Volumes consolidados (mock)

- **Entrada:** ~173 rows do Postgres (91 INCs + 80 chamados + 2 PRBs).
- **Memória durante ciclo:** ~196 objetos Python.
- **Saída:** 1 arquivo JSON (~30 KB) + 24 rows Postgres + ~13-15 mensagens Slack.
- **Tempo total:** ~5-10s.

### A ordem das saídas é deliberada

```
5a. JSON      → rápido (~10ms), sem rede, fallback
5b. Postgres  → médio (50-100ms), rede local
5c. Slack     → lento (~5s com rate limit), rede externa
```

**Princípio:** ordem por **probabilidade de sucesso decrescente**. Se uma cair,
as anteriores já gravaram tudo.

---

## 4. Os 15 módulos abertos

Resumo do papel de cada um. Para detalhes técnicos profundos, consulte o código
(citações `arquivo.py:linhas` para referência).

### Nível 1 — Fundação

#### `config.py` (~200 linhas)

**Papel:** centralizar **todas as decisões de produto** do motor. Thresholds,
janelas temporais, termos heurísticos, credenciais (via env vars), registry de
chamados por organização, mapeamento prioridade→peso.

**Princípio:** zero número mágico no código. Tudo que afeta decisão mora aqui.

**Como evoluir:** ajustar threshold = mudar 1 linha. Adicionar organização =
adicionar entrada no dict `TABELAS_CHAMADOS_POR_ORGANIZACAO`.

#### `models.py` (~165 linhas)

**Papel:** 6 dataclasses tipados que formam o domínio do motor:

- **Dados primários:** `Incidente`, `PRBExistente`, `InteracaoChamado`.
- **Resultados:** `Cluster`, `PrescricaoPRB`, `SaudeCliente`.
- **Agregador raiz:** `ExecucaoMotor`.

**Princípio:** dataclass para conceitos de domínio, não para detalhes técnicos
internos.

**Hierarquia:** rasa (3 níveis: dados → resultados → agregador). Sem classes
intermediárias técnicas (Token, Vetor, etc. — esses são detalhes do `analyzer`).

### Nível 2 — Utilitários

#### `time_utils.py` (~60 linhas)

**Papel:** padronização UTC ↔ BRT. Funções:
- `agora_utc()` — substituto de `datetime.now()` (sempre UTC tz-aware).
- `naive_banco_para_utc(dt)` — converte texto BRT do banco para UTC interno.
- `utc_para_string_banco(dt)` — caminho inverso, para queries SQL.

**Princípio:** **internamente UTC, externamente BRT**. Sem ambiguidade de fuso
em comparações ou ordenações.

#### `db.py` (~110 linhas)

**Papel:** acesso ao PostgreSQL via `psycopg2`. Lê `config.ini` compartilhado
com o projeto irmão locapredict.

- `resolve_config_path()` — busca `config.ini` em paths conhecidos.
- `load_db_config()` — carrega seção `[database]`.
- `conectar()` — context manager que garante fechamento.

**Lazy import de psycopg2:** módulo importável mesmo sem a lib (testes, CI).

### Nível 3 — Domínio

#### `extractor.py` (~720 linhas, o maior módulo)

**Papel:** trazer dados de fora para Python.

**ABCs (contratos):**
- `FonteIncidentes` — `listar_incidentes_recentes/cliente`,
  `listar_incidentes_por_produto_servidor(produto, servidor, desde, ate=None)`
  (com `ate` opcional para janela bilateral pré/pós),
  `listar_prbs_abertos/para_validacao`, `contar_clientes_com_inc_recente`
  (agregado, para a Saúde do Cliente), `listar_incidentes_para_saude` (bulk + slim),
  `contar_incidentes_no_ci_periodo` (volumetria pré do ValidadorEntrega),
  `listar_prbs_novos_no_ci_periodo` (PRBs novos pós-resolução).
- `FonteChamados` — `listar_chamados_periodo/cliente`, `listar_chamados_para_saude`
  (bulk Locaweb + KingHost), `contar_chamados_vinculados` (delta pré/pós V3 do
  ValidadorEntrega, match por `chamados.prb = prb_id` OU `inc IN (...)`).
  `contar_chamados_por_produto` marcado como deprecated (era a V2 com match
  por produto — substituído por `contar_chamados_vinculados`).

**Implementações concretas:**
- `ServiceNowExtractor` — SQL real em `lwsa.service_now_*`.
- `ChamadosExtractor` — SQL real iterando registry declarativo.
- `ServiceNowExtractorMock`, `ChamadosExtractorMock` — dados sintéticos.

**Helpers de normalização e filtros** (no topo do módulo):
- `sql_normalizar_login_cliente(coluna)` — expressão PostgreSQL canônica para
  unificar formatos de `login_cliente` (port do locapredict). Usado em todos
  os WHEREs e GROUP BYs da Saúde do Cliente.
- `normalizar_login_cliente(s)` — equivalente Python (regex), usado no mock
  para coerência em testes.
- `_filtro_orgs_sni()` — cláusula `AND organizacao IN (...)` a partir de
  `config.ORGANIZACOES_ATIVAS`. Aplicada em todos os SELECTs de INCs/PRBs.
- `_registry_chamados_ativo()` — devolve `TABELAS_CHAMADOS_POR_ORGANIZACAO`
  filtrado por orgs ativas (KingHost pulada quando inativa).
- `_filtro_padroes_login_excluidos(coluna)` — cláusula `AND col NOT ILIKE '%pat%'`
  a partir de `config.LOGIN_CLIENTE_PADROES_EXCLUIDOS`. Aplicada em
  `contar_clientes_com_inc_recente`.
- `_sql_cte_chamados_por_inc(janela_dias)` — CTE PostgreSQL com `DISTINCT ON (inc)`
  pra enriquecer INCs com `dynamics.chamados.logincliente` (login efetivo).

**Parsers defensivos:**
- `_parse_datetime` — text → UTC tz-aware (fallback None se inválido).
- `_parse_prioridade` — "3" → "P3" (default "P4" se inválido).
- `_contar_atualizacoes` — regex de timestamps no texto livre + fallback.
- `_detectar_contorno` — heurística textual.

**Factory pattern:** `criar_fonte_incidentes()` / `criar_fonte_chamados()`
decidem mock vs. real via `USAR_MOCKS` (default `false` — DB real).

**Registry declarativo:** `_montar_sql_chamados(spec, where)` constrói SQL
dinamicamente para qualquer organização, lendo de
`config.TABELAS_CHAMADOS_POR_ORGANIZACAO`.

#### `analyzer.py` (~310 linhas)

**Papel:** clusterização semântica + scores. **Único módulo que usa ML.**

**Pré-processamento** (`_normalizar`):
- Remove acentos via NFKD.
- Lower-case.
- Remove pontuação não-alfanumérica.
- Colapsa espaços.

**Stop-words customizadas PT-BR** (60 palavras, sem acentos para casar com texto
normalizado).

**Clusterização:**
- `TfidfVectorizer(max_features=5000, ngram_range=(1,2))` — TF-IDF com unigrams
  e bigrams.
- `DBSCAN(eps=0.55, min_samples=2, metric='cosine')` — descobre número de
  clusters automaticamente, identifica outliers (label `-1`).
- **Fallback Jaccard** se sklearn não disponível.
- **Fusão por (produto, servidor)** (`_fundir_singletons_por_ci`):
  pós-processamento que agrupa singletons que compartilham mesmo `produto`
  E mesmo `servidor` truthy. Compensa casos onde TF-IDF não detecta
  similaridade textual mas operacionalmente é o mesmo caso no mesmo CI.

**Scores:**
- **Criticidade** (0-1): combinação ponderada de volume (0.35) + indisponibilidade
  (0.30) + sem-contorno (0.25) + recorrência CI (0.10).
- **Ineficiência** (0-1): composição volume de updates (0.6) + velocidade em
  updates/hora (0.4).

**Detecção de CI recorrente:** mapa `Counter` de servidores em janela móvel de
15 dias. Requisito do Victor.

#### `rules_engine.py` (~415 linhas, o "coração regulatório")

**Papel:** aplicar a matriz oficial P1-P5. **Determinístico — sem ML.**

**Cascata** (`_avaliar_cascata`): avalia P1 → P2 → P3 → P4 → P5 em ordem.
Primeira que casar vence. Cada nível tem função própria (`_avaliar_p1` a
`_avaliar_p4`).

**Helpers compartilhados:**
- `_qualquer_termo_no_cluster(termos)` — usa regex `\b...\b` (word boundary)
  para evitar falsos positivos com siglas curtas. Esse helper foi corrigido
  durante o desenvolvimento por causa de um bug onde "ra " (Reclame Aqui)
  casava em "fora". Hoje protege todos os termos curtos.
- `_qtd_sem_contorno`, `_qtd_com_contorno` — contagens.
- `_ola_estourado_implicito` — heurística MVP (banco não tem `breach_time` do
  SNow ainda).

**Gatilho proativo** (`_gatilho_proativo_p3`): ≥5 INCs P3 no mesmo cluster →
adiciona justificativa textual + **promove P3 para P2** (se a cascata
classificou como P3). Antecipa escalada.

**Sugestão de repriorização:**
- `_buscar_prb_correspondente` — match por (produto + servidor).
- `_sugerir_repriorizacao` — compara prioridade nova vs. atual via
  `ORDEM_PRIORIDADE`. **Só sugere upgrade**, nunca downgrade (conservadorismo).

**Determinação da ação final** (`_determinar_acao`): cascata interna que decide
entre `ABRIR_PRB`, `REPRIORIZAR_PRB`, `MONITORAR`, `NENHUMA`.

**Defesa em camadas:** `prescrever_lote` envolve `prescrever` com try/except
por cluster. Falha em 1 cluster não derruba os outros.

#### `customer_monitor.py` (~190 linhas, "Saúde do Cliente")

**Papel:** avaliar clientes recorrentes (requisito Emerson/Bruno).

**Estratégia em 2 fases (bulk):**

1. **Identificar candidatos** — `fonte_incidentes.contar_clientes_com_inc_recente`
   roda **SQL agregado** (`GROUP BY login_canonico`) em janela de 30 dias com:
   - Filtro `tipo_usuario IN ('Nominal',)` — INCs de monitoração ficam de fora.
   - Normalização do `login_cliente` via `sql_normalizar_login_cliente` (port
     do projeto locapredict) — unifica formatos como `username (Cód. NNN)`,
     `ficha=NNN`, dígitos puros.
   - Filtro `qtd >= LIMIAR_INCS_SAUDE_CLIENTE` (3).
   Resultado: lista de ~10-15 login_canonico (de ~1.400 Nominais).

2. **Hidratar histórico (BULK)** — 2 chamadas que substituem N×2 queries seriais:
   - `listar_incidentes_para_saude(candidatos, 6m)` — 1 SELECT com
     `WHERE login_canonico IN (...)`, colunas slim, `tem_contorno`
     pré-computado via regex SQL.
   - `listar_chamados_para_saude(candidatos, 6m)` — 1 query Locaweb + 1 KingHost
     (sem `_descobrir_organizacao_via_inc`; cada org devolve só clientes que
     têm registro lá).

**Cálculos por candidato (em memória, sem mais SQL):**
- `_calcular_severidade_media` — média ponderada de prioridades (P1=1.0,
  P5=0.0).
- `_tem_inc_recente` — INC nas últimas 7 dias (anti alert-fatigue).
- `_montar_linha_do_tempo` — mescla INCs + chamados em ordem cronológica
  decrescente.

**Veredicto:** `alerta_recorrencia_alta = (qtd_incs >= 3) AND _tem_inc_recente(7)`.

**Por que bulk:** reduziu de ~36 round-trips/ciclo (~80 min) para 3 (~30s).
Com os índices `idx_sni_data_abertura`, `idx_dyn_chamados_datacriacao`,
`idx_kh_chamados_datacriacao`, `idx_sni_data_tipo` no DBA, o ciclo total cai
para ~30-45s.

#### `validador_entrega.py` (~210 linhas) — prisma retrospectivo

**Papel:** complemento ao `rules_engine` (preventivo) — olha PRBs **já
entregues** pelo Change Team e verifica se o problema realmente foi resolvido.
Fecha o loop de qualidade do fix.

**Estratégia por PRB:** `_avaliar_prb(prb, fonte_inc, fonte_chamados)` coleta
**4 sinais**:

1. **Veredicto** via `fonte_inc.listar_incidentes_por_produto_servidor` +
   `_classificar(qtd_pos, dias_pos)`:
   - `REINCIDENCIA` se `qtd ≥ LIMIAR_INCS_REINCIDENCIA` (3).
   - `ENTREGA_VALIDADA` se `qtd == 0` E `dias_pos ≥ MIN_DIAS_PARA_VALIDAR` (7).
   - `INCONCLUSIVO` no resto.
2. **Volumetria pré-resolução** via `fonte_inc.contar_incidentes_no_ci_periodo`
   (janela `JANELA_VOLUMETRIA_PRE_DIAS = 60` dias antes de `data_encerrado`).
   Retorna `{qtd, clientes_unicos, categorias}`.
3. **Δ chamados vinculados pré/pós (V3)** via `fonte_chamados.contar_chamados_vinculados`.
   Para cada lado da janela: levanta INCs do CI no período via
   `listar_incidentes_por_produto_servidor(produto, servidor, desde, ate)` e
   conta chamados onde `prb = prb_id` **OU** `inc IN (incs_ids)`.
   `JANELA_CHAMADOS_DELTA_DIAS = 14` dias em cada lado.
4. **PRBs novos pós-resolução** via `fonte_inc.listar_prbs_novos_no_ci_periodo`.
   Lista `numero` dos PRBs abertos no mesmo `(produto, servidor)` após
   `data_encerrado`, com `ignorar_prb_id` excluindo o PRB sendo validado.

**Defesa em camadas:** falha em um sinal não derruba o PRB — registra warning
e zera o campo. `fonte_chamados` é opcional: sem ela, validador ainda emite
veredicto + volumetria + PRBs novos, mas Δ chamados fica em 0.

**Entry-point separado:** `validar_entregas.py` — análogo ao `main.py` mas com
cadência default 6h (validações não mudam de minuto em minuto). Compartilha
persistência Postgres (mesma `motor_execucao`). Wrapper Windows:
`Motor-PRB-Validador.bat` para Task Scheduler.

#### `notifier.py` (~290 linhas)

**Papel:** comunicação push (Slack) + dashboard JSON.

**Slack:**
- `formatar_alerta_slack(prescricao, cluster)` — texto markdown com emojis
  combinados (urgência + ação: 🚨🆘 = crítico+abrir, ⚠️🔧 = alta+repriorizar).
- `formatar_alerta_saude_cliente(saude)` — emoji `:thermometer:` para Saúde.
- `formatar_alerta_reincidencia(validacao)` — emoji ⚠️🔁 para PRB com
  reincidência detectada pelo ValidadorEntrega.
- `enviar_slack(texto)` — preferência: `slack_sdk.WebClient.chat_postMessage`
  (Bot Token API, padrão locapredict). Fallback: HTTP POST webhook legado.
- `disparar_alertas_criticos(execucao)` — orquestra, rate limit 1s se Slack
  configurado. Inclui reincidências do ValidadorEntrega.

**Dashboard JSON:**
- `montar_payload_dashboard(execucao)` — JSON normalizado com separação
  clusters/incidentes (evita duplicação).
- `gravar_payload_dashboard(execucao)` — escreve `output/dashboard_state.json`
  com UTF-8, indent 2.

**Helper opcional:** `montar_dataframes_dashboard()` — DataFrames pandas para
consumidores Python (Streamlit, Jupyter).

#### `notifier_db.py` (~280 linhas)

**Papel:** persistência Postgres em `lwsa.motor_*` (histórico com TTL 30 dias).

- `persistir_execucao(execucao)` — transação atômica que INSERT em 5 tabelas.
  **Filtra singletons** (`qtd_incs < 2`) antes de gravar `motor_cluster` — só
  agrupamentos significativos entram. `total_clusters` em `motor_execucao`
  reflete o filtrado.
- `purgar_execucoes_antigas(dias=30)` — DELETE de execuções antigas.
- Helpers privados: `_insert_execucao`, `_insert_clusters`,
  `_insert_prescricoes`, `_insert_saude_clientes`, `_insert_validacoes_entrega`.

**Tabelas persistidas:**
- `motor_execucao` (cabeça do ciclo)
- `motor_cluster` (1 linha por cluster)
- `motor_prescricao` (1 linha por prescrição)
- `motor_saude_cliente` (1 linha por avaliação de cliente)
- `motor_validacao_entrega` (1 linha por PRB validado — **21 colunas**:
  11 base + 8 V2 (grupo_designado, data_abertura_prb, volumetria pré,
  Δ chamados) + 2 V3-extension (`qtd_prbs_novos_pos_resolucao`, `prbs_novos`).
  O significado de `chamados_pre`/`chamados_pos`/`delta_chamados_pct` mudou
  na V3: agora conta apenas chamados vinculados via `prb`/`inc`, não por
  produto)

**Defesa:** se Postgres falhar, motor continua (JSON e Slack tentam).

**Configurável:** `PERSISTIR_NO_BANCO=true/false`, `CLEANUP_TTL_HABILITADO`
(default false porque conta da Locaweb não tem DELETE — DBA cuida).

### Nível 4 — Orquestração

#### `scheduler.py` (~130 linhas)

**Papel:** pipeline de execução single-run do prisma preventivo.

**Função core:** `executar_ciclo(fonte_inc, fonte_chamados)` — executa pipeline
de 5 fases, com defesa em camadas. Retorna `ExecucaoMotor` sempre (mesmo em
falha).

**Sem loop interno** (removido em 2026-06-05). A cadência é externa: Windows
Task Scheduler dispara `Motor-PRB.bat` que chama `python main.py` uma vez.
Vantagem: se um ciclo crashar, o próximo ainda roda intacto — o Task Scheduler
faz o papel do supervisor.

**Métrica:** `duracao_ciclo_ms` populada antes da persistência Postgres (não
inclui Slack que é variável).

#### `main.py` (~65 linhas, entry point preventivo)

**Papel:** setup de logging + chamada do pipeline do prisma preventivo.

- `configurar_logging()` — handlers console (UTF-8 forçado) + arquivo
  rotacionado por dia (`motor-prb-{data}.log`).
- `main()` — chama `executar_ciclo()` uma vez e sai. Exit code 0/1.

**Agendado em PROD:** Windows Task Scheduler → cada **1 hora** (via
`Motor-PRB.bat`, em `\TarefasTrafego\` desde 2026-06-09). Cadência original
de 15 min foi revista no go-live do Painel Change Team — 1h é suficiente para
o volume atual da Locaweb e reduz custo de execução.

#### `validar_entregas.py` (~115 linhas, entry point retrospectivo)

**Papel:** entry-point do ValidadorEntrega — separado do `main.py` por design.
Em PROD desde 2026-06-09 também executa o **Painel Change Team** num 3º
bloco try/except (Defense in Depth, CON-012 LOCKED).

- `executar_validacao()` — cria `ExecucaoMotor`, popula 3 saídas:
  1. **V3.1 do ValidadorEntrega** via `gerar_validacoes_entrega(fonte_inc, fonte_chamados)` (try/except 1).
  2. **Painel Change Team** via `change_team.gerar_painel_change_team(...)` (try/except 2, condicional em `config.CHANGE_TEAM_HABILITADO`).
  3. **Persistência + Slack** das 2 saídas anteriores (try/except 3).
- `main()` — chama `executar_validacao()` uma vez e sai.

**Por que entry-point separado do `main.py`:**
- Cadência diferente (1h preventivo vs 6h retrospectivo) — não faz sentido bundlear no mesmo loop.
- Escopo distinto (INCs abertas hoje vs PRBs encerrados nos últimos 14d).
- Logs separados (`validador-entrega-{data}.log`) para facilitar auditoria.

**Agendado em PROD:** Windows Task Scheduler → cada **6 horas** (via
`Motor-PRB-Validador.bat`, em `\TarefasTrafego\` desde 2026-06-09).

#### `change_team.py` (~180 linhas) — Painel Change Team

**Papel:** materializa snapshot dos ~84 PRBs da força-tarefa **Change Team** numa
tabela Postgres `lwsa.motor_change_team_painel`, atualizada a cada 6h via o
mesmo entry-point do ValidadorEntrega (`validar_entregas.py`, 3º bloco
try/except). Phase 1 do GSD entregue 2026-06-05; go-live PROD 2026-06-09.

**Estratégia:**

1. **Lê a master** `lwsa.motor_change_team` com `WHERE ativo = true` (soft
   delete via `ativo` + `removido_em`).
2. **Cruza com SNow espelho** via `extractor.listar_prbs_por_numero(numeros)`
   — query **sem janela temporal** (D-03), captura PRBs antigos que o
   ValidadorEntrega normal (14d) jamais pegaria.
3. **Para PRBs resolvidos**, reusa `validador_entrega._avaliar_prb` —
   CON-012 LOCKED preserva V3.1 do validador. Falha do Change Team NÃO
   afeta `motor_validacao_entrega`.
4. **Persiste TRUNCATE+INSERT atômico** (D-04) via
   `notifier_db.persistir_painel_change_team`.

**Toggle:** env var `CHANGE_TEAM_HABILITADO` (default `"true"`). Set
`"false"` para desligar sem deploy.

**Pré-requisito de banco** (aprendido no go-live):
- Owner das 2 tabelas deve ser a conta do motor (`automatizacoes` na Locaweb)
  via `ALTER TABLE ... OWNER TO automatizacoes` — `TRUNCATE+RESTART IDENTITY`
  exige owner da sequência.
- PRBs históricos precisam estar replicados em `lwsa.service_now_problems`
  (rodar `projetos/problemas/backfill.py` se faltar).

**Consumo:** chart "PRB Change Team" no Superset corporativo (D-07).
Documentação operacional completa em [DASHBOARD_CHANGE_TEAM.md](DASHBOARD_CHANGE_TEAM.md).

---

## 5. Os 7 princípios transversais

Padrões que apareceram repetidamente ao longo do código. Aplicar consistentemente
mantém o motor coeso.

### Princípio 1 — Defesa em camadas (`Defense in Depth`)

**Onde aparece:** try/except em 4 níveis:

```
scheduler.executar_ciclo
├── try/except em cada fase            ← Camada 1
├── _job (wrapper)                     ← Camada 2
│   └── try/except envolvente          ← Camada 3
└── prescrever_lote
    └── try/except por cluster         ← Camada 4 (interna a rules_engine)
```

**Princípio:** **um único bug não derruba o motor**. Falhas contidas no menor
escopo possível.

**Trade-off:** mais código (~30% das linhas são tratamento de erro), mais difícil
debugar **exatamente onde quebrou** sem ler logs. **Aceito** porque uptime é
prioridade.

**Quando NÃO aplicar:** código de lógica pura interna (`_avaliar_p1`, etc.). Lá,
exceções **devem** propagar para defesa externa capturar.

### Princípio 2 — Single Responsibility por módulo

| Módulo | Responsabilidade única |
|---|---|
| `extractor.py` | Trazer dados de fora para Python |
| `analyzer.py` | Clusterizar + calcular scores |
| `rules_engine.py` | Aplicar matriz P1-P5 (prisma preventivo) |
| `validador_entrega.py` | Avaliar PRBs entregues pelo Change Team (prisma retrospectivo) |
| `change_team.py` | Materializar snapshot do Painel Change Team (Phase 1, 2026-06-05) |
| `customer_monitor.py` | Avaliar saúde de clientes |
| `notifier.py` | Comunicação push (Slack, JSON) |
| `notifier_db.py` | Persistência Postgres |
| `scheduler.py` | Orquestrar pipeline single-run |
| `config.py` | Decisões de produto |
| `db.py` | Conexão SQL |
| `time_utils.py` | Conversão de fuso |
| `models.py` | Estruturas de dados |

**Princípio:** cada módulo faz **uma coisa** e faz bem. Não há "módulo que faz
tudo".

**Sinal de violação:** se você precisar tocar 5 arquivos para adicionar uma
feature, há acoplamento errado. Adições típicas tocam 1-2 arquivos.

### Princípio 3 — Configurabilidade externa

**Toda decisão de produto vive em `config.py`.** Código nunca tem "número mágico":

```python
# ANTI-PADRÃO:
if qtd >= 5:  # ← por que 5? Quem decidiu?
    ...

# PADRÃO:
if qtd >= config.LIMIAR_P2_INCS_SEM_CONTORNO:  # ← rastreável
    ...
```

**Vantagem:** mudanças de produto (ajuste de threshold, adição de organização)
**não exigem código novo**.

**Indicador:** se você precisa de PR para ajustar `5` → `7`, o motor está mal
feito. Hoje: ajuste é env var ou 1 linha em config.

### Princípio 4 — UTC interno, fronteiras locais

```python
# Interno (todo o motor):
inicio = time_utils.agora_utc()  # UTC tz-aware

# Fronteira SQL:
corte_str = time_utils.utc_para_string_banco(corte_utc)  # → BRT naive

# Fronteira JSON:
"data": inc.abertura.isoformat()  # → "2026-05-26T17:30:00+00:00"

# Exceção deliberada:
arquivo_log = f"motor-prb-{datetime.now().strftime('%Y-%m-%d')}.log"  # ← BRT local
```

**Princípio:** **internamente UTC**, **converte na fronteira**. Comparações de
data sempre corretas independente do servidor.

**Vimos bug real causado por isso** durante o desenvolvimento (Postgres BRT vs
Python naive). Lição aplicada de forma consistente.

### Princípio 5 — Justificativa auditável em decisões

**Toda decisão automatizada explica-se em texto livre:**

```python
# rules_engine acumula justificativas:
justificativas: List[str] = []
if qtd_sem >= 5:
    justificativas.append(f"{qtd_sem} INCs sem contorno (limiar P2: 5).")

# notifier renderiza no Slack como bullets:
"*Justificativas:*\n    • ...\n    • ...\n"
```

**Princípio:** motor não é caixa-preta. Coordenador olhando alerta entende
**por que** o motor decidiu, não só **o que** decidiu.

**Vimos o valor disso quando o bug do "ra " foi descoberto** — justificativa
explícita "*Reclame Aqui sem solução de contorno...*" em cluster que NÃO
mencionava RA acendeu alerta vermelho.

### Princípio 6 — `ExecucaoMotor` como agregador único

**Um objeto único** carrega todo o estado de um ciclo. Não há "passar 5 listas
separadas entre funções":

```python
# scheduler.executar_ciclo:
execucao = ExecucaoMotor(timestamp=...)
execucao.clusters = analyzer.analisar(...)
execucao.prescricoes = rules_engine.prescrever_lote(...)
execucao.saude_clientes = customer_monitor.gerar_saude_clientes(...)
notifier.gravar_payload_dashboard(execucao)
notifier_db.persistir_execucao(execucao)
notifier.disparar_alertas_criticos(execucao)
```

**Princípio:** clareza de API. Função `notifier.X(execucao)` sempre recebe
`execucao`. Sem ambiguidade.

### Princípio 7 — Degradação suave (`graceful degradation`)

**Funcionalidade reduzida é melhor que funcionalidade ausente.**

```python
# scheduler: hierarquia de criticidade entre fontes
try:
    incidentes = ...
except:
    return execucao  # aborta (crítico)
try:
    chamados = ...
except:
    chamados = []  # segue sem (não-crítico)

# notifier: webhook sem config
if not cfg.configurado:
    log.info("[Slack desabilitado/sem webhook] ...")
    return False
```

**Princípio:** motor **sempre funciona**, mesmo em ambiente quebrado.

**Indicador:** operador percebe degradação **via warnings**, não via "motor não
fez nada".

---

## 6. Decisões importantes (e por quê)

Decisões arquiteturais que vale registrar com a justificativa de cada uma.

### Por que Windows Task Scheduler externo em vez de loop interno

A primeira versão usava a lib `schedule` (Python) num loop interno em
`scheduler.py:rodar_loop` com `signal` handlers para SIGTERM/SIGINT. **Removido
em 2026-06-05** em favor de execução single-run (`python main.py` roda 1 ciclo
e sai com exit code 0/1; cadência delegada ao Windows Task Scheduler).

| Opção | Por que descartada/escolhida |
|---|---|
| **APScheduler** | Overkill. ~20 deps transitivas. Persistência que não precisamos. |
| **Celery** | Distributed task queue. Requer broker (Redis/RabbitMQ). Complexidade desproporcional. |
| **asyncio** | Motor é síncrono. Trocar quebraria psycopg2 (não-async). |
| **`schedule`** | Funcionou no MVP, mas exigia processo Python sempre vivo + signal handling — se ciclo crashar de modo não-recuperável, o processo morria e ninguém percebia. |
| **Windows Task Scheduler externo** ✅ | Zero código de loop/signal. Crash de um ciclo não afeta o próximo. Retry/timeout configurável na UI. Supervisor de fato. |

**Vantagem operacional do Task Scheduler externo:** o supervisor (Windows)
sabe restartar, sabe matar processo travado por timeout, e o log de execução
é auditável via aba **Histórico** sem precisar parsear logs Python.

### Por que TF-IDF + DBSCAN em vez de sentence-transformers

Comparação com o projeto irmão (locapredict) que usa sentence-transformers:

| Aspecto | TF-IDF + DBSCAN (motor) | sentence-transformers (locapredict) |
|---|---|---|
| Tamanho do modelo | 0 MB (lib) | ~500 MB (modelo) |
| Inicialização | Instantânea | ~5s |
| Qualidade semântica | Boa para textos técnicos curtos | Excelente (entende sinônimos) |
| Dependências | `scikit-learn` | `sentence-transformers`, `torch` |

**Motor escolheu TF-IDF** porque INCs são textos curtos e técnicos com vocabulário
consistente. Investimento em embeddings profundos não traz retorno proporcional
ao custo.

**Locapredict escolheu sentence-transformers** porque análise é semanal (não
exige startup rápido) e busca padrões mais sutis.

### Por que stateless (não persiste estado entre ciclos)

**Estado entre ciclos resolveria:**
- Detecção de "escalada gradual" (4 P3 ontem → 5 hoje).
- Anti alert-fatigue para PRBs (não repetir mesma mensagem).
- Tendência por cliente.

**Mas exigiria:**
- Persistência adicional (já temos no Postgres com histórico, mas exige queries
  comparativas).
- Lógica de "primeira vez vs. continuação".
- Testes mais complexos.

**Decisão MVP:** começar stateless. **Análise temporal** se faz via SQL no
histórico persistido (subtópico de evolução).

**Workaround para alert-fatigue:** critério de recência (`_tem_inc_recente(7
dias)`) para Saúde do Cliente. Para PRBs, ainda não temos solução — limitação
documentada.

### Por que Postgres `json` em vez de `jsonb`

**Versão do Postgres da Locaweb:** 9.2 ou 9.3. **`jsonb` só existe em 9.4+.**

Decisão: usar `json` (existe desde 9.2) para compatibilidade.

**Impacto operacional:** zero. Motor apenas serializa Python → JSON. Sem queries
internas com operadores específicos de `jsonb`.

**Migração futura:** quando infra atualizar para 9.4+, ALTER TABLE para `jsonb`
em 6 colunas + trocar `::json` por `::jsonb` em 5 lugares no `notifier_db.py`.
Documentado no rodapé de `sql/motor_tables.sql`.

### Por que motor lê do data warehouse (não da API do SNow)

**Alternativas consideradas:**

| Fonte | Por que descartada/escolhida |
|---|---|
| **ServiceNow REST API** | Rate limit. Autenticação OAuth complexa. Latência variável. Acoplamento direto. |
| **Webhook do SNow** | Push em vez de pull. Mais complexo. Requer endpoint HTTP no motor. |
| **Data warehouse Postgres** ✅ | ETL já existe (locapredict usa). Latência previsível. Junção com outras tabelas. Backups inclusos. |

**Princípio:** **lazy data** — usar o que já existe antes de criar nova
integração.

### Por que registry declarativo para chamados (Abordagem 2)

Considerei 3 abordagens para suportar Locaweb + Kinghost:

1. **If/else hardcoded em cada query.**
2. **Strategy pattern com classes Estratégia*.**
3. **Registry declarativo** (`dict` rico com colunas/joins por organização). ✅

**Abordagem 2 escolhida** porque:
- Adicionar organização nova = **editar dict**, zero código novo.
- Diferenças entre orgs ficam explícitas num único lugar.
- Validação de schema no startup.
- Strategy pattern seria boilerplate para 2 orgs.

**Trade-off:** construção dinâmica de SQL exige cuidado com SQL injection.
Mitigação: schema/tabela/colunas SÓ vêm do config (whitelist), valores via
`%s` (psycopg2 escapa).

### Por que JSON em paralelo a Postgres

Quando migramos de "JSON only" para Postgres, optamos por **manter JSON em
paralelo** (Opção 1 — histórico Postgres com TTL + JSON sempre). Razões:

1. **Custo zero:** código JSON já existe e funciona.
2. **Rede de segurança:** se Postgres cair, JSON ainda preserva o estado atual.
3. **Front-end simples:** scripts ad-hoc, Streamlit, HTML estático podem ler
   JSON sem configurar SQL.
4. **Debug humano:** abrir JSON num editor é mais rápido que conectar DBeaver.

**Quando deprecar JSON:** após validação de que ninguém o usa. Hoje, mantém-se.

### Por que defesa em camadas é redundante (e por quê isso é bom)

**Exemplo de redundância:**

- `prescrever_lote` tem try/except por cluster (camada interna).
- `scheduler.executar_ciclo` tem try/except em volta de `prescrever_lote`
  (camada externa).

A camada externa "nunca deveria ser acionada" porque a interna já captura. Por
que mantemos?

**Defense in depth:** se houver bug **em `prescrever_lote` em si** (não num
cluster específico), camada externa salva o motor. Custo: 4 linhas extras.
Benefício: catastrophe avoidance.

**Princípio:** redundância defensiva em sistemas críticos paga. Em código de
algoritmo puro, não vale.

---

## 7. Pontos de extensão

Onde o motor está **preparado para crescer** sem refactor.

### Configurações ajustáveis sem código

| O que ajustar | Onde |
|---|---|
| Threshold de qualquer regra P1-P5 | `config.LIMIAR_*` |
| Pesos do score de criticidade | `config.PESO_*` |
| Pesos do score de ineficiência | `config.PESO_INEFICIENCIA_*` |
| Pesos de severidade por prioridade | `config.PESO_PRIORIDADE_SEVERIDADE` |
| Janelas temporais | `config.JANELA_*` |
| Termos heurísticos (Reclame Aqui, contratação, etc.) | `config.TERMOS_*` |
| Organizações de chamados | `config.TABELAS_CHAMADOS_POR_ORGANIZACAO` |
| Status PRB ativos | `config.STATUS_PRB_ATIVOS` |
| TTL do banco | `config.JANELA_TTL_BANCO_DIAS` + env `CLEANUP_TTL_HABILITADO` |
| Timezone do banco | `config.TIMEZONE_BANCO` |

### Pontos com ABCs (substituibilidade)

| ABC | Para substituir | Como |
|---|---|---|
| `FonteIncidentes` | ServiceNow por Jira/outro | Nova classe + factory |
| `FonteChamados` | Adicionar nova org | Editar registry + (opcional) implementar lógica específica |

### Pontos extensíveis sem ABCs

| Extensão | Onde |
|---|---|
| Nova ação prescrita (além de ABRIR/REPRIORIZAR/MONITORAR/NENHUMA) | `_determinar_acao` em `rules_engine.py` |
| Nova saída (e-mail, Teams, webhook) | Novo módulo `notifier_X.py` + chamada no scheduler |
| Novo nível de prioridade (P0) | `config.MAPA_URGENCIA_PRIORIDADE` + nova função `_avaliar_p0` + emoji |
| Novo cenário no mock | Adicionar entrada em `_GeradorMock.CENARIOS` |
| Novo campo em Incidente/PRB | `models.py` + parser no `extractor.py` |

### Exemplo concreto — adicionar organização "Hostgator"

```python
# config.py — UMA mudança
TABELAS_CHAMADOS_POR_ORGANIZACAO = {
    "Locaweb": {...},
    "Kinghost": {...},
    "Hostgator": {                        # ← NOVA
        "schema": "hostgator",
        "tabela": "chamados",
        "alias": None,
        "join": None,
        "colunas": {
            "chamado_id": "idchamado",
            "login_cliente": "logincliente",
            "data": "datacriacao",
            "assunto": "assunto",
            "origem": "origem",
            "produto": "fila",
            "qtd_interacoes_cliente": "qtd_interacoes",
        },
    },
}
```

**Zero código novo.** Restart motor → próximo ciclo já consulta Hostgator.

### Exemplo concreto — adicionar saída por e-mail

```python
# notifier_email.py (NOVO)
def enviar_resumo_diario(execucao: ExecucaoMotor) -> bool:
    """Envia resumo via SMTP."""
    import smtplib
    ...

# scheduler.py — adicionar 5d
try:
    notifier_email.enviar_resumo_diario(execucao)
except Exception as exc:
    log.exception("Falha ao enviar e-mail: %s", exc)
    execucao.erros.append(f"email: {exc}")
```

~50 linhas de código novo + 6 linhas no scheduler. Mesma estrutura defensiva
das outras saídas.

---

## 8. Limitações conscientes do MVP

Itens **deliberadamente fora do MVP**. Cada um com mitigação documentada e
caminho para o futuro. Detalhes em [../GLOSSARIO.md](../GLOSSARIO.md) seção
"Limitações reais".

### Resumo executivo

| Categoria | Status | Mitigação atual |
|---|---|---|
| Motor stateless | Aceito | Persistência histórica em Postgres permite análise temporal via SQL |
| Repetição de alertas Slack PRB | Aceito | Slack pode silenciar similares manualmente |
| Sem retry/backoff | Aceito | Próximo ciclo (1h em PROD) tenta de novo |
| Sem health check HTTP | Aceito | Monitorar timestamp do JSON ou MAX(timestamp_utc) no Postgres |
| Limiar de Saúde único por porte | Aceito | Pendente dado de "porte do cliente" no banco |
| Sem ML aprendendo com feedback | Decidido | Regras determinísticas auditáveis vencem ML opaco no MVP |
| Sem integração bidirecional com SNow | Decidido | Motor sugere, humano decide |
| Sem microservices | Decidido | Monolito modular adequado ao tamanho |

### Limitações ↔ Riscos operacionais

| Limitação | Risco | Probabilidade |
|---|---|---|
| Repetição Slack PRB | Alert fatigue → time ignora canal | **Alta** em produção 24/7 |
| Sem retry | Falha transitória = ciclo perdido | Baixa (próximo ciclo tenta) |
| Sem health check | Motor pode estar morto sem alguém perceber | Média |
| Cleanup TTL desabilitado | Banco cresce indefinidamente | Baixa (~800k rows em 1 ano, OK) |
| Limiar único por porte | Falsos positivos para clientes enterprise | Média |

### Quando revisitar

**Revisitar limitações em 2 marcos:**
1. **Após 3 meses em produção:** com dados reais, validar se as mitigações
   manuais (silenciar Slack, DBA cuida do cleanup) são sustentáveis.
2. **Após 1 ano:** considerar evoluções que dependem de feedback de uso real
   (limiar por porte, ML, integração bidirecional).

---

## 9. Como contribuir sem quebrar

Diretrizes para devs que vão evoluir o motor.

### Antes de mexer

1. **Leia este documento + GLOSSARIO.md.** Entenda os 7 princípios.
2. **Rode `python -m pytest tests/`.** Confirme que tudo passa antes da
   mudança. Garante baseline.
3. **Rode `python main.py` com `USAR_MOCKS=true`.** Veja saída atual.

### Durante a mudança

1. **Identifique o nível do módulo que vai tocar** (1-4).
2. **Não importe para cima** (config.py não pode importar extractor.py).
3. **Adicione testes** para o que você mudou (`tests/test_*.py`).
4. **Configurabilidade > hardcode:** se introduziu um número, ele vai para
   `config.py`.
5. **Defensiva em I/O:** qualquer chamada externa (banco, HTTP, arquivo) deve
   ter try/except apropriado.

### Antes de fazer commit

1. **Rode `python -m pytest tests/ -v`.** Todos os 116 testes devem passar.
2. **Rode `python main.py`.** Pipeline completo sem erros.
3. **Verifique o JSON de output** (`output/dashboard_state.json`). Sanity check.
4. **Se mudou regra de negócio:** atualize [REGRAS.md](REGRAS.md).
5. **Se mudou comportamento operacional:** atualize [MANUAL.md](MANUAL.md).
6. **Se mudou arquitetura:** atualize este documento.

### Padrões de código

- **PT-BR:** variáveis, funções, comentários, logs em português.
- **Termos técnicos universais** preservados em inglês (TF-IDF, DBSCAN, UTC).
- **snake_case** para funções e variáveis.
- **PascalCase** para classes.
- **UPPER_SNAKE_CASE** para constantes do `config.py`.
- **Docstrings** explicam o "por quê", não o "como".

### Quando criar novo módulo vs. estender um existente

**Criar novo módulo se:**
- Nova responsabilidade conceitual (nova "saída", nova "fonte").
- Mais de ~100 linhas de código novo coeso.
- Pode ser desenvolvido em isolamento.

**Estender módulo existente se:**
- Refino de comportamento já existente.
- Menos de ~50 linhas de código novo.
- Não introduz nova dimensão de complexidade.

### Pull request checklist (futuro)

- [ ] Testes adicionados ou ajustados.
- [ ] Todos os testes passam (`pytest`).
- [ ] `python main.py` (single-run) funciona sem erros.
- [ ] Configurabilidade respeitada (sem números mágicos).
- [ ] Documentação atualizada (ARQUITETURA / MANUAL / REGRAS conforme escopo).
- [ ] Justificativa de design no commit message.

---

## Referências cruzadas

- **[MANUAL.md](MANUAL.md):** como usar o motor (operadores).
- **[REGRAS.md](REGRAS.md):** matriz oficial P1-P5 e critérios de negócio.
- **[SAUDE_DO_CLIENTE.md](SAUDE_DO_CLIENTE.md):** processo completo do prisma de Saúde do Cliente.
- **[VALIDADOR_ENTREGA.md](VALIDADOR_ENTREGA.md):** processo completo do prisma retrospectivo (V3.1).
- **[DASHBOARD_CHANGE_TEAM.md](DASHBOARD_CHANGE_TEAM.md):** guia operacional do Painel Change Team (Phase 1 GSD, PROD desde 2026-06-09).
- **[../GLOSSARIO.md](../GLOSSARIO.md):** termos técnicos.
- **`sql/motor_tables.sql`:** DDL das tabelas de persistência.
- **`config.py`:** todas as decisões de produto centralizadas.
- **`tests/`:** suíte de testes unitários.

---

_Documento mantido sob responsabilidade dos contribuidores do motor. Última
atualização: 2026-06-09 (Phase 1 Painel Change Team em PROD + refactor
single-run + cadências revisadas para 1h motor / 6h validador)._