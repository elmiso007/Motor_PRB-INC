# Context Notes (DOC-level Synthesized)

> Fonte: docs/APRESENTACAO.md, GLOSSARIO.md, docs/ARQUITETURA.md,
> docs/MANUAL.md, docs/SAUDE_DO_CLIENTE.md, docs/VALIDADOR_ENTREGA.md.
> Todos classificados como DOC (precedencia mais baixa).

---

## Topico: Visao Executiva (origem do projeto)

- **source:** docs/APRESENTACAO.md
- **conteudo:**
  - Motor Prescritivo PRB e MVP irmao do locapredict.
  - Resolve dor: plantao dependia de percepcao humana para notar que 5 INCs
    isoladas eram, na verdade, o mesmo problema crescendo. Motor faz essa
    deteccao sistematicamente e antecipa crises.
  - Requisito original levantado em reuniao com Jessica, Victor e Bruno
    (Locaweb).
  - Resultados operacionais registrados em 2026-06-02.

## Topico: Arquitetura em camadas (4 niveis)

- **source:** docs/ARQUITETURA.md secao 2
- **conteudo:**
  - Nivel 1 (Fundacao): config.py, models.py — stdlib only.
  - Nivel 2 (Utilitarios): time_utils.py, db.py — importa Nivel 1.
  - Nivel 3 (Dominio): extractor, analyzer, rules_engine, customer_monitor,
    notifier, notifier_db, validador_entrega.
  - Nivel 4 (Orquestracao): main.py, scheduler.py, validar_entregas.py.
  - Regra: imports so vao "para baixo". Verificavel via grep.

## Topico: Fluxo de dados end-to-end por ciclo

- **source:** docs/ARQUITETURA.md secao 3
- **conteudo:**
  - Entrada por ciclo: ~91 INCs + ~80 chamados + ~2 PRBs (volumes mock).
  - Saidas: 1 JSON ~30KB + 24 rows Postgres + ~13-15 mensagens Slack.
  - Tempo total: ~5-10s no preventivo.
  - Fase Saude do Cliente: ~30-45s isoladamente (depois do bulk+slim+indices).
  - Memoria pico: ~196 objetos Python.

## Topico: 7 principios transversais

- **source:** docs/ARQUITETURA.md secao 5
- **conteudo:**
  1. Defesa em camadas (try/except em 4 niveis).
  2. Single Responsibility por modulo.
  3. Configurabilidade externa (zero numero magico).
  4. UTC interno, BRT na fronteira.
  5. Justificativa auditavel em decisoes (texto livre em justificativas).
  6. `ExecucaoMotor` como agregador unico (1 objeto carrega todo ciclo).
  7. Degradacao suave (funcionalidade reduzida > ausente).

## Topico: Limitacoes conscientes do MVP

- **source:** docs/ARQUITETURA.md secao 8
- **conteudo:**
  - Motor stateless aceito — analise temporal via SQL.
  - Repeticao de alertas Slack para PRBs (so Saude tem anti alert-fatigue).
  - Sem retry/backoff (proximo ciclo 15min tenta).
  - Sem health check HTTP (monitorar timestamp do JSON ou MAX em motor_execucao).
  - Limiar Saude unico por porte de cliente (falta dado de porte no banco).
  - Sem ML aprendendo com feedback (decisao deliberada — regras
    deterministicas auditaveis > ML opaco no MVP).
  - Sem integracao bidirecional com SNow (motor sugere, humano decide).
  - Sem microservices (monolito modular adequado).
  - `tempo_solucao_contorno_min` hardcoded em 0 — criterio P4 de tempo
    raramente dispara.
  - `breach_time` SNow nao replicado pelo ETL — OLA estourado e heuristica.

## Topico: Pontos de extensao prontos sem refactor

- **source:** docs/ARQUITETURA.md secao 7
- **conteudo:**
  - Adicionar organizacao = editar `TABELAS_CHAMADOS_POR_ORGANIZACAO`.
  - Adicionar saida (email, Teams) = novo modulo `notifier_X.py`.
  - Adicionar nivel P0 = `MAPA_URGENCIA_PRIORIDADE` + funcao `_avaliar_p0`.
  - ABCs: `FonteIncidentes`, `FonteChamados` para substituir backends.

## Topico: Setup operacional

- **source:** docs/MANUAL.md secoes 1-3
- **conteudo:**
  - Python 3.10+ (testado em 3.13).
  - Dependencias: psycopg2-binary, scikit-learn, requests, schedule, pandas,
    tzdata, pytest.
  - `config.ini` compartilhado com locapredict em `projetos/config.ini`.
  - DDL 1x via `Motor PRB-INC/sql/motor_tables.sql`.
  - Permissoes minimas: SELECT em lwsa.*, dynamics.*, kinghost.*, lw_octadesk.*.
    INSERT+SELECT em lwsa.motor_*. USAGE+SELECT em sequencias.

## Topico: Dashboard JSON e mensagens Slack

- **source:** docs/MANUAL.md secoes 5-6, docs/ARQUITETURA.md modulo notifier
- **conteudo:**
  - `output/dashboard_state.json` UTF-8 indent 2.
  - Emojis combinados: 🚨🆘=critico+abrir, ⚠️🔧=alta+repriorizar.
  - Emoji Saude: :thermometer:. Emoji reincidencia: ⚠️🔁.
  - Slack so para criticos (CRITICA + recorrencia_alta + reincidencia).

## Topico: Queries SQL uteis

- **source:** docs/MANUAL.md secao 7 (nao expandido neste sintese, referenciar arquivo)
- **conteudo:** queries.sql / sql/motor_tables.sql contem DDL e queries de
  consulta. Verificar arquivo direto para detalhes.

## Topico: Saude do Cliente — Login canonico

- **source:** docs/SAUDE_DO_CLIENTE.md, docs/REGRAS.md secao 12
- **conteudo:**
  - Funcao SQL `sql_normalizar_login_cliente(coluna)` portada do locapredict.
  - Resolve 5 formatos do `login_cliente`: `username`, `username (Cod. NNN)`,
    URL `intranet.kinghost.com.br/.../ficha=NNN`, digitos puros, texto puro.
  - Equivalente Python `normalizar_login_cliente(s)` em extractor.py para
    coerencia em mocks.
  - Enriquecimento via `dynamics.chamados.logincliente` (DISTINCT ON):
    `login_efetivo = COALESCE(NULLIF(TRIM(dyn.logincliente), ''), sni.login_cliente)`.

## Topico: ValidadorEntrega — Historico de evolucao

- **source:** docs/VALIDADOR_ENTREGA.md
- **conteudo:**
  - V1: veredicto so por INCs novas pos-resolucao.
  - V2 (2026-06-02): + volumetria pre + delta chamados por produto.
  - V3 (2026-06-02): match de chamados via vinculo (`chamados.prb` OR `inc`),
    nao por produto. Cobertura cai mas precisao sobe.
  - V3.1: + tabela `motor_validacao_entrega_equipe` (times impactados) +
    Slack on + TOP=7.

## Topico: Glossario — termos chave

- **source:** GLOSSARIO.md
- **conteudo:** Termos ITSM/ITIL (INC, PRB, CI, OLA, SLA), ServiceNow,
  Dynamics 365, ML/NLP (TF-IDF, DBSCAN, NFKD), Locaweb-especificos (lwsa,
  produto, servidor, login_cliente), convencoes de codigo PT-BR. Referencia
  direta para tirar duvida de jargao — nao re-sintetizado aqui.

## Topico: Projetos relacionados

- **source:** GLOSSARIO.md, docs/ARQUITETURA.md
- **conteudo:**
  - **locapredict** — projeto irmao em `MRP para PRB/locapredict/`. Cadencia
    semanal, usa sentence-transformers. Motor PRB-INC reutiliza padroes:
    `sql_normalizar_login_cliente`, `config.ini`, Slack bot token.
  - **dashboard_state.json** consumivel por Streamlit, HTML estatico ou
    scripts ad-hoc.

## Topico: Resultados operacionais (2026-06-02)

- **source:** docs/APRESENTACAO.md (slides)
- **conteudo:** numeros de producao reportados em data 2026-06-02 — verificar
  slide deck para metricas atualizadas. Conteudo nao replicado aqui para
  evitar dessincronia.

## Topico: Painel Change Team (informacao do prompt do ingest)

- **source:** prompt do usuario na adocao GSD (NAO em doc classificado)
- **conteudo:**
  - Force-task interdisciplinar "Change Team" recebeu ~88 PRBs especificos.
  - Necessidade de painel de acompanhamento desses 88 PRBs.
  - Sem PRD/SPEC/ADR escrito ainda. Capturado como REQ-painel-change-team
    em requirements.md com status `upcoming`.
  - Acceptance criteria ainda em aberto — exige refinamento downstream.
