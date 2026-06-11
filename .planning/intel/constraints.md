# Constraints (Synthesized SPEC content)

> Fonte: docs/REGRAS.md (classificado como SPEC, confidence high). Documento
> normativo que define o contrato de implementacao do motor: criterios
> deterministicos, thresholds nomeados, pseudocodigo de cascata, mapeamentos
> veredicto→acao.
>
> Per orientacao do ingest: tratar REGRAS.md como **LOCKED SPEC** — a matriz
> P1-P5 e a fonte oficial Locaweb (reuniao Jessica/Victor/Bruno) e nao pode
> ser auto-overridden. Caso futuro ADR contradiga, exige conflito explicito.

---

## CON-001 — Matriz oficial P1-P5

- **source:** docs/REGRAS.md secao 1
- **type:** business-rule (matriz de priorizacao)
- **locked:** true (LOCKED SPEC por orientacao do PO)
- **content:**

  | Nivel | Urgencia  | Prazo de avaliacao             | Prazo de solucao        |
  |-------|-----------|--------------------------------|-------------------------|
  | P1    | Crise     | Imediato                       | ASAP                    |
  | P2    | Alta      | 1 dia util                     | 4 dias uteis            |
  | P3    | Media     | 4 dias uteis                   | 20 dias uteis           |
  | P4    | Baixa     | sem urgencia                   | sem urgencia            |
  | P5    | Planejado | Sob confirmacao Coord/PO       | sem urgencia definida   |

  **Cascata determinada em `rules_engine._avaliar_cascata`:** P1 → P2 → P3 → P4
  → P5. Primeira regra que casa vence. Default ao final: P5 (se ha contorno e
  qtd_incs<5) ou P4 fallback generico.

## CON-002 — Criterios P1 (Crise)

- **source:** docs/REGRAS.md secao 2
- **type:** business-rule (criterios deterministicos)
- **locked:** true
- **content:**
  - **P1.A:** cluster contem termos Reclame Aqui AND todas INCs sem contorno
    AND `score_ineficiencia >= 0.6 AND qtd_sem_contorno > 0` (OLA estourado
    heuristico).
  - **P1.B:** termos contratacao AND termos indisponibilidade_total AND todas
    INCs sem contorno.
  - **P1.C:** termos indisponibilidade_total AND `cluster.produto IN {CAL,
    Central do Cliente, Painel do Produto}`.
  - **P1.D:** qualquer termo em `TERMOS_RISCO_SEGURANCA` (vazamento, invasao,
    ataque, ransomware, credencial exposta, leak).

  **Limitacao consciente (P1.A):** ETL nao expoe `breach_time` do SNow. "OLA
  estourado" e heuristica via score_ineficiencia. Substituir quando ETL
  evoluir.

## CON-003 — Criterios P2 (Alta)

- **source:** docs/REGRAS.md secao 3
- **type:** business-rule
- **locked:** true
- **content:**
  - **P2.A:** termos Reclame Aqui AND >=1 INC sem contorno.
  - **P2.B:** `qtd_sem_contorno >= LIMIAR_P2_INCS_SEM_CONTORNO` (default 5).
  - **P2.C:** `qtd_com_contorno >= LIMIAR_P2_INCS_COM_CONTORNO` (default 100).
  - **P2.D:** cluster tem contorno AND `tempo_contorno_min_medio >=
    LIMIAR_P2_CONTORNO_MIN` (default 60 min).
  - **P2.E:** nome do cluster contem "instalacao/instalacao" AND >=1 INC com
    `produto` contendo "dedicado".

## CON-004 — Criterios P3 (Media)

- **source:** docs/REGRAS.md secao 4
- **type:** business-rule
- **locked:** true
- **content:**
  - **P3.A:** termos Reclame Aqui AND cluster com contorno.
  - **P3.B:** `0 < qtd_sem_contorno < 5`.
  - **P3.C:** `LIMIAR_P3_INCS_COM_CONTORNO_MIN <= qtd_com_contorno <
    LIMIAR_P3_INCS_COM_CONTORNO_MAX` (default 20 a 99).
  - **P3.D:** tem contorno AND `10 <= tempo_contorno_min_medio < 60`.

## CON-005 — Criterios P4 (Baixa)

- **source:** docs/REGRAS.md secao 5
- **type:** business-rule
- **locked:** true
- **content:**
  - **P4.A:** cluster tem contorno AND (`qtd_com_contorno <
    LIMIAR_P4_INCS_COM_CONTORNO_MAX` default 20 OR `tempo_contorno_min_medio
    < LIMIAR_P4_CONTORNO_MAX_MIN` default 10 com tempo>0).

  **Limitacao consciente:** `tempo_solucao_contorno_min` hoje hardcoded em 0
  no extractor — criterio de tempo raramente dispara em producao.

## CON-006 — Criterios P5 (Planejado)

- **source:** docs/REGRAS.md secao 6
- **type:** business-rule
- **locked:** true
- **content:**
  - Default da cascata quando nenhuma P1-P4 casa AND cluster tem contorno AND
    `qtd_incs < 5`. Motor SUGERE P5 mas explicitamente sinaliza "aguarda
    confirmacao de Coordenador/PO". Decisao final humana.
  - Fallback generico: se nem P5 bater, atribui P4 ("Nenhuma regra mais grave
    acionada — classificado como P4.").

## CON-007 — Gatilho proativo dos 5 P3

- **source:** docs/REGRAS.md secao 7
- **type:** business-rule
- **locked:** true
- **content:** Apos cascata, se cluster tem `>=LIMIAR_PRB_PROATIVO_INCS_P3`
  (default 5) INCs com `prioridade_atual == P3`, adiciona justificativa
  textual e promove para P2 (se a cascata classificou como P3). Nao promove
  P2→P1, P4/P5→P2.

## CON-008 — Sugestao de repriorizacao (so upgrade)

- **source:** docs/REGRAS.md secao 8
- **type:** business-rule
- **locked:** true
- **content:**
  - Match: primeiro PRB onde `prb.produto.lower() == cluster.produto.lower()
    AND prb.servidor.lower() == cluster.servidor_principal.lower()`.
  - Comparacao: `ORDEM_PRIORIDADE = {P1:1, P2:2, P3:3, P4:4, P5:5}`.
    Sugere upgrade se `nova_int < atual_int`. Nunca rebaixa.
  - Acoes resultantes quando ha PRB matched: REPRIORIZAR_PRB (se upgrade) /
    MONITORAR (se PRB ja igual ou mais grave). Sem PRB matched: ABRIR_PRB
    (P1/P2), MONITORAR (P3), NENHUMA (P4/P5).

## CON-009 — Saude do Cliente: criterio `alerta_recorrencia_alta`

- **source:** docs/REGRAS.md secao 9, docs/SAUDE_DO_CLIENTE.md
- **type:** business-rule
- **locked:** true
- **content:**
  - Fase 1 — identificacao de candidatos:
    - Janela: 30 dias (`JANELA_CANDIDATOS_SAUDE_DIAS`).
    - Filtro de tipo: `TIPOS_USUARIO_SAUDE_CLIENTE = ("Nominal",)`.
    - Normalizacao: `sql_normalizar_login_cliente` (port locapredict).
    - Limiar volume: `>= LIMIAR_INCS_SAUDE_CLIENTE` (default 3).
  - Veredicto disparado se ambos:
    - `qtd_incs_periodo >= 3`.
    - Pelo menos 1 INC nos ultimos 7 dias (`JANELA_RECENCIA_ALERTA_DIAS`).
  - Severidade media (`PESO_PRIORIDADE_SEVERIDADE`): P1=1.0, P2=0.75, P3=0.50,
    P4=0.25, P5=0.0.

## CON-010 — Clusterizacao TF-IDF + DBSCAN + fusao por CI

- **source:** docs/REGRAS.md secao 12, docs/ARQUITETURA.md modulo analyzer
- **type:** technical-constraint
- **locked:** true
- **content:**
  - `DBSCAN_EPS = 0.55` (cosseno).
  - `DBSCAN_MIN_SAMPLES = 2`.
  - `TFIDF_NGRAM_RANGE = (1, 2)` (unigrams + bigrams).
  - Pos-DBSCAN: `_fundir_singletons_por_ci` agrupa singletons com mesmo
    `produto` truthy AND mesmo `servidor` truthy. Singletons com CI
    incompleto permanecem singletons.
  - Persistencia: clusters com `qtd_incs == 1` NAO entram em
    `lwsa.motor_cluster` (regra de filtro em `notifier_db.persistir_execucao`).

## CON-011 — Filtros de organizacao e login

- **source:** docs/REGRAS.md secao 13
- **type:** scope-filter
- **locked:** true
- **content:**
  - `ORGANIZACOES_ATIVAS: tuple = ("Locaweb",)` — restringe INCs, PRBs e
    chamados. Tupla vazia = sem filtro.
  - `LOGIN_CLIENTE_PADROES_EXCLUIDOS: tuple = ("kinghost",)` — aplicado SO em
    `contar_clientes_com_inc_recente`. Substring NOT ILIKE.

## CON-012 — ValidadorEntrega: 3 veredictos + 3 sinais auxiliares

- **source:** docs/REGRAS.md secao 14, docs/VALIDADOR_ENTREGA.md
- **type:** business-rule
- **locked:** true
- **content:**
  - **REINCIDENCIA:** `qtd_incs_pos_resolucao >= LIMIAR_INCS_REINCIDENCIA`
    (default 3) no mesmo `(produto, servidor)`. Reincidencia tem precedencia
    sobre tempo. **Slack: SIM.**
  - **ENTREGA_VALIDADA:** `qtd_incs_pos_resolucao == 0` AND `dias_pos_resolucao
    >= MIN_DIAS_PARA_VALIDAR` (default 7). **Slack: NAO.**
  - **INCONCLUSIVO:** casos intermediarios. **Slack: NAO.**
  - **Sinal 1 — Volumetria pre-resolucao:** janela
    `JANELA_VOLUMETRIA_PRE_DIAS=60` dias. Campos: `qtd_incs_pre_resolucao`,
    `clientes_unicos_pre`, `categorias_pre`.
  - **Sinal 2 — Delta chamados vinculados:** `JANELA_CHAMADOS_DELTA_DIAS=14`
    dias em cada lado. Match: `chamados.prb = prb_id OR inc IN (incs_periodo)`.
    Alerta com seta para baixo quando `delta <= LIMIAR_REDUCAO_CHAMADOS_PCT`
    (-0.5).
  - **Sinal 3 — PRBs novos pos-resolucao:** lista de `numero` no mesmo CI
    apos `data_encerrado`. PRB sendo validado excluido por `numero <> %s`.

## CON-013 — Termos heuristicos (word boundary regex)

- **source:** docs/REGRAS.md secao 10
- **type:** lexicon
- **locked:** true (definidos em config.py, ajuste exige revisao deliberada)
- **content:**
  - Match via `\b...\b` para proteger siglas curtas (ex.: "ra" nao casa em
    "fora").
  - Listas: `TERMOS_RECLAME_AQUI`, `TERMOS_CONTRATACAO`,
    `TERMOS_INDISPONIBILIDADE_TOTAL`, `TERMOS_RISCO_SEGURANCA`,
    `TERMOS_SEM_CONTORNO` (futura), `_TERMOS_INDICADORES_CONTORNO` (em
    extractor).

## CON-014 — Permissoes de banco

- **source:** docs/MANUAL.md secao 1.5
- **type:** infrastructure-constraint
- **locked:** false (configuravel por DBA)
- **content:**
  - Conta do motor precisa de `SELECT` em `lwsa.service_now_incidentes`,
    `lwsa.service_now_problemas`, `dynamics.chamados`, `kinghost.chamados`,
    `lw_octadesk.classificacoes`.
  - `INSERT, SELECT` em `lwsa.motor_*` (5 tabelas).
  - `USAGE, SELECT` em sequencias `lwsa.motor_*_id_seq`.
  - `DELETE` opcional (so se `CLEANUP_TTL_HABILITADO=true`).

## CON-015 — Compatibilidade Postgres 9.2/9.3

- **source:** docs/ARQUITETURA.md secao 6
- **type:** infrastructure-constraint
- **locked:** false (migrar quando infra atualizar)
- **content:** Tipos `json` (nao `jsonb`) em todas as colunas JSON.
  Documentacao em `sql/motor_tables.sql`. Plano de migracao: ALTER TABLE em
  6 colunas + ajuste em `notifier_db.py`.

## CON-016 — Pre-requisitos de runtime

- **source:** docs/MANUAL.md secao 1
- **type:** runtime-constraint
- **locked:** false
- **content:**
  - Python 3.10+ (testado em 3.13).
  - Dependencias: `psycopg2-binary`, `scikit-learn`, `requests`, `schedule`,
    `pandas`, `tzdata`, `pytest`.
  - `config.ini` compartilhado com locapredict em `projetos/config.ini`.
  - 5 tabelas DDL em `lwsa` criadas via `sql/motor_tables.sql` (1x).

## CON-017 — Cadencia operacional dos jobs

- **source:** docs/MANUAL.md secao 2, docs/ARQUITETURA.md
- **type:** scheduling-constraint
- **locked:** false (configuravel no Task Scheduler)
- **content:**
  - Motor preventivo: a cada 15 min via `Motor-PRB.bat` (Task Scheduler).
  - ValidadorEntrega: a cada 6h via `Motor-PRB-Validador.bat`.
  - Default em producao: `USAR_MOCKS=false` (mudou em 2026-06-02).
  - Single-run: cada execucao roda 1 ciclo e encerra. Exit code 0=ok, 1=erros.
