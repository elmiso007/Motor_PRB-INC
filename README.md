# Motor Prescritivo PRB-INC

Motor de análise automatizada de incidentes e recomendação de Problems para a infraestrutura Locaweb/KingHost. Detecta agrupamentos de incidentes (INCs) semanticamente relacionados, aplica a matriz de prioridade P1-P5 e prescreve ações antes que situações se tornem crises.

## O que faz

Sem este motor, o time de plantão precisaria notar manualmente que 5 incidentes isolados são, na verdade, o mesmo problema crescendo. O motor sistematiza essa detecção e antecipa crises em dois ciclos independentes:

| Prisma | Frequência | Entrada | Saída |
|---|---|---|---|
| **Preventivo** | A cada 1h | INCs das últimas 24h | Recomendação de abrir/repriorizar PRB ou monitorar |
| **Retrospectivo** | A cada 6h | PRBs encerrados nos últimos 14 dias | Veredicto de recidiva ou entrega validada |

O **Painel Change Team** (subproduto do ciclo retrospectivo) mantém um snapshot materializado de ~84 PRBs de uma força-tarefa específica, consumido pelo Superset/BI.

## Arquitetura resumida

```
extractor  →  analyzer  →  rules_engine  →  notifier / notifier_db
   (SQL)      (TF-IDF        (Matriz           (Slack + JSON +
              + DBSCAN)       P1-P5)            PostgreSQL)
```

Quatro camadas com imports unidirecionais:

```
Orquestração  →  main.py, validar_entregas.py, scheduler.py
Domínio       →  extractor, analyzer, rules_engine, customer_monitor,
                 validador_entrega, change_team, notifier, notifier_db
Utilitários   →  time_utils, db
Fundação      →  config, models
```

- **Dados de entrada:** ServiceNow (`lwsa.service_now_incidentes`, `lwsa.service_now_problemas`) + chamados de suporte (`dynamics.chamados`, `kinghost.chamados`)
- **Persistência de saída:** 8 tabelas `lwsa.motor_*` + `output/dashboard_state.json`
- **Notificações:** Slack via Bot Token API

## Tecnologias

- **Python 3.10+** — todo o código está em português (convenção intencional)
- **scikit-learn** — TF-IDF + DBSCAN para clustering semântico
- **psycopg2** — acesso ao data warehouse PostgreSQL
- **slack_sdk** — alertas via Slack Bot Token
- **Windows Task Scheduler** — agendamento externo (processo single-run, sem loop interno)

## Pré-requisitos

- Python 3.10+
- Acesso ao data warehouse PostgreSQL da Locaweb
- Arquivo `config.ini` com credenciais (veja [Configuração](#configuração))

## Instalação

```bash
cd "Motor PRB-INC"
pip install -r requirements.txt
```

**Banco de dados (executar uma vez):**

```sql
-- 1. Cria as tabelas de persistência
\i sql/motor_tables.sql

-- 2. Popula a lista do Change Team (~84 PRBs)
\i sql/seed_change_team.sql
```

## Configuração

Crie o arquivo `config.ini` em `../config.ini` (compartilhado com o locapredict) ou `./config.ini`:

```ini
[database]
server   = <host>
port     = 5432
database = <nome_db>
uid      = <usuario>
pwd      = <senha>

[slack]
bot_token = xoxb-...
channels  = C08C34VKB5Y,U06V8A8GF5L
```

### Variáveis de ambiente

| Variável | Padrão | Descrição |
|---|---|---|
| `USAR_MOCKS` | `false` | Usa dados sintéticos em vez do banco |
| `PERSISTIR_NO_BANCO` | `true` | Habilita persistência PostgreSQL |
| `SLACK_HABILITADO` | `true` | Habilita envio de alertas Slack |
| `SLACK_BOT_TOKEN` | config.ini | Sobrescreve o token do config.ini |
| `SLACK_CHANNELS` | config.ini | CSV de IDs de canais/usuários |
| `CLEANUP_TTL_HABILITADO` | `false` | Auto-purga execuções antigas |
| `JANELA_TTL_BANCO_DIAS` | `30` | Dias de retenção no banco |
| `LOG_LEVEL` | `INFO` | Nível de log |
| `CHANGE_TEAM_HABILITADO` | `true` | Habilita painel Change Team |

## Execução

**Modo mock (sem banco de dados):**

```bash
# PowerShell
$env:USAR_MOCKS = "true"
python main.py
```

**Produção:**

```bash
python main.py              # Prisma preventivo (roda uma vez e sai)
python validar_entregas.py  # Prisma retrospectivo (roda uma vez e sai)
```

**Windows Task Scheduler (produção):**

- `Motor-PRB.bat` → executa `main.py`, agendado a cada 1 hora
- `Motor-PRB-Validador.bat` → executa `validar_entregas.py`, agendado a cada 6 horas

## Testes

```bash
python -m pytest tests/ -v
```

~116 testes, todos em memória (sem banco), executam em menos de 1 segundo.

Cobertura: parsing do extractor, scoring do analyzer, matriz P1-P5 do rules_engine, queries bulk do customer_monitor, validador retrospectivo V3.1 e Change Team Phase 1.

## Estrutura do projeto

```
Motor PRB-INC/
├── main.py                  # Entry point — prisma preventivo
├── validar_entregas.py      # Entry point — prisma retrospectivo
├── scheduler.py             # Orquestrador do pipeline (executar_ciclo)
├── config.py                # Configuração central (thresholds, env vars)
├── models.py                # Dataclasses tipados (objetos de domínio)
├── extractor.py             # Ingestão de dados (PostgreSQL + mocks)
├── analyzer.py              # Clustering semântico (TF-IDF + DBSCAN)
├── rules_engine.py          # Motor de regras P1-P5
├── customer_monitor.py      # Avaliação de saúde do cliente
├── validador_entrega.py     # Validador retrospectivo de entregas
├── change_team.py           # Snapshot do Painel Change Team
├── notifier.py              # Alertas Slack + JSON dashboard
├── notifier_db.py           # Persistência PostgreSQL (lwsa.motor_*)
├── time_utils.py            # Helpers UTC/BRT
├── db.py                    # Gerenciador de conexão PostgreSQL
├── requirements.txt
├── Motor-PRB.bat            # Wrapper do Task Scheduler (preventivo)
├── Motor-PRB-Validador.bat  # Wrapper do Task Scheduler (retrospectivo)
├── sql/                     # DDL e seeds do banco
├── tests/                   # Testes unitários (~116)
├── output/                  # JSON de saída (dashboard_state.json)
├── logs/                    # Logs com rotação diária
└── docs/                    # Documentação detalhada
```

## Documentação detalhada

| Documento | Conteúdo |
|---|---|
| [docs/ARQUITETURA.md](docs/ARQUITETURA.md) | Estrutura em 4 camadas, decisões de design, pontos de extensão |
| [docs/MANUAL.md](docs/MANUAL.md) | Setup completo, operação, queries úteis, troubleshooting |
| [docs/REGRAS.md](docs/REGRAS.md) | Matriz de prioridade P1-P5 completa |
| [docs/SAUDE_DO_CLIENTE.md](docs/SAUDE_DO_CLIENTE.md) | Processo de avaliação de saúde do cliente |
| [docs/VALIDADOR_ENTREGA.md](docs/VALIDADOR_ENTREGA.md) | Validador retrospectivo V3.1 |
| [docs/DASHBOARD_CHANGE_TEAM.md](docs/DASHBOARD_CHANGE_TEAM.md) | Guia operacional do Painel Change Team |
| [GLOSSARIO.md](GLOSSARIO.md) | Termos ITSM/ITIL, SNow/Dynamics, motor, ML/NLP e Locaweb |
