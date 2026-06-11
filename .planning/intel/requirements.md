# Requirements (Synthesized)

> Fonte: nenhum PRD formal foi classificado. Os requisitos abaixo foram
> derivados:
> 1. **Implicit-from-DOC:** docs/MANUAL.md e docs/ARQUITETURA.md descrevem
>    comportamento ja em producao — tratado como requisito existente
>    ("As-Built Requirement"). Acceptance criteria sao o comportamento atual.
> 2. **Implicit-from-SPEC:** docs/REGRAS.md (LOCKED SPEC) define regras de
>    negocio que sao requisitos de saida.
> 3. **Roadmap / Upcoming:** o item "Painel Change Team" foi indicado pelo
>    usuario no contexto do ingest e NAO consta em nenhum doc. Capturado como
>    requirement upcoming (nao existe ainda).
>
> ID convencao: `REQ-{kebab-slug}`. `status: existing` = ja implementado;
> `status: upcoming` = ainda nao implementado.

---

## REQ-extracao-snow-incidentes

- **source:** docs/ARQUITETURA.md secao 3 (Fase 1), docs/MANUAL.md
- **status:** existing
- **description:** Motor le INCs abertas nas ultimas 24h de
  `lwsa.service_now_incidentes`, com filtro `organizacao IN (config.ORGANIZACOES_ATIVAS)`.
- **acceptance:**
  - SELECT retorna INCs com `data_abertura >= NOW() - 24h` em BRT naive,
    convertidas internamente para UTC tz-aware.
  - Parsers defensivos: prioridade "3"→"P3", data BRT→UTC, contagem de
    atualizacoes via regex no texto.
  - Falha aqui aborta o ciclo (critico).
- **scope:** extracao

## REQ-extracao-chamados-multi-org

- **source:** docs/ARQUITETURA.md modulo extractor, docs/MANUAL.md
- **status:** existing
- **description:** Motor le chamados das ultimas 24h de Locaweb
  (`dynamics.chamados` JOIN `lw_octadesk.classificacoes`) e KingHost
  (`kinghost.chamados`), via registry declarativo.
- **acceptance:**
  - SQL construido dinamicamente a partir de
    `config.TABELAS_CHAMADOS_POR_ORGANIZACAO`.
  - KingHost so processada se em `ORGANIZACOES_ATIVAS`.
  - Falha em fonte de chamados nao aborta ciclo (chamados=[]; nao critico).
- **scope:** extracao

## REQ-extracao-prbs-ativos

- **source:** docs/ARQUITETURA.md secao 3
- **status:** existing
- **description:** Motor le PRBs ativos (`status` em `STATUS_PRB_ATIVOS`) de
  `lwsa.service_now_problemas` para match de repriorizacao.
- **acceptance:**
  - PRBs filtrados por status e organizacao.
  - Cada PRB retorna `numero, produto, servidor, prioridade, status, data_abertura`.
- **scope:** extracao

## REQ-clusterizacao-semantica

- **source:** docs/ARQUITETURA.md modulo analyzer, docs/REGRAS.md secao 12
- **status:** existing
- **description:** Agrupar INCs semanticamente similares via TF-IDF + DBSCAN
  + fusao por (produto, servidor) para singletons.
- **acceptance:**
  - INCs normalizadas via NFKD + lowercase + remocao de pontuacao + stop-words
    PT-BR.
  - TfidfVectorizer com `ngram_range=(1,2)`, `max_features=5000`.
  - DBSCAN com `eps=0.55, min_samples=2, metric='cosine'`.
  - Fallback Jaccard se sklearn nao disponivel.
  - Pos-DBSCAN: singletons com mesmo produto truthy E mesmo servidor truthy
    sao fundidos via `_fundir_singletons_por_ci`.
  - Singletons (qtd=1) NAO persistem em motor_cluster mas continuam em memoria.
- **scope:** analise

## REQ-scores-criticidade-ineficiencia

- **source:** docs/ARQUITETURA.md modulo analyzer
- **status:** existing
- **description:** Cada cluster recebe dois scores 0-1 ponderados.
- **acceptance:**
  - **Criticidade** = 0.35*volume + 0.30*indisponibilidade + 0.25*sem_contorno
    + 0.10*recorrencia_ci.
  - **Ineficiencia** = 0.6*volume_updates + 0.4*velocidade_updates_hora.
  - Pesos em `config.PESO_*`.
- **scope:** analise

## REQ-cascata-p1-p5

- **source:** docs/REGRAS.md secoes 1-6, docs/ARQUITETURA.md modulo rules_engine
- **status:** existing
- **description:** Aplicar a matriz oficial P1-P5 com avaliacao em cascata.
- **acceptance:** Ver CON-001 a CON-006 (constraints.md). Justificativa textual
  acumulada e renderizada em Slack/dashboard. Defesa por cluster: falha em 1
  nao derruba os outros.
- **scope:** regras

## REQ-gatilho-proativo-p3

- **source:** docs/REGRAS.md secao 7
- **status:** existing
- **description:** Promover P3→P2 quando cluster tem >=5 INCs identicas em P3.
- **acceptance:** Ver CON-007. So promove P3→P2; nao mexe em P1/P2/P4/P5.
- **scope:** regras

## REQ-sugestao-repriorizacao

- **source:** docs/REGRAS.md secao 8
- **status:** existing
- **description:** Comparar prioridade sugerida pelo motor vs. PRB existente
  matched por (produto, servidor) e sugerir upgrade quando aplicavel.
- **acceptance:** Ver CON-008. Saida: acao=REPRIORIZAR_PRB | MONITORAR |
  ABRIR_PRB | NENHUMA.
- **scope:** regras

## REQ-saude-cliente-recorrencia

- **source:** docs/REGRAS.md secao 9, docs/SAUDE_DO_CLIENTE.md
- **status:** existing
- **description:** Identificar clientes com recorrencia alta (>=3 INCs em 6m
  + recencia 7d) e consolidar timeline cronologica SNow + chamados.
- **acceptance:** Ver CON-009. Estrategia bulk+slim, performance ~30-45s
  ciclo. Linha do tempo apenas no dashboard JSON; Slack so resumo numerico.
- **scope:** saude-cliente

## REQ-validador-entrega-v3

- **source:** docs/VALIDADOR_ENTREGA.md, docs/REGRAS.md secao 14
- **status:** existing (V3.1 em producao desde 2026-06-02)
- **description:** Olhar PRBs ja entregues pelo Change Team e classificar em
  REINCIDENCIA / ENTREGA_VALIDADA / INCONCLUSIVO com 3 sinais auxiliares.
- **acceptance:** Ver CON-012. Persiste em `motor_validacao_entrega` (21
  colunas) e em `motor_validacao_entrega_equipe` (times impactados).
- **scope:** validador

## REQ-output-dashboard-json

- **source:** docs/ARQUITETURA.md secao 3 (Fase 5a), notifier.py
- **status:** existing
- **description:** Gravar `output/dashboard_state.json` SEMPRE em cada ciclo.
- **acceptance:**
  - JSON ~30KB, UTF-8, indent 2.
  - Estrutura normalizada (separacao clusters/incidentes).
  - Sempre primeiro nas saidas (fallback robusto).
- **scope:** output

## REQ-output-persistencia-postgres

- **source:** docs/ARQUITETURA.md modulo notifier_db, sql/motor_tables.sql
- **status:** existing
- **description:** Persistir cada ciclo em 5 tabelas `lwsa.motor_*` em
  transacao atomica.
- **acceptance:**
  - Tabelas: motor_execucao, motor_cluster, motor_prescricao,
    motor_saude_cliente, motor_validacao_entrega.
  - Singletons filtrados (qtd_incs<2) antes do INSERT em motor_cluster.
  - Defesa: falha de Postgres nao aborta motor (JSON e Slack continuam).
  - Configuravel via `PERSISTIR_NO_BANCO`.
  - Cleanup TTL desabilitado por default (`CLEANUP_TTL_HABILITADO=false`) —
    DBA gerencia.
- **scope:** output

## REQ-output-slack-criticos

- **source:** docs/ARQUITETURA.md modulo notifier, docs/MANUAL.md secao 6
- **status:** existing
- **description:** Disparar alertas Slack para `prescricoes.urgencia=CRITICA`
  + `saude.alerta_recorrencia_alta` + reincidencias do ValidadorEntrega.
- **acceptance:**
  - Preferencia: `slack_sdk.WebClient.chat_postMessage` (Bot Token).
  - Fallback: HTTP POST webhook legado.
  - Rate limit 1s entre envios.
  - Sem config: log "Slack desabilitado/sem webhook" e retorno False.
  - Emojis combinados (urgencia + acao).
- **scope:** output

## REQ-cadencia-15min-preventivo

- **source:** docs/MANUAL.md secao 2.3, docs/ARQUITETURA.md
- **status:** existing
- **description:** Motor preventivo executa a cada 15 min em producao.
- **acceptance:**
  - `Motor-PRB.bat` disparado por Windows Task Scheduler.
  - `python main.py` roda single-run e termina (sem loop interno).
  - Exit code 0=sucesso, 1=erros.
- **scope:** orquestracao

## REQ-cadencia-6h-validador

- **source:** docs/ARQUITETURA.md modulo `validar_entregas.py`, docs/VALIDADOR_ENTREGA.md
- **status:** existing
- **description:** ValidadorEntrega executa a cada 6h em producao.
- **acceptance:**
  - `Motor-PRB-Validador.bat` disparado por Task Scheduler.
  - `python validar_entregas.py` single-run.
  - Logs proprios em `validador-entrega-{data}.log`.
- **scope:** orquestracao

## REQ-logs-rotacionados

- **source:** docs/ARQUITETURA.md modulo main.py, docs/MANUAL.md secao 4
- **status:** existing
- **description:** Console + arquivo rotacionado por dia em UTF-8.
- **acceptance:**
  - Filename: `motor-prb-{YYYY-MM-DD}.log`.
  - Console handler com UTF-8 forcado (Windows).
  - Rotacao diaria.
- **scope:** observabilidade

## REQ-modo-mock

- **source:** docs/MANUAL.md secao 2.2
- **status:** existing
- **description:** Modo `USAR_MOCKS=true` gera dados sinteticos coerentes para
  desenvolvimento e testes sem banco.
- **acceptance:**
  - Sintetiza ~91 INCs + 80 chamados + 2 PRBs + 13-19 clientes.
  - Factories `criar_fonte_incidentes()` / `criar_fonte_chamados()` retornam
    mocks quando env var ativa.
  - Default em producao: `USAR_MOCKS=false` (desde 2026-06-02).
- **scope:** dev-experience

## REQ-painel-change-team (UPCOMING)

- **source:** entrada do usuario via prompt de ingest (NAO consta em nenhum doc
  classificado). Marcador para o roadmapper.
- **status:** **upcoming** — nova feature a planejar
- **description:** Dashboard panel para acompanhar ~88 PRBs especificos
  atribuidos a uma force-task interdisciplinar ("Change Team"). Deve
  permitir tracking do progresso dos PRBs do escopo da forca-tarefa.
- **acceptance (a definir pelo roadmapper):**
  - **PROVISORIO — exige refinamento via PRD/RDD:**
    - Lista filtrada de ~88 PRBs especificos (criterio de selecao do escopo
      a definir: por numero, por grupo_designado, por etiqueta, etc.).
    - Visao consolidada: prioridade atual, status, idade, ultima atualizacao.
    - Cruzamento com ValidadorEntrega: quais ja foram entregues, quais
      tiveram reincidencia.
    - Possivel integracao com Saude do Cliente: clientes impactados.
  - **Decisoes em aberto:**
    - Fronteira tecnologica: dashboard web (Streamlit/HTML) ou extensao do
      JSON ja gerado pelo motor?
    - Cadencia: real-time, 15min (acompanha motor), ou outra?
    - Onde mora a lista dos ~88 PRBs: hardcoded, tabela nova, etiqueta no SNow?
    - Quem consome: time Change Team, coordenacao, todos?
- **scope:** painel-change-team
- **notes:** Esta e a unica feature **nova** prevista no momento da adocao do
  GSD. Roadmapper deve abrir thread de discovery (PRD ou ADR) antes de
  prescrever implementacao.
