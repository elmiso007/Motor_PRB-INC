# Decisions (Synthesized)

> Fonte: extraidas implicitamente de docs/ARQUITETURA.md e docs/MANUAL.md.
> Nenhum ADR formal existe no repositorio — todas as decisoes foram derivadas
> da secao "6. Decisoes importantes (e por que)" da ARQUITETURA.md.
>
> Status convencao:
> - `Aceita (implicita)` — decisao tomada e implementada, sem ADR formal mas
>   documentada em prosa.
> - `locked: false` — nenhuma ADR explicita com cabecalho "Status: Locked" foi
>   classificada, portanto nenhuma decisao aqui e LOCKED. Em caso de duvida,
>   tratar como override-able pelo proximo ADR.

---

## DEC-001 — Clusterizacao via TF-IDF + DBSCAN (scikit-learn)

- **source:** docs/ARQUITETURA.md (secao 6 — "Por que TF-IDF + DBSCAN em vez de sentence-transformers")
- **status:** Aceita (implicita)
- **locked:** false
- **scope:** algoritmo de agrupamento semantico de INCs
- **decisao:** Motor usa `TfidfVectorizer(max_features=5000, ngram_range=(1,2))`
  + `DBSCAN(eps=0.55, min_samples=2, metric='cosine')`. Alternativa
  sentence-transformers descartada (custo ~500 MB de modelo + ~5s de startup
  nao compensa para textos tecnicos curtos).
- **consequencia:** dependencia obrigatoria de `scikit-learn`. Fallback Jaccard
  se sklearn indisponivel. Locapredict (projeto irmao) usa abordagem oposta
  (sentence-transformers) por ciclo semanal vs. 15min do motor.

## DEC-002 — Persistencia em PostgreSQL (`lwsa.motor_*`) com schema `json` (nao `jsonb`)

- **source:** docs/ARQUITETURA.md (secao 6 — "Por que Postgres `json` em vez de `jsonb`")
- **status:** Aceita (implicita)
- **locked:** false
- **scope:** persistencia historica do motor
- **decisao:** Persistir cada ciclo em 5 tabelas Postgres (`motor_execucao`,
  `motor_cluster`, `motor_prescricao`, `motor_saude_cliente`,
  `motor_validacao_entrega`). Schema usa tipo `json` (nao `jsonb`) por
  compatibilidade com Postgres 9.2/9.3 da Locaweb.
- **consequencia:** migracao futura para `jsonb` exige ALTER TABLE em 6 colunas
  + ajuste em 5 lugares de `notifier_db.py`. Documentado em
  `sql/motor_tables.sql`.

## DEC-003 — Leitura do Data Warehouse, nao da API ServiceNow

- **source:** docs/ARQUITETURA.md (secao 6 — "Por que motor le do data warehouse")
- **status:** Aceita (implicita)
- **locked:** false
- **scope:** fonte de dados de INCs/PRBs
- **decisao:** Motor consulta `lwsa.service_now_incidentes`,
  `lwsa.service_now_problemas` e tabelas de chamados (`dynamics.chamados`,
  `kinghost.chamados`) via SQL no Postgres compartilhado. ETL upstream cuida
  da replicacao SNow → DW.
- **consequencia:** sem acoplamento direto com SNow REST API. Latencia
  previsivel. Limitacao: campos nao replicados pelo ETL (ex.: `breach_time`)
  geram heuristicas em vez de logica exata.

## DEC-004 — Cadencia externa via Windows Task Scheduler (sem loop interno)

- **source:** docs/ARQUITETURA.md (modulos `scheduler.py` / `main.py`), docs/MANUAL.md
  secao 2.1
- **status:** Aceita (implicita) — refatoracao explicita em 2026-06-05
- **locked:** false
- **scope:** orquestracao temporal do motor preventivo
- **decisao:** Aplicacao roda como single-run (`python main.py` chama
  `executar_ciclo()` uma vez e termina). Windows Task Scheduler dispara
  `Motor-PRB.bat` a cada 15 min. Loop interno foi removido em 2026-06-05.
- **consequencia:** Task Scheduler atua como supervisor — crash em um ciclo
  nao afeta o proximo. Exit code 0/1 sinaliza sucesso/falha.
  Biblioteca `schedule` descartada (era usada antes do refactor).

## DEC-005 — Cadencia separada do ValidadorEntrega (6h, entry-point proprio)

- **source:** docs/ARQUITETURA.md (modulo `validar_entregas.py`), docs/VALIDADOR_ENTREGA.md
- **status:** Aceita (implicita)
- **locked:** false
- **scope:** orquestracao do prisma retrospectivo
- **decisao:** `validar_entregas.py` e entry-point separado de `main.py`,
  agendado em cadencia default 6h via `Motor-PRB-Validador.bat`. Persiste na
  mesma `motor_execucao` mas com logs proprios (`validador-entrega-{data}.log`).
- **consequencia:** validacoes nao competem com o ciclo de 15 min do preventivo.

## DEC-006 — Arquitetura em 4 niveis com regra de imports unidirecional

- **source:** docs/ARQUITETURA.md (secao 2 — "Arquitetura em camadas")
- **status:** Aceita (implicita)
- **locked:** false
- **scope:** estrutura de codigo Python
- **decisao:** Niveis 1=Fundacao (`config`, `models`), 2=Utilitarios
  (`time_utils`, `db`), 3=Dominio (extractor/analyzer/rules_engine/customer_monitor/notifier),
  4=Orquestracao (`scheduler`, `main`). Imports so vao "para baixo".
- **consequencia:** sem ciclos. Mudanca em config nao depende de modulo de
  dominio. Verificavel via `grep "^import\|^from"`.

## DEC-007 — Motor stateless entre ciclos (analise temporal via SQL no historico)

- **source:** docs/ARQUITETURA.md (secao 6 — "Por que stateless")
- **status:** Aceita (implicita, decidida para MVP)
- **locked:** false
- **scope:** modelo de estado do motor
- **decisao:** Cada ciclo nao carrega estado do ciclo anterior. Analise
  temporal (escalada gradual, comparacao com historico) e feita via SQL no
  `lwsa.motor_*` quando necessario.
- **consequencia:** Sem deteccao automatica de tendencia "4 P3 ontem → 5 hoje".
  Sem anti alert-fatigue para PRBs (so para Saude do Cliente, via criterio
  de recencia de 7 dias). Documentado como limitacao consciente.

## DEC-008 — JSON em paralelo a Postgres (rede de seguranca)

- **source:** docs/ARQUITETURA.md (secao 6 — "Por que JSON em paralelo a Postgres")
- **status:** Aceita (implicita)
- **locked:** false
- **scope:** outputs do motor
- **decisao:** Cada ciclo escreve `output/dashboard_state.json` SEMPRE, alem de
  persistir no Postgres. Ordem das saidas: JSON (~10ms) → Postgres (~50-100ms)
  → Slack (~5s). Princpio: probabilidade de sucesso decrescente.
- **consequencia:** se Postgres cair, JSON ainda preserva estado atual.
  Deprecar JSON apenas apos confirmacao de que ninguem o consome.

## DEC-009 — Slack via slack_sdk WebClient (com fallback HTTP webhook)

- **source:** docs/ARQUITETURA.md (modulo `notifier.py`)
- **status:** Aceita (implicita)
- **locked:** false
- **scope:** integracao Slack
- **decisao:** Preferencia por `slack_sdk.WebClient.chat_postMessage` (Bot Token API,
  padrao do projeto irmao locapredict). Fallback para HTTP POST em webhook
  legado. Rate limit de 1s entre envios.
- **consequencia:** filtros aplicados: so envia para `prescricoes.urgencia=CRITICA`
  + `saude.alerta_recorrencia_alta` + reincidencias do ValidadorEntrega.

## DEC-010 — Defesa em camadas (Defense in Depth) com try/except em 4 niveis

- **source:** docs/ARQUITETURA.md (secao 5 — Principio 1, secao 6 — "redundancia")
- **status:** Aceita (implicita) — principio transversal
- **locked:** false
- **scope:** tratamento de erros em todo o pipeline
- **decisao:** Pipeline tem try/except em 4 camadas: por fase em
  `executar_ciclo`, no `_job` wrapper, envolvendo `prescrever_lote`, e por
  cluster dentro de `prescrever_lote`. Redundancia deliberada.
- **consequencia:** ~30% das linhas sao tratamento de erro. Trade-off aceito
  porque uptime e prioridade.

## DEC-011 — UTC interno, BRT na fronteira

- **source:** docs/ARQUITETURA.md (secao 5 — Principio 4)
- **status:** Aceita (implicita)
- **locked:** false
- **scope:** convencao de timestamps em todo o motor
- **decisao:** Internamente, tudo UTC tz-aware via `time_utils.agora_utc()`.
  Conversao para BRT naive so na fronteira SQL (`utc_para_string_banco`) e
  log filename. JSON output usa ISO 8601 com offset.
- **consequencia:** comparacoes/ordenacoes seguras independente do servidor.

## DEC-012 — Configurabilidade externa total (zero numero magico no codigo)

- **source:** docs/ARQUITETURA.md (secao 5 — Principio 3)
- **status:** Aceita (implicita)
- **locked:** false
- **scope:** thresholds, janelas, termos heuristicos
- **decisao:** Toda decisao de produto vive em `config.py`. Codigo nunca tem
  numero literal — sempre `config.LIMIAR_*` ou similar.
- **consequencia:** ajustes operacionais (mudar limiar de 5 para 7) nao
  requerem refactor — apenas edicao em config + ajuste de testes.

## DEC-013 — Registry declarativo para multi-tenancy de chamados

- **source:** docs/ARQUITETURA.md (secao 6 — "Por que registry declarativo")
- **status:** Aceita (implicita)
- **locked:** false
- **scope:** suporte a multiplas organizacoes (Locaweb, KingHost)
- **decisao:** `config.TABELAS_CHAMADOS_POR_ORGANIZACAO` e um dict declarativo
  rico (schema/tabela/colunas/joins por org). Strategy pattern e if/else
  hardcoded foram descartados.
- **consequencia:** adicionar nova organizacao (ex.: Hostgator) = editar dict,
  zero codigo novo. SQL construido dinamicamente exige cuidado: whitelist
  para identificadores, `%s` para valores.

## DEC-014 — Filtros default focados em Locaweb

- **source:** docs/REGRAS.md secao 13, config.py
- **status:** Aceita (implicita) — operacional vigente
- **locked:** false
- **scope:** escopo de dados processados
- **decisao:** `ORGANIZACOES_ATIVAS = ("Locaweb",)` por default.
  `LOGIN_CLIENTE_PADROES_EXCLUIDOS = ("kinghost",)` filtra INCs marcadas como
  Locaweb mas com URL de KingHost no `login_cliente`.
- **consequencia:** KingHost so processada quando explicitamente adicionada
  a tupla. Filtro de padroes de login so atua em
  `contar_clientes_com_inc_recente`.

## DEC-015 — Singletons (qtd_incs=1) nao sao persistidos em `motor_cluster`

- **source:** docs/REGRAS.md secao 12 ("Filtragem de singletons na persistencia")
- **status:** Aceita (implicita)
- **locked:** false
- **scope:** persistencia de clusters
- **decisao:** Cluster com 1 unica INC nao grava em `motor_cluster`. Continua
  em memoria para alimentar Saude do Cliente e dashboard JSON.
- **consequencia:** tabela `motor_cluster` ~70% mais limpa. `total_clusters`
  em `motor_execucao` reflete o filtrado.

## DEC-016 — Saude do Cliente: estrategia "bulk + slim" em 2 fases

- **source:** docs/ARQUITETURA.md modulo `customer_monitor.py`, docs/SAUDE_DO_CLIENTE.md
- **status:** Aceita (implicita)
- **locked:** false
- **scope:** desempenho da fase Saude do Cliente
- **decisao:** Fase 1: SQL agregado (GROUP BY login_canonico) com filtro
  `tipo_usuario='Nominal'`, janela 30d, normalizacao via
  `sql_normalizar_login_cliente`. Fase 2: bulk slim — 1 SELECT INCs +
  1 SELECT chamados Locaweb + 1 SELECT chamados KingHost.
- **consequencia:** ciclo Saude do Cliente caiu de ~80min (com N×2 queries
  seriais) para ~30-45s. Exige indices `idx_sni_data_abertura`,
  `idx_dyn_chamados_datacriacao`, `idx_kh_chamados_datacriacao`,
  `idx_sni_data_tipo` no DBA.

## DEC-017 — Login canonico unificado via expressao SQL portada do locapredict

- **source:** docs/REGRAS.md secao 9 e 12, docs/ARQUITETURA.md modulo extractor
- **status:** Aceita (implicita)
- **locked:** false
- **scope:** normalizacao de `login_cliente`
- **decisao:** `sql_normalizar_login_cliente(coluna)` e expressao Postgres que
  unifica 5 formatos: `username`, `username (Cod. NNN)`, URL com `ficha=NNN`,
  digitos puros, texto puro. Equivalente Python `normalizar_login_cliente`
  usado no mock.
- **consequencia:** GROUP BY estavel para Saude do Cliente. Login efetivo
  preferido vem de `dynamics.chamados.logincliente` quando ha JOIN.

## DEC-018 — ValidadorEntrega V3.1: 4 sinais por PRB

- **source:** docs/VALIDADOR_ENTREGA.md, docs/REGRAS.md secao 14
- **status:** Aceita (implicita) — atual em producao desde 2026-06-02
- **locked:** false
- **scope:** prisma retrospectivo de PRBs entregues
- **decisao:** Cada PRB validado carrega: (1) veredicto (REINCIDENCIA |
  ENTREGA_VALIDADA | INCONCLUSIVO), (2) volumetria pre-resolucao (janela 60d),
  (3) delta chamados vinculados pre/pos (janela 14d cada lado, match
  `chamados.prb = prb_id` OR `inc IN (...)`), (4) PRBs novos pos-resolucao no
  mesmo (produto, servidor).
- **consequencia:** tabela `motor_validacao_entrega` tem 21 colunas. V2 match
  por produto foi deprecado (era ruidoso); V3 match vinculado e mais preciso
  mesmo com menor cobertura.

## DEC-019 — Stop-words customizadas PT-BR sem acentos

- **source:** docs/ARQUITETURA.md modulo `analyzer.py`
- **status:** Aceita (implicita)
- **locked:** false
- **scope:** pre-processamento de texto
- **decisao:** 60 stop-words PT-BR mantidas sem acentos para casar com texto
  ja normalizado via NFKD + lowercase + remocao de pontuacao.
- **consequencia:** TF-IDF mais limpo. Termos de regras P1-P5 tambem sao
  comparados em forma normalizada via word boundary regex.

## DEC-020 — Sugestao de repriorizacao so faz upgrade (nunca downgrade)

- **source:** docs/REGRAS.md secao 8
- **status:** Aceita (implicita) — conservadorismo deliberado
- **locked:** false
- **scope:** logica `_sugerir_repriorizacao` em rules_engine
- **decisao:** Quando ha PRB matched por (produto, servidor), motor compara
  prioridade nova vs. atual. So sugere mudanca se nova for mais grave (menor
  numero). Nunca rebaixa.
- **consequencia:** PRBs em P2 com pouco volume permanecem P2 ate fechamento
  manual. Motor nunca "perde foco" automaticamente.

## DEC-021 — Gatilho proativo P3 → P2 (so promove uma faixa)

- **source:** docs/REGRAS.md secao 7
- **status:** Aceita (implicita) — conservadorismo deliberado
- **locked:** false
- **scope:** logica `_gatilho_proativo_p3` em rules_engine
- **decisao:** Cluster com >=5 INCs P3 identicas tem prioridade promovida para
  P2 (se a cascata classificou P3). Nao promove P2 → P1 (P1 exige criterio
  qualitativo). Nao promove P4/P5 → P2 (mantem rebaixamento).
- **consequencia:** sinal volumetrico forte gera escalada mas nao crise.
