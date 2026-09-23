# Motor Prescritivo PRB-INC

> Nota de diferenciação: este repositório é o projeto Motor Prescritivo PRB-INC, com foco em incidentes, clusterização e recomendações operacionais. Ele é diferente do projeto InsightFlow / Análise de Conversas e ROBO, que enfoca NPS, conversas e análise de detratores WOZ.

Projeto em Python para análise automatizada de incidentes e recomendação de ações operacionais. O motor agrupa incidentes semanticamente relacionados, aplica uma matriz de prioridade e sugere se vale abrir, repriorizar, monitorar ou acompanhar um problema.

## O que faz

Sem este motor, uma equipe de operação precisaria detectar manualmente que vários incidentes isolados apontam para a mesma causa raiz. O projeto sistematiza essa detecção e antecipa riscos em dois ciclos independentes:

| Prisma | Frequência | Entrada | Saída |
|---|---|---|---|
| **Preventivo** | A cada hora | INCs das últimas 24h | Recomendação de abrir, repriorizar ou monitorar |
| **Retrospectivo** | A cada 6h | PRBs encerrados nos últimos 14 dias | Veredicto de recidiva ou entrega validada |

O projeto também gera um painel operacional resumido para acompanhamento de PRBs e métricas de desempenho.

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

- **Dados de entrada:** incidentes e problemas de fontes internas do ambiente operacional
- **Persistência de saída:** tabelas de controle e dashboard em JSON
- **Notificações:** Slack via Bot Token API

## Tecnologias

- **Python 3.10+** — código organizado em módulos com convenção em português
- **scikit-learn** — TF-IDF + DBSCAN para clustering semântico
- **psycopg2** — acesso ao data warehouse PostgreSQL
- **slack_sdk** — alertas via Slack Bot Token
- **Windows Task Scheduler** — agendamento externo (processo single-run, sem loop interno)

## Pré-requisitos

- Python 3.10+
- Acesso ao PostgreSQL do ambiente operacional
- Arquivo `config.ini` com credenciais e ajuste de ambiente

## Instalação

```bash
cd "Motor PRB-INC"
pip install -r requirements.txt
```

**Banco de dados (executar uma vez):**

```sql
-- 1. Cria as tabelas de persistência
\i sql/motor_tables.sql

-- 2. Popula a lista do Change Team, quando aplicável
\i sql/seed_change_team.sql
```

## Configuração

Crie um arquivo `config.ini` na raiz do projeto ou em um diretório compartilhado do ambiente:

```ini
[database]
server   = <host>
port     = 5432
database = <nome_db>
uid      = <usuario>
pwd      = <senha>

[slack]
bot_token = xoxb-...
channels  = C1234567890,U0987654321
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
| `CHANGE_TEAM_HABILITADO` | `true` | Habilita painel de acompanhamento |

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

Os testes cobrem parsing do extractor, scoring do analyzer, matriz P1-P5 do rules_engine e validadores operacionais em memória.

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
├── change_team.py           # Snapshot do painel operacional
├── notifier.py              # Alertas Slack + JSON dashboard
├── notifier_db.py           # Persistência PostgreSQL
├── time_utils.py            # Helpers UTC/BRT
├── db.py                    # Gerenciador de conexão PostgreSQL
├── requirements.txt
├── Motor-PRB.bat            # Wrapper do Task Scheduler (preventivo)
├── Motor-PRB-Validador.bat  # Wrapper do Task Scheduler (retrospectivo)
├── sql/                     # DDL e seeds do banco
├── tests/                   # Testes unitários
├── output/                  # JSON de saída do dashboard
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
| [docs/DASHBOARD_CHANGE_TEAM.md](docs/DASHBOARD_CHANGE_TEAM.md) | Guia operacional do painel de acompanhamento |
| [GLOSSARIO.md](GLOSSARIO.md) | Termos ITSM/ITIL, SNow, Dynamics, motor e ML/NLP |
