# 📊 Análise da Aplicação — Motor Prescritivo PRB-INC

**Data da Análise:** 15 de junho de 2026  
**Projeto:** Motor Prescritivo PRB  
**Tipo:** Sistema de automação de gestão de incidentes e problemas  
**Linguagem:** Python 3.10+  
**Arquitetura:** Modular, orientada a dados, baseada em regras

---

## 📌 Sumário Executivo

O **Motor Prescritivo PRB** é um sistema inteligente de **automação preventiva** que:
- **Lê** incidentes, problemas e chamados de múltiplas fontes (ServiceNow, Dynamics, Kinghost)
- **Agrupa** semanticamente usando TF-IDF + DBSCAN
- **Aplica** matriz oficial de priorização P1-P5
- **Recomenda** ações: abrir PRB, repriorizar, monitorar
- **Alerta** via Slack para crises + persiste estado em PostgreSQL

**Status:** Produção em Windows via Task Scheduler (execução single-run a cada hora)

---

## 🏗️ 1. Arquitetura Geral

### 1.1 Visão em camadas

```
┌─────────────────────────────────────────────────┐
│ NÍVEL 4: ORQUESTRAÇÃO                           │
│ main.py → scheduler.py → executar_ciclo()       │
│ (entry point single-run, sem loop interno)      │
└──────────────────┬──────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────┐
│ NÍVEL 3: DOMÍNIO                                │
│ • extractor.py       → leitura de dados         │
│ • analyzer.py        → clusterização semântica  │
│ • rules_engine.py    → aplicação de regras      │
│ • customer_monitor.py → saúde do cliente        │
│ • notifier.py        → alertas Slack            │
│ • notifier_db.py     → persistência em BD       │
└──────────────────┬──────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────┐
│ NÍVEL 2: UTILITÁRIOS                            │
│ • time_utils.py  → conversão de timezones       │
│ • db.py          → pool de conexão PostgreSQL   │
└──────────────────┬──────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────┐
│ NÍVEL 1: FUNDAÇÃO                               │
│ • config.py → thresholds e configurações        │
│ • models.py → dataclasses tipadas               │
└─────────────────────────────────────────────────┘
```

### 1.2 Princípios de design

✅ **Sem acoplamento entre módulos** — importações seguem hierarquia  
✅ **Sem loops internos** — scheduler externo comanda execução  
✅ **Funções puras** — regras recebem dados, devolvem decisões  
✅ **Defensive coding** — erros isolados não interrompem o pipeline  
✅ **Logs estruturados** — rastreabilidade completa de decisões  
✅ **Tipagem completa** — dataclasses + type hints

---

## 🔧 2. Componentes Principais

### 2.1 `extractor.py` — Ingestão de Dados

**Responsabilidade:** Ler dados de PostgreSQL (ServiceNow, Dynamics, Kinghost)

| Classe | Função |
|--------|--------|
| `FonteIncidentes` | Interface abstrata para INCs + PRBs |
| `FonteIncidentesReal` | Implementação PostgreSQL real |
| `FonteIncidentesMock` | Dados sintéticos para testes |
| `FonteChamados` | Interface abstrata para chamados |
| `FonteChamadosReal` | Dynamics + Kinghost via PostgreSQL |

**Fluxo:**
```
PostgreSQL (lwsa.*) → Incidente (dataclass)
PostgreSQL (dynamics/kinghost) → InteracaoChamado (dataclass)
```

**Destaques:**
- Suporta mocks (config.USAR_MOCKS) para validação sem rede
- Janelas de tempo configuráveis (JANELA_INC_HORAS=24, etc.)
- Tratamento defensivo de parsing (datas, prioridades)

---

### 2.2 `analyzer.py` — Clusterização Semântica

**Responsabilidade:** Agrupar INCs similares usando machine learning

| Função | O que faz |
|--------|-----------|
| `analisar()` | Orquestra TF-IDF + DBSCAN |
| `_vetorizar()` | Converte texto em vetor TF-IDF |
| `_clusterizar()` | DBSCAN encontra grupos densos |
| `_calcular_scores()` | Severidade, ineficiência, SLA |
| `_enriquecer()` | Adiciona volume de chamados |

**Parâmetros (em config.py):**
```python
MIN_DOCS_TF_IDF = 2              # Mínimo para vetorização
EPSILON_DBSCAN = 0.4             # Raio de densidade
MIN_SAMPLES_DBSCAN = 2           # Mínimo por vizinhança
PESO_VOLUME_SCORE = 0.3          # Impacto de chamados
```

**Saída:** Lista de `Cluster` — cada um é um grupo de INCs correlatas com scores

---

### 2.3 `rules_engine.py` — Matriz P1-P5

**Responsabilidade:** Classificar clusters e gerar prescrições

**Cascata de regras (a primeira que casa vence):**

| P-Level | Trigger | Exemplo |
|---------|---------|---------|
| **P1** | `_avaliar_p1()` | OLA estourado + crise explícita |
| **P2** | `_avaliar_p2()` | ≥5 INCs sem contorno OU ≥100 com contorno |
| **P3** | `_avaliar_p3()` | 20-100 INCs com contorno |
| **P4** | `_avaliar_p4()` | <20 INCs com contorno |
| **P5** | Fallback | Sem match em nenhuma regra |

**Gatilho proativo:**
- Se ≥5 INCs P3 **idênticas** (mesmo cluster) → elevar P2 + sugerir abrir PRB

**Sugestão de repriorização:**
- PRB já aberto em P3 mas realidade atual bate em P2 → sugerir upgrade

**Saída:** `PrescricaoPRB` com:
- Prioridade calculada
- Lista de justificativas (bullets auditáveis)
- Ação sugerida (abrir / repriorizar / monitorar / nada)

---

### 2.4 `customer_monitor.py` — Saúde do Cliente

**Responsabilidade:** Detectar clientes com padrão de recorrência alta

| Função | O que faz |
|--------|-----------|
| `avaliar_saude()` | Identifica clientes em risco |
| `_buscar_candidatos()` | Query ampliada (30 dias) para clientes com ≥3 INCs |
| `_construir_timeline()` | Consolida INCs + chamados com timeline |

**Gatilho:** Cliente com ≥3 INCs em 6 meses + INC recente (últimos 7 dias)

**Filtro por tipo:** `tipo_usuario = "Nominal"` (cliente real, não integração)

**Saída:** `SaudeCliente` com:
- Identificação do cliente
- Severidade média (ponderada P1=1.0 ... P5=0.0)
- Timeline consolidada (INCs + chamados)

---

### 2.5 `notifier.py` → Slack & Dashboard

**Responsabilidade:** Comunicar resultados

| Função | Canal |
|--------|-------|
| `enviar_alertas_criticos()` | Slack (apenas P1) |
| `montar_dataframes_dashboard()` | Pandas → JSON |
| `_renderizar_prescricao()` | Formatação verbatim das justificativas |

**Alertas críticos (P1):**
- Thread no Slack com cluster, justificativa, ações
- Cc: canal default + on-call (se configurado)

**Dashboard (JSON):**
- Clusters ordenados por score
- Prescrições com status ("novo", "aceito", "rejeitado", etc.)
- Saúde de clientes com timeline

---

### 2.6 `notifier_db.py` → PostgreSQL

**Responsabilidade:** Persistir estado para auditoria + dashboard

| Tabela | Conteúdo |
|--------|----------|
| `motor_cluster` | Clusters da rodada (MD5 do grupo) |
| `motor_prescricao` | Prescrições geradas |
| `motor_saude_cliente` | Clientes monitorados |
| `motor_execucao` | Metadata da rodada (duração, erros) |

**Uso:** SQL direto para análise de tendências, validação retrospectiva

---

### 2.7 `scheduler.py` — Orquestração

**Responsabilidade:** Coordenar todo o pipeline

```python
def executar_ciclo(fonte_inc, fonte_chamados) -> ExecucaoMotor:
    # 1. Extração (INCs, chamados, PRBs)
    # 2. Análise (clustering + scores)
    # 3. Regras (prescrições P1-P5)
    # 4. Customer Monitor (saúde)
    # 5. Notificação (Slack + BD)
    # Retorna: relatório de execução com erros/métricas
```

**Tratamento de erro:** Falha em uma etapa **não** interrompe as próximas — o motor é resiliente a flakiness de APIs

**Saída:** `ExecucaoMotor` com:
- `clusters: List[Cluster]`
- `prescricoes: List[PrescricaoPRB]`
- `saude_clientes: List[SaudeCliente]`
- `erros: List[str]`
- `duracao_ciclo_ms: int`

---

### 2.8 Módulos Secundários

| Módulo | Responsabilidade |
|--------|-----------------|
| `time_utils.py` | Conversão de timezones (UTC ↔ BRT) |
| `db.py` | Pool de conexão PostgreSQL (`psycopg2`) |
| `validador_entrega.py` | PRBs candidatos a validação retrospectiva |
| `validar_entregas.py` | Entry point de validação |
| `customer_monitor.py` | Detecção de recorrência por cliente |
| `change_team.py` | Dashboard da Change Team |

---

## 📊 3. Fluxo de Dados (End-to-End)

```
┌──────────────────────────────────────────────┐
│ ENTRADA: main.py                             │
│ - Configura logging (arquivo + console)      │
│ - Cria fontes de dados (Real ou Mock)        │
│ - Dispara scheduler.executar_ciclo()         │
└────────────────┬─────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────┐
│ PASSO 1: EXTRAÇÃO (extractor.py)             │
│ - Query: INCs (24h)                          │
│ - Query: Chamados (24h)                      │
│ - Query: PRBs abertos                        │
│ Output: Incidente[], InteracaoChamado[],     │
│         PRBExistente[]                       │
└────────────────┬─────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────┐
│ PASSO 2: CLUSTERIZAÇÃO (analyzer.py)         │
│ - TF-IDF sobre descricao_curta + descricao   │
│ - DBSCAN agrupa similares                    │
│ - Calcula scores (severidade, ineficiência) │
│ - Cruza com volume de chamados               │
│ Output: Cluster[]                            │
└────────────────┬─────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────┐
│ PASSO 3: REGRAS (rules_engine.py)            │
│ - Cascata P1 → P2 → P3 → P4 → P5             │
│ - Gatilho proativo (5 P3 idênticas)          │
│ - Sugestão de repriorização                  │
│ Output: PrescricaoPRB[]                      │
└────────────────┬─────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────┐
│ PASSO 4: SAÚDE (customer_monitor.py)         │
│ - Query ampliada (30 dias) para candidatos   │
│ - Filtra por tipo_usuario = "Nominal"        │
│ - Consolida timeline INCs + chamados         │
│ Output: SaudeCliente[]                       │
└────────────────┬─────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────┐
│ PASSO 5: NOTIFICAÇÃO (notifier.py)           │
│ - Alertas críticos (P1) → Slack              │
│ - Dashboard JSON → arquivo                   │
│ - Persistência → PostgreSQL (notifier_db.py) │
│ Output: Slack messages, arquivos JSON        │
└────────────────┬─────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────┐
│ SAÍDA FINAL: ExecucaoMotor                   │
│ - Rodada completa em ~10-30s (sem rede)      │
│ - Exit code: 0 (sucesso) ou 1 (erro)         │
│ - Próxima execução: +1h (Task Scheduler)     │
└──────────────────────────────────────────────┘
```

---

## 🛠️ 4. Stack Técnico

### Dependências principais

| Lib | Versão | Uso |
|-----|--------|-----|
| `psycopg2-binary` | 2.9.0+ | Driver PostgreSQL |
| `scikit-learn` | 1.3.0+ | TF-IDF + DBSCAN |
| `requests` | 2.31.0+ | HTTP (ServiceNow, Slack) |
| `slack_sdk` | 3.0.0+ | Slack Bot API |
| `pandas` | 2.0.0+ | Dashboard (dataframes) |
| `tzdata` | 2024.1+ | Timezone Windows |
| `pytest` | 8.0.0+ | Testes |

### Banco de dados

- **Produção:** PostgreSQL (banco `lwsa`, schema compartilhado com locapredict)
- **Tabelas lidas:** `lwsa.service_now_incidentes`, `lwsa.service_now_problemas`, `dynamics.chamados`, `kinghost.chamados`
- **Tabelas escritas:** `motor_cluster`, `motor_prescricao`, `motor_saude_cliente`, `motor_execucao`

### Execução

- **SO:** Windows
- **Orquestração:** Task Scheduler (Motor-PRB.bat)
- **Cadência:** A cada 15 minutos (configurável)
- **Modo:** Single-run (sem loop interno)

---

## ✅ 5. Pontos Fortes

### 5.1 Arquitetura
- ✅ **Modular:** cada módulo tem responsabilidade clara
- ✅ **Sem acoplamento:** importações seguem hierarquia
- ✅ **Testável:** funções puras, mocks integrados
- ✅ **Resiliente:** erro isolado não mata o pipeline

### 5.2 Código
- ✅ **Type hints completos** em toda a codebase
- ✅ **Dataclasses** para models (imutáveis, comparáveis)
- ✅ **Logging estruturado** com contexto
- ✅ **Configuração centralizada** (config.py)

### 5.3 Negócio
- ✅ **Matriz P1-P5 auditável** — cada decisão tem justificativa
- ✅ **Cascata clara** — impossível passar desapercebido um P1
- ✅ **Detecção proativa** — 5 P3 idênticas → PRB automática
- ✅ **Saúde do cliente** — padrão de recorrência detectado

### 5.4 Operação
- ✅ **Logs rotacionados** por dia
- ✅ **Mocks integrados** para validação offline
- ✅ **Dashboard persistido** em BD
- ✅ **Alertas Slack** para crises

---

## 🎯 6. Oportunidades de Melhoria

### 6.1 Performance & Escalabilidade

| Problema | Impacto | Sugestão |
|----------|---------|----------|
| TF-IDF recalculado a cada rodada | Lento com >1000 INCs | Cache de vectorizer ou índice Elasticsearch |
| Query full-table DBSCAN em memória | OOM com grandes datasets | Clustering incremental ou HDBSCAN |
| Pool de conexão DB (default) | Contenção em paralelo | Tune `psycopg2.pool.ThreadedConnectionPool` |

### 6.2 Funcionalidades ausentes

| Funcionalidade | Prioridade | Esforço |
|---|---|---|
| Detecção de termos por NLP (Gemini/OpenAI) | ALTA | Alto |
| SLA real (tempo solução contorno) | ALTA | Médio |
| Validação retrospectiva de PRBs | MÉDIA | Médio |
| Dashboard web (hoje é JSON) | MÉDIA | Alto |
| Feedback loop (rejeição de prescrições) | MÉDIA | Médio |

### 6.3 Testes

| Aspecto | Status | Ação |
|--------|--------|------|
| Testes unitários | ✅ Existem | ✔️ Manter |
| Testes de integração | ❌ Faltam | Testar com dados reais do BD |
| Testes E2E | ❌ Faltam | Executar full pipeline em staging |
| Cobertura de linha | ⚠️ Desconhecida | Medir com `pytest --cov` |

### 6.4 Documentação

| Documento | Status | Ação |
|-----------|--------|------|
| ARQUITETURA.md | ✅ Presente | Manter |
| REGRAS.md | ✅ Presente | Sincronizar com código |
| MANUAL.md | ✅ Presente | Adicionar troubleshooting |
| Docstrings no código | ⚠️ Parcial | Completar em `analyzer.py` |
| Diagramas ER | ❌ Faltam | Gerar para BD |

### 6.5 Segurança & Governança

| Aspecto | Status | Ação |
|--------|--------|------|
| Credenciais via env vars | ✅ OK | Manter (não hardcoded) |
| SQL injection | ✅ OK | Usar parameterized queries (já fazem) |
| Auditoria de decisões | ✅ OK | Logs em BD + JSON |
| Rate limiting API | ⚠️ Parcial | ServiceNow + Slack têm limites — considerar backoff |
| Acesso ao BD | ❌ Rever | Credential rotation? Least privilege? |

---

## 🚀 7. Recomendações Prioritárias

### Curto Prazo (1-2 sprints)

1. **Testes de integração** com dados reais
   - Executar `pytest tests/` contra BD de staging
   - Validar que prescrições batem com manual QA

2. **Sincronizar documentação**
   - Revisar REGRAS.md vs código atual
   - Adicionar exemplos de prescrições reais

3. **Instrumentação**
   - Medir tempo de cada etapa (extração, clustering, regras)
   - Alertar se alguma etapa demorar muito

### Médio Prazo (3-4 sprints)

4. **Dashboard web**
   - Expor JSON atual em interface web
   - Visualizar clusters com scatter plot 2D
   - Marcar prescrições como "aceita/rejeita/pendente"

5. **Feedback loop**
   - Coletar rejeições de prescrições
   - Retrainer de rules com feedback

6. **Validação retrospectiva de PRBs**
   - Implementar `validador_entrega.py` completo
   - Medir taxa de acerto das prescrições (precision/recall)

### Longo Prazo (roadmap)

7. **NLP avançado** (Gemini/Claude)
   - Extração automática de "solução de contorno"
   - Detecção de termos de negócio novos
   - Summarização de clusters para Slack

8. **Previsão (ML)**
   - Prever se INC vai se tornar PRB
   - Score de urgência baseado em padrões históricos

---

## 📈 8. Métricas de Saúde

Monitorar regularmente:

```sql
-- Clusters por rodada (deve ser ~10-30)
SELECT COUNT(*), DATE(timestamp) FROM motor_cluster GROUP BY DATE(timestamp);

-- Prescrições P1 vs P2 (P1 deve ser raro, <5% do volume)
SELECT prioridade, COUNT(*) FROM motor_prescricao 
GROUP BY prioridade ORDER BY prioridade;

-- Taxa de aceitação (if feedback loop existe)
SELECT status, COUNT(*) FROM motor_prescricao 
WHERE status IN ('aceito', 'rejeitado') GROUP BY status;

-- Clientes monitorados com recorrência
SELECT COUNT(DISTINCT cliente_login) FROM motor_saude_cliente;

-- Duração média de ciclo (deve estar <30s)
SELECT AVG(duracao_ciclo_ms) FROM motor_execucao 
WHERE DATE(timestamp) >= CURRENT_DATE - INTERVAL '7 days';
```

---

## 🔍 9. Troubleshooting Comum

### Problema: "Nenhum cluster gerado"
**Causa:** Não há INCs nos últimos 24h ou TF-IDF não convergiu  
**Solução:** Verificar `JANELA_INC_HORAS`, listar INCs raw via SQL

### Problema: "P1 falso positivo"
**Causa:** Heurística de OLA estourado muito sensível  
**Solução:** Ajustar thresholds em `config.py` + revalidar com manual QA

### Problema: "Customer monitor não detecta cliente"
**Causa:** Cliente sem tipo_usuario = "Nominal" ou <3 INCs em 30 dias  
**Solução:** Revisar TIPOS_USUARIO_SAUDE_CLIENTE, JANELA_CANDIDATOS_SAUDE_DIAS

### Problema: "Slack não recebe alerta"
**Causa:** Token inválido ou canal não existe  
**Solução:** Validar `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_CRITICA` em env vars

---

## 📚 10. Próximos Passos Recomendados

1. ✅ **Revisar esta análise** com PO e tech lead
2. 🎯 **Priorizar melhorias** conforme roadmap interno
3. 🧪 **Executar testes E2E** em staging
4. 📊 **Monitorar métricas** de saúde (queries SQL acima)
5. 🔄 **Feedback loop** com usuários (coordenadores)
6. 📖 **Manter documentação** sincronizada

---

**Fim da análise | Emerson Ramos | 2026-06-15**
