# Manual de Uso — Motor Prescritivo PRB

> **Audiência:** operadores, time de plantão, coordenadores e times de suporte.
> Para entender a lógica de implementação, veja [ARQUITETURA.md](ARQUITETURA.md).
> Para as regras de negócio, veja [REGRAS.md](REGRAS.md).
> Para termos técnicos, veja [../GLOSSARIO.md](../GLOSSARIO.md).

Este documento mostra **como usar o motor no dia a dia**: setup inicial, comandos,
configuração, troubleshooting e consultas SQL úteis.

---

## 1. Setup inicial

### 1.1 Pré-requisitos

- **Python 3.10+**
- **Acesso ao PostgreSQL** do ambiente operacional
- **`config.ini`** com a seção `[database]` e, quando necessário, as chaves de Slack

Verificar Python:
```bash
python --version
```

### 1.2 Instalar dependências

```bash
cd "Motor PRB-INC"
pip install -r requirements.txt
```

### 1.3 Configurar `config.ini`

Crie um arquivo `config.ini` na raiz do projeto ou em um diretório compartilhado do ambiente:

```ini
[database]
server = <host_postgres>
port = 5432
database = <nome_do_banco>
uid = <usuario>
pwd = <senha>
```

Você também pode adicionar uma seção opcional para o Slack:

```ini
[slack]
bot_token = xoxb-...
channels  = C1234567890,U0987654321
```

Sem o `config.ini`, o motor falha em modo real. Para rodar sem banco, use `USAR_MOCKS=true` antes do comando.

### 1.4 Executar a DDL no banco (1x)

O motor persiste dados em várias tabelas de controle. Crie a estrutura com o script disponível em `sql/motor_tables.sql`.

**Opção A — via psql:**
```bash
psql -h <host> -U <user> -d <database> -f "Motor PRB-INC/sql/motor_tables.sql"
```

**Opção B — via DBeaver/pgAdmin:**
1. Abrir conexão no banco.
2. Abrir o arquivo `Motor PRB-INC/sql/motor_tables.sql`.
3. Selecionar tudo (`Ctrl+A`) e executar (`Ctrl+Enter`).

### 1.5 Permissões de banco necessárias

A conta usada pelo motor precisa ter acesso de leitura às fontes e acesso de gravação às tabelas operacionais do projeto.

Exemplo de permissões mínimas:

| Schema/Tabela | Permissões necessárias |
|---|---|
| `seu_schema.service_now_incidentes` | `SELECT` |
| `seu_schema.service_now_problemas` | `SELECT` |
| `seu_schema.chamados` | `SELECT` |
| `seu_schema.motor_*` | `INSERT, SELECT` |
| Sequências de tabelas do motor | `USAGE, SELECT` |

### 1.6 Verificar setup

Rodar uma execução de teste **em modo mock** (não toca o banco):

```bash
USAR_MOCKS=true python main.py
```

Se o comando executa com sucesso e gera resultados esperados, o setup está OK.

---

## 2. Como rodar o motor

### 2.1 Execução (single-run)

A aplicação **sempre** roda um único ciclo e encerra. A cadência é controlada
externamente — em produção, pelo Windows Task Scheduler. Não há loop interno.

```bash
python main.py
```

### 2.2 Modo mock vs. produção

| Modo | Quando usar | Como ativar |
|---|---|---|
| **Produção (default)** | Banco real, alertas reais | Sem env var — apenas `python main.py` |
| **Mock** | Desenvolvimento, testes, demo, validação local | `$env:USAR_MOCKS = "true"` (PowerShell) ou `USAR_MOCKS=true` (bash) |

### 2.3 Agendamento via Windows Task Scheduler (UI)

Padrão recomendado em produção: o Task Scheduler dispara `Motor-PRB.bat` a cada
**1 hora**. A vantagem é que, se uma execução falhar, a próxima ainda roda intacta.

---

## 3. Variáveis de ambiente

Exemplos de uso:

```bash
$env:USAR_MOCKS = "true"
$env:LOG_LEVEL = "DEBUG"
$env:SLACK_HABILITADO = "false"
```

As principais variáveis são:

- `USAR_MOCKS`
- `PERSISTIR_NO_BANCO`
- `SLACK_HABILITADO`
- `SLACK_BOT_TOKEN`
- `SLACK_CHANNELS`
- `LOG_LEVEL`
- `CHANGE_TEAM_HABILITADO`

---

## 4. Como ler os logs

Os logs são escritos em `logs/` e ajudam a validar execução, falhas e alertas.

```bash
Get-ChildItem logs
Get-Content logs\main-YYYY-MM-DD.log -Tail 60
```

Procure por:

- `Motor Prescritivo PRB iniciado`
- `Clusters formados`
- `Prescrições geradas`
- `Erro` ou `Exception`

---

## 5. Como interpretar o dashboard JSON

O arquivo `output/dashboard_state.json` deve refletir o último ciclo executado.

Campos úteis:

- `clusters` — lista de clusters detectados
- `prescricoes` — recomendações do rules engine
- `saude_clientes` — alertas de recorrência
- `execucao` — metadados e timestamp da execução

---

## 6. Como interpretar mensagens Slack

Mensagens de alerta devem identificar:

- severidade
- cluster ou problema
- contexto de risco
- ação sugerida

Se `SLACK_HABILITADO=false`, o sistema pode registrar a mensagem mas não enviá-la.

---

## 7. Queries SQL úteis

Exemplo de consulta de leitura do último ciclo:

```sql
SELECT *
FROM motor_execucao
ORDER BY id DESC
LIMIT 20;
```

Exemplo de verificação de clusters gerados:

```sql
SELECT *
FROM motor_cluster
ORDER BY id DESC
LIMIT 20;
```

---

## 8. Testes unitários

```bash
python -m pytest tests/ -v
```

Use esse comando para validar correções e mudanças de regra antes de liberar em produção.

---

## 9. Troubleshooting

### O motor não inicia

- confira se o Python 3.10+ está ativo;
- confira se `requirements.txt` foi instalado;
- confira o `config.ini` e as variáveis de ambiente.

### O banco não responde

- teste a conexão via cliente PostgreSQL;
- confirme as credenciais do `config.ini`;
- confirme permissões de leitura/escrita nas tabelas do projeto.

### O dashboard está vazio

- verifique se a execução terminou com sucesso;
- confirme o diretório de saída `output/`;
- veja os logs do ciclo.

---

## 10. Checklist de deploy em produção

- [ ] validar `config.ini`
- [ ] validar permissões do banco
- [ ] confirmar `requirements.txt`
- [ ] confirmar `USAR_MOCKS=false` em produção
- [ ] rodar um teste em mock
- [ ] rodar a aplicação em um ciclo real
- [ ] validar saída do dashboard
- [ ] confirmar logs e alertas

     agendada`.
   - Marcar `Se a tarefa falhar, reiniciar a cada:` **`5 minutos`** / tentar
     **`3`** vezes (retry automático).
   - `Se a tarefa em execução não terminar quando solicitado:` `Interromper a
     tarefa em execução` após **`1 hora`** (kill switch — ciclo normal leva ~3-5min).
7. **OK** → vai pedir a senha do Windows.

**Verificando depois:**

| Item                  | Como conferir |
|-----------------------|---------------|
| Task ativa            | `taskschd.msc` → coluna `Status` deve estar `Pronto` |
| Próxima execução      | Coluna `Próxima Execução` na lista |
| Histórico             | Selecionar a task → aba **Histórico** (ativar via "Habilitar Histórico" no painel direito se vier desabilitado) |
| Última saída do motor | `Motor PRB-INC\logs\motor-prb-{YYYY-MM-DD}.log` |
| Estado no banco       | `SELECT * FROM lwsa.motor_execucao ORDER BY timestamp_utc DESC LIMIT 5;` |
| Alertas no Slack      | Canal configurado em `[slack].channels` do `config.ini` |

**Modificar ou remover:** clique na task → painel direito → `Propriedades`
para editar ou `Excluir` para remover. O motor continua funcionando se a task
sumir — só para de ser agendado.

### 2.7 Agendamento do ValidadorEntrega (prisma retrospectivo)

O `main.py` (preventivo, 1h em PROD) e o `validar_entregas.py` (retrospectivo, 6h)
rodam em **entry-points separados**. Para ter os dois ativos, crie uma
**segunda task** no Task Scheduler. **Em PROD ambas vivem em** `\TarefasTrafego\`.

**Wrapper já criado:** `Motor-PRB-Validador.bat` na raiz do projeto:

```bat
@echo off
setlocal
set "PROJ=%~dp0"
set "VENV=C:\Users\emerson.ramos\Desktop\projetos\.venv"
set "USAR_MOCKS=false"
cd /d "%PROJ%"
"%VENV%\Scripts\python.exe" validar_entregas.py
endlocal & exit /b %ERRORLEVEL%
```

**Passo a passo na UI:**

1. **Criar Tarefa...** com nome `Motor PRB - Validador de Entrega`.
2. Aba **Geral:** marcar `Executar estando o usuário conectado ou não` +
   `Executar com privilégios mais altos`.
3. Aba **Disparadores → Novo...**:
   - `Diariamente`, começar hoje em `00:05:00` (fora do pico)
   - Configurações avançadas: `Repetir a tarefa a cada:` **`6 horas`**
   - Pela duração de: `1 dia` (Windows repete daily, então isso basta)
4. Aba **Ações → Nova...**:
   - Programa/script: `C:\Users\emerson.ramos\Desktop\projetos\Motor PRB-INC\Motor-PRB-Validador.bat`
   - Iniciar em: `C:\Users\emerson.ramos\Desktop\projetos\Motor PRB-INC`
5. Aba **Condições:** desmarcar restrições de bateria.
6. Aba **Configurações:**
   - Marcar `Executar tarefa o mais cedo possível após perder uma execução`
   - `Se a tarefa falhar, reiniciar a cada:` `15 minutos` / `3` tentativas
   - `Interromper se rodar mais que:` `1 hora` (kill switch — normalmente leva ~30s)
7. **OK** → vai pedir a senha do Windows.

**Disparos resultantes:** 00:05, 06:05, 12:05, 18:05 — alinhados com janelas
fora do pico operacional.

**Verificando:**

```sql
SELECT id, timestamp_utc, total_validacoes_entrega, duracao_ciclo_ms
FROM lwsa.motor_execucao
WHERE total_validacoes_entrega > 0
ORDER BY id DESC LIMIT 5;
```

Logs em `Motor PRB-INC\logs\validador-entrega-{YYYY-MM-DD}.log`.

---

## 3. Variáveis de ambiente

Todas configuráveis via env. Defaults em `config.py`.

### 3.1 Modo de execução

| Variável | Default | Descrição |
|---|---|---|
| `USAR_MOCKS` | `false` | `true` para dados sintéticos. `false` para banco real (default). |
| `PERSISTIR_NO_BANCO` | `true` | Liga/desliga gravação em `lwsa.motor_*`. |
| `CLEANUP_TTL_HABILITADO` | `false` | `true` se conta do motor tem permissão DELETE. |
| `JANELA_TTL_BANCO_DIAS` | `30` | Quantos dias manter no histórico (só se cleanup habilitado). |

### 3.2 Configuração do banco

| Variável | Default | Descrição |
|---|---|---|
| `CONFIG_PATH` | (busca em `../config.ini`, `./config.ini`) | Caminho do `config.ini`. |
| `CAMINHO_ARQUIVO_CONFIGURACAO` | mesmo | Alias do anterior. |

### 3.3 Slack

| Variável | Default | Descrição |
|---|---|---|
| `SLACK_WEBHOOK_URL` | _(vazio)_ | URL do webhook do Slack. Vazio = Slack desabilitado. |
| `SLACK_CANAL_CRITICOS` | `#prb-alertas` | Canal para alertas (sobrescreve default do webhook). |
| `SLACK_HABILITADO` | **`false`** | Liga/desliga Slack mesmo com webhook configurado. Default mudou em 2026-06-02 — quando desligado, motor prepara e *loga* a mensagem mas não envia (útil pra revisão antes de ativar). |

### 3.4 ServiceNow (não-usado hoje — placeholder)

O motor lê do data warehouse Postgres, não da API REST. As env vars abaixo são
placeholders para evolução futura caso a integração direta seja necessária:

| Variável | Default |
|---|---|
| `SERVICENOW_BASE_URL` | _(vazio)_ |
| `SERVICENOW_USER` | _(vazio)_ |
| `SERVICENOW_PASSWORD` | _(vazio)_ |

### 3.5 Logs

| Variável | Default | Descrição |
|---|---|---|
| `LOG_DIR` | `./logs` | Pasta onde gravar os logs diários. |
| `LOG_LEVEL` | `INFO` | Nível mínimo. Pode ser `DEBUG`, `INFO`, `WARNING`, `ERROR`. |

### 3.6 Dashboard

| Variável | Default | Descrição |
|---|---|---|
| `DASHBOARD_OUTPUT_PATH` | `./output/dashboard_state.json` | Caminho do JSON gerado a cada ciclo. |

### 3.7 Filtros de escopo (em `config.py`, não env)

Essas configs **não são env vars** — vivem em `config.py` porque mudam pouco e
afetam todas as consultas. Editar arquivo + reiniciar motor.

| Constante | Default | Descrição |
|---|---|---|
| `ORGANIZACOES_ATIVAS` | `("Locaweb",)` | Restringe INCs/PRBs/chamados às orgs listadas. Tupla vazia = sem filtro. |
| `LOGIN_CLIENTE_PADROES_EXCLUIDOS` | `("kinghost",)` | Substrings que descartam INCs cujo `login_cliente` casa (case-insensitive). |
| `TIPOS_USUARIO_SAUDE_CLIENTE` | `("Nominal",)` | Tipos aceitos pra Saúde do Cliente (INCs de monitoração ficam fora). |
| `JANELA_CANDIDATOS_SAUDE_DIAS` | `30` | Janela para identificar candidatos a Saúde. |
| `JANELA_VOLUMETRIA_PRE_DIAS` | `60` | Janela do volumetria pré do ValidadorEntrega. |
| `JANELA_CHAMADOS_DELTA_DIAS` | `14` | Janela do Δ de chamados (simétrica). |
| `LIMIAR_REDUCAO_CHAMADOS_PCT` | `-0.5` | Δ ≤ esse valor mostra ↓ no Slack (queda significativa). |
| `LIMIAR_AUMENTO_CHAMADOS_PCT` | `+0.5` | Δ ≥ esse valor mostra ↑ no Slack (subida significativa). |
| `TOP_EQUIPES_IMPACTADAS` | `7` | Top N times internos Locaweb no bloco "Times impactados" (V3.1). |

### 3.7 Exemplo `.env` (não commitar!)

```bash
# Produção real
USAR_MOCKS=false
PERSISTIR_NO_BANCO=true
CLEANUP_TTL_HABILITADO=false      # mude para true quando tiver GRANT DELETE

SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../...
SLACK_CANAL_CRITICOS=#noc-alertas
SLACK_HABILITADO=true

LOG_LEVEL=INFO
DASHBOARD_OUTPUT_PATH=/var/www/dashboard/motor-prb/state.json
```

---

## 4. Como ler os logs

### 4.1 Formato padrão

```
2026-05-27 12:36:13 | INFO    | scheduler              | Ciclo executado em 8104 ms (processamento: 3668 ms, Slack: 4436 ms).
```

Colunas separadas por `|`:
- **Timestamp** local (BRT): `YYYY-MM-DD HH:MM:SS`.
- **Severidade:** `INFO`, `WARNING`, `ERROR`, `DEBUG`.
- **Módulo:** quem emitiu a mensagem (`scheduler`, `extractor`, `analyzer`, etc.).
- **Mensagem:** texto narrativo em PT-BR.

### 4.2 Localização dos logs

```
Motor PRB-INC/
└── logs/
    ├── motor-prb-2026-05-27.log    ← arquivo do dia
    ├── motor-prb-2026-05-28.log    ← arquivo do dia seguinte
    └── ...
```

**Um arquivo por dia.** Nome inclui data (BRT local).

### 4.3 Mensagens-chave a observar

#### Início de ciclo
```
======================================================================
Iniciando ciclo do Motor Prescritivo PRB às 2026-05-27T15:30:00+00:00
```

#### Resumo de extração
```
INCs lidas (24h): 91.
Chamados (24h): 80.
PRBs abertos lidos: 2.
```

**Se algum desses ficar zero por muitos ciclos:** algo está errado com o ETL
upstream ou com permissões do banco.

#### Análise
```
CIs recorrentes detectados (>=2 INCs em 15d): {'srv-01': 6, ...}
Análise concluída: 5 clusters formados.
```

#### Prescrições
```
Prescrições geradas: 5 (críticas: 1).
```

**`(críticas: 0)` consistente** pode indicar:
- Nada crítico está acontecendo (bom).
- OU bug na lógica que está deixando passar críticos (ruim).

#### Saúde do Cliente
```
Clientes candidatos a avaliacao de saude (>=3 INCs na janela): 13 -> [...]
Saude de clientes avaliada: 13.
```

#### Saídas
```
Payload do dashboard gravado em ./output/dashboard_state.json.
Persistência Postgres OK: execucao_id=42 (5 clusters, 5 prescrições, 13 saúde).
Alertas Slack enviados: 4.
```

#### Fim de ciclo
```
Ciclo executado em 8104 ms (processamento: 3668 ms, Slack: 4436 ms).
Ciclo concluído: 5 clusters, 5 prescrições, 13 saúde de clientes, 0 erros.
```

### 4.4 Tipos de warnings importantes

#### Falha em fonte secundária (não-crítica)
```
WARNING | scheduler | Falha ao extrair chamados — seguindo sem cruzamento: ...
WARNING | scheduler | Falha ao listar PRBs abertos — sem sugestão de repriorização: ...
```

**O que isso significa:** o ciclo segue mas perde alguma capacidade. Investigar
se persistir.

#### Cleanup TTL desabilitado (esperado se sem GRANT DELETE)
```
WARNING | notifier_db | Falha no cleanup TTL — seguindo sem purgar: permission denied
```

**O que fazer:** ou ignorar (banco cresce devagar) ou pedir GRANT DELETE à DBA
e ativar `CLEANUP_TTL_HABILITADO=true`.

#### Webhook Slack ausente (dev)
```
INFO | notifier | [Slack desabilitado/sem webhook] :rotating_light::sos: ...
```

**O que isso significa:** `SLACK_WEBHOOK_URL` não configurado. Em produção,
sinal de bug de deploy. Em dev, esperado.

### 4.5 Tipos de erros importantes

#### Falha na fonte primária (motor abandonou ciclo)
```
ERROR | scheduler | Falha ao extrair INCs: ...
[stack trace]
```

**O que fazer:** verificar `config.ini`, conexão de rede, schema do banco. Motor
não processou nada nesse ciclo.

#### Falha na análise (bug interno)
```
ERROR | analyzer | Falha na clusterização sklearn: ...
[stack trace]
```

**O que fazer:** abrir bug. Stack trace mostra onde quebrou.

#### Falha na persistência Postgres
```
ERROR | notifier_db | Falha na persistência Postgres — JSON ainda foi gravado: ...
```

**O que isso significa:** Postgres caiu ou permissão negada. JSON ainda foi
gravado — front-end pode usar. Investigar Postgres.

### 4.6 Como filtrar logs

#### Apenas erros e warnings
```bash
grep -E "WARNING|ERROR" logs/motor-prb-2026-05-27.log
```

#### Apenas ciclos completos (resumos)
```bash
grep "Ciclo concluído" logs/motor-prb-2026-05-27.log
```

#### Ciclos lentos (acima de 30s)
```bash
grep "Ciclo executado em" logs/motor-prb-2026-05-27.log | awk '/[0-9]{5,} ms/'
```

#### Alertas Slack disparados
```bash
grep "Alertas Slack enviados:" logs/motor-prb-2026-05-27.log
```

---

## 5. Como interpretar o dashboard JSON

A cada ciclo, o motor grava `output/dashboard_state.json` (configurável via
`DASHBOARD_OUTPUT_PATH`).

### 5.1 Estrutura geral

```json
{
  "meta": {...},
  "clusters": [...],
  "prescricoes": [...],
  "saude_clientes": [...],
  "incidentes": [...]
}
```

**5 chaves de primeiro nível.** Cada uma é uma "tabela lógica".

### 5.2 Seção `meta`

```json
"meta": {
  "timestamp": "2026-05-27T15:30:00+00:00",
  "total_incs_lidas": 91,
  "total_chamados": 80,
  "total_clusters": 5,
  "total_prescricoes": 5,
  "total_saude_clientes": 13,
  "erros": []
}
```

| Campo | O que significa |
|---|---|
| `timestamp` | Quando o ciclo iniciou (UTC tz-aware) |
| `total_*` | Contagens de cada tipo |
| `erros` | Lista de strings de erro (vazio = ciclo limpo) |

### 5.3 Seção `clusters`

```json
"clusters": [
  {
    "cluster_id": "cluster-0",
    "nome": "vps servidor fora",
    "produto": "VPS",
    "servidor_principal": "vps-prod-01.locaweb.local",
    "qtd_incs": 6,
    "score_criticidade": 0.673,
    "score_ineficiencia": 1.0,
    "tem_solucao_contorno": false,
    "tempo_contorno_min_medio": 0,
    "chamados_relacionados": 17,
    "cis_recorrentes_15d": ["vps-prod-01.locaweb.local"],
    "termos_dominantes": ["vps", "servidor", "fora", "kernel", "panic"],
    "inc_ids": ["INC1000001", "INC1000002", ...]
  },
  ...
]
```

| Campo | O que significa |
|---|---|
| `score_criticidade` | 0.0-1.0. **Quanto maior, mais grave.** |
| `score_ineficiencia` | 0.0-1.0. **Quanto maior, mais o time está patinando.** |
| `chamados_relacionados` | Quantos chamados Locaweb+Kinghost para o produto deste cluster |
| `cis_recorrentes_15d` | Servidores com recorrência sistêmica detectada |
| `inc_ids` | IDs das INCs deste cluster (lookup em `incidentes`) |

### 5.4 Seção `prescricoes`

```json
"prescricoes": [
  {
    "cluster_id": "cluster-0",
    "acao": "ABRIR_PRB",
    "urgencia": "ALTA",
    "prioridade_sugerida": "P2",
    "prb_existente": null,
    "prioridade_atual_prb": null,
    "sugestao_repriorizacao": null,
    "justificativa": [
      "6 INCs sem contorno (limiar P2: 5).",
      "Gatilho proativo: 6 INCs P3 idênticas detectadas — sugere abertura de PRB antes que escale.",
      "CI(s) com recorrência em 15 dias: vps-prod-01.locaweb.local.",
      "17 chamados no último dia para o produto VPS (impacto real, Locaweb/Kinghost)."
    ]
  },
  ...
]
```

| Campo | Valores possíveis |
|---|---|
| `acao` | `ABRIR_PRB` / `REPRIORIZAR_PRB` / `MONITORAR` / `NENHUMA` |
| `urgencia` | `CRITICA` / `ALTA` / `MEDIA` / `BAIXA` / `PLANEJADO` |
| `prioridade_sugerida` | `P1` / `P2` / `P3` / `P4` / `P5` |
| `prb_existente` | ID do PRB matched (string) ou `null` |
| `justificativa` | Lista de bullets textuais auditáveis |

### 5.5 Seção `saude_clientes`

```json
"saude_clientes": [
  {
    "cliente_login": "cliente005",
    "qtd_incs_periodo": 22,
    "qtd_chamados_periodo": 18,
    "severidade_media": 0.477,
    "alerta_recorrencia_alta": true,
    "linha_do_tempo": [
      {"fonte": "ServiceNow", "tipo": "INC", "id": "INC...", "data": "...", ...},
      {"fonte": "Locaweb", "tipo": "Chamado", "id": "CAS-...", "data": "...", ...},
      ...
    ]
  },
  ...
]
```

| Campo | O que significa |
|---|---|
| `qtd_incs_periodo` | INCs nos últimos 6 meses |
| `qtd_chamados_periodo` | Chamados Locaweb/Kinghost nos últimos 6 meses |
| `severidade_media` | 0.0-1.0. P1=1.0 ... P5=0.0. **Quanto maior, mais grave.** |
| `alerta_recorrencia_alta` | `true` se ≥3 INCs E pelo menos 1 INC nos últimos 7 dias |
| `linha_do_tempo` | Eventos consolidados (INCs + chamados) ordem cronológica reversa |

### 5.6 Seção `incidentes`

```json
"incidentes": [
  {
    "inc_id": "INC1000001",
    "descricao_curta": "Servidor VPS fora — kernel panic",
    "produto": "VPS",
    "servidor": "vps-prod-01.locaweb.local",
    "login_cliente": "cliente001",
    "organizacao": "Locaweb",
    "prioridade_atual": "P3",
    "status": "Em Análise",
    "categoria": "Servidor",
    "subcategoria": "Indisponibilidade",
    "grupo_designado": "NOC",
    "abertura": "2026-05-27T15:00:00+00:00",
    "atualizacao": "2026-05-27T15:30:00+00:00",
    "qtd_atualizacoes": 14,
    "tem_solucao_contorno": false,
    "tempo_solucao_contorno_min": 0
  },
  ...
]
```

Todas as INCs do ciclo, **sem duplicação** (mesmo aparecendo em múltiplos
clusters). Front-end faz lookup por `inc_id`.

### 5.7 Como inspecionar o JSON manualmente

#### Resumo do estado
```bash
python -c "
import json
d = json.load(open('output/dashboard_state.json', encoding='utf-8'))
print('Timestamp:', d['meta']['timestamp'])
print('Clusters:', len(d['clusters']))
print('Prescricoes:', len(d['prescricoes']))
print('Alertas criticos:', sum(1 for p in d['prescricoes'] if p['urgencia']=='CRITICA'))
print('Saude clientes em alerta:', sum(1 for s in d['saude_clientes'] if s['alerta_recorrencia_alta']))
"
```

#### Listar prescrições críticas
```bash
python -c "
import json
d = json.load(open('output/dashboard_state.json', encoding='utf-8'))
for p in d['prescricoes']:
    if p['urgencia'] == 'CRITICA':
        print(f\"{p['cluster_id']}: {p['acao']} ({p['prioridade_sugerida']})\")
        for j in p['justificativa']:
            print(f'  - {j}')
"
```

---

## 6. Como interpretar mensagens Slack

### 6.1 Alerta de PRB crítico

Renderização típica:

```
🚨🆘 *Motor Prescritivo PRB — Alerta CRITICA*
_Ação sugerida: *ABRIR_PRB* | Prioridade: *P1*_

*Cluster:* checkout indisponivel contratacao
*Produto:* CAL
*Servidor/CI:* cal-frontend-03.locaweb.local
*INCs no cluster:* 3
*Score Criticidade:* 0.66 | *Ineficiência:* 0.38
*Chamados (24h, produto):* 16
*CIs recorrentes (15d):* cal-frontend-03.locaweb.local

*Justificativas:*
    • Contratação indisponível, sem solução de contorno total (P1).
    • CI(s) com recorrência em 15 dias: cal-frontend-03.locaweb.local.
    • 16 chamados no último dia para o produto CAL (impacto real, Locaweb/Kinghost).
```

### 6.2 Significado dos emojis

| Combinação | Significado |
|---|---|
| 🚨🆘 | Crítico + abrir PRB novo |
| 🚨🔧 | Crítico + repriorizar PRB existente |
| ⚠️🆘 | Alta + abrir PRB |
| ⚠️🔧 | Alta + repriorizar |
| 🔍🆘 | Média + abrir |
| 🔍🔧 | Média + repriorizar |
| 🌡️ | Saúde do Cliente — recorrência alta |

**Triagem visual:** olhe o emoji combinado para entender **tipo de problema** e
**tipo de ação** em 1 segundo.

### 6.3 Alerta de Saúde do Cliente

```
🌡️ *Saúde do Cliente — Recorrência Alta*
*Cliente:* `cliente005`
*INCs em 6 meses:* 22
*Chamados em 6 meses:* 18
*Severidade média:* 0.48
*Total de eventos consolidados:* 40
_Use o dashboard para ver a linha do tempo completa._
```

| Campo | O que olhar |
|---|---|
| `qtd_incs_periodo` + `qtd_chamados_periodo` | Volume total — quão "barulhento" é o cliente |
| `severidade_media` | Gravidade — 0.0 (rotineiro) a 1.0 (crítico) |
| `Total de eventos consolidados` | Tamanho da linha do tempo no dashboard |

**Cruzar volume + severidade:**
- Volume alto + severidade alta → atenção do gerente de conta.
- Volume alto + severidade baixa → "cliente ruidoso", acompanhar.
- Volume baixo + severidade alta → casos isolados graves, monitorar.

### 6.4 Quando NÃO chega alerta

O Slack é seletivo:
- **PRBs:** apenas `urgencia == "CRITICA"` (P1).
- **Saúde:** apenas `alerta_recorrencia_alta == true`.

Alertas P2, P3, P4, P5 **não vão para Slack** — só dashboard. Coordenador deve
revisar dashboard periodicamente para esses.

---

## 7. Queries SQL úteis

Queries para acompanhar o motor via Postgres. Rodar como qualquer SELECT.

### 7.1 Saúde do motor (último ciclo)

```sql
SELECT
    id,
    timestamp_utc,
    total_incs_lidas,
    total_chamados,
    total_clusters,
    total_prescricoes,
    total_saude_clientes,
    duracao_ciclo_ms,
    erros
FROM lwsa.motor_execucao
ORDER BY timestamp_utc DESC
LIMIT 1;
```

### 7.2 Motor está vivo?

```sql
SELECT
    NOW() - MAX(timestamp_utc) AS ultimo_ciclo_ha
FROM lwsa.motor_execucao;
```

**Se retornar > 1h15min:** motor está parado ou lento (cadência PROD é 1h
desde 2026-06-09 — antes o limiar era 20min com cadência de 15min).

### 7.3 Tendência de criticidade (últimos 7 dias)

> ⚠️ Postgres **9.2.19** (Locaweb — confirmado no go-live 2026-06-09) não
> suporta `COUNT(*) FILTER (WHERE ...)`, `ON CONFLICT`, `jsonb`, nem
> `CREATE INDEX IF NOT EXISTS`. Sintaxes introduzidas em 9.4+. Usamos
> `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` no lugar de COUNT FILTER, e
> DO block PL/pgSQL com checagem `IF NOT EXISTS` para idempotência.

```sql
SELECT
    DATE_TRUNC('day', e.timestamp_utc) AS dia,
    SUM(CASE WHEN p.urgencia = 'CRITICA' THEN 1 ELSE 0 END) AS qtd_criticos,
    SUM(CASE WHEN p.urgencia = 'ALTA'    THEN 1 ELSE 0 END) AS qtd_altas,
    SUM(CASE WHEN p.urgencia = 'MEDIA'   THEN 1 ELSE 0 END) AS qtd_medias
FROM lwsa.motor_execucao e
JOIN lwsa.motor_prescricao p ON p.execucao_id = e.id
WHERE e.timestamp_utc >= NOW() - INTERVAL '7 days'
GROUP BY dia
ORDER BY dia;
```

### 7.4 Performance do motor (lentidão crescente?)

```sql
SELECT
    DATE_TRUNC('hour', timestamp_utc) AS hora,
    AVG(duracao_ciclo_ms)::int AS media_ms,
    MAX(duracao_ciclo_ms) AS pico_ms,
    AVG(total_clusters)::int AS media_clusters
FROM lwsa.motor_execucao
WHERE timestamp_utc >= NOW() - INTERVAL '24 hours'
  AND duracao_ciclo_ms IS NOT NULL
GROUP BY hora
ORDER BY hora;
```

**Sinais de alerta:**
- `media_ms > 30000` (>30s) → motor lento, investigar.
- `pico_ms > 60000` (>1min) → ciclo individual problemático.

### 7.5 Clientes recorrentes do mês

```sql
SELECT
    cliente_login,
    COUNT(DISTINCT execucao_id) AS qtd_ciclos_em_alerta,
    MAX(qtd_incs_periodo) AS pico_incs,
    AVG(severidade_media)::numeric(4,3) AS sev_media_periodo
FROM lwsa.motor_saude_cliente sc
JOIN lwsa.motor_execucao e ON e.id = sc.execucao_id
WHERE e.timestamp_utc >= NOW() - INTERVAL '30 days'
  AND sc.alerta_recorrencia_alta = true
GROUP BY cliente_login
ORDER BY qtd_ciclos_em_alerta DESC
LIMIT 20;
```

### 7.6 CIs problemáticos (aparecem em muitos ciclos)

```sql
SELECT
    jsonb_array_elements_text(cis_recorrentes_15d::jsonb) AS ci,
    COUNT(DISTINCT execucao_id) AS qtd_ciclos
FROM lwsa.motor_cluster c
JOIN lwsa.motor_execucao e ON e.id = c.execucao_id
WHERE e.timestamp_utc >= NOW() - INTERVAL '14 days'
GROUP BY ci
HAVING COUNT(DISTINCT execucao_id) > 50
ORDER BY qtd_ciclos DESC;
```

**Nota:** se você estiver em Postgres 9.2/9.3 com tipo `json` (não `jsonb`),
substitua `jsonb_array_elements_text(... ::jsonb)` por
`json_array_elements_text(...)`.

### 7.7 Cleanup manual (se TTL desabilitado)

Para purgar execuções antigas manualmente (executar como conta com DELETE):

```sql
DELETE FROM lwsa.motor_execucao
WHERE timestamp_utc < NOW() - INTERVAL '30 days';
-- ON DELETE CASCADE remove clusters/prescrições/saúdes vinculados
```

Frequência recomendada: **1x por mês**.

---

## 8. Testes unitários

### 8.1 Como rodar

```bash
# Todos os testes
python -m pytest tests/

# Verbose
python -m pytest tests/ -v

# Apenas um arquivo
python -m pytest tests/test_rules_engine.py

# Apenas um teste específico
python -m pytest tests/test_rules_engine.py::TestP1Crise::test_contratacao_indisponivel_sem_contorno_vira_p1
```

### 8.2 O que cada arquivo testa

| Arquivo | Cobertura |
|---|---|
| `tests/test_extractor.py` | Parsers + queries SNow/Dynamics (`_parse_datetime`, `_parse_prioridade`, `_contar_atualizacoes`, `_detectar_contorno`, `listar_prbs_por_numero` para Change Team) |
| `tests/test_analyzer.py` | Scores (`_score_criticidade`, `_score_ineficiencia`, `_termos_dominantes`) |
| `tests/test_rules_engine.py` | Matriz P1-P5, gatilho proativo, repriorização, ação final |
| `tests/test_customer_monitor.py` | Bulk + slim queries, login canônico, anti alert-fatigue |
| `tests/test_validador_entrega.py` | V3.1 (veredicto, volumetria pré, Δ chamados, PRBs novos, times impactados) |
| `tests/test_change_team.py` | Phase 1 — snapshot atômico do Painel Change Team |

**Total:** ~116 testes, <1s de execução.

### 8.3 Quando rodar

- **Antes de fazer commit:** sempre.
- **Após mudança em `config.py`:** sempre (thresholds afetam testes).
- **Após mudança em qualquer módulo de domínio:** sempre.
- **Antes de subir para produção:** sempre.

### 8.4 Test de regressão importante

Há um teste explícito que **garante que o bug do "ra " (falso positivo de
Reclame Aqui em "fora") não volta**:

```python
def test_palavra_fora_NAO_casa_falsamente_em_ra(self):
    ...
    assert not any("Reclame Aqui" in j for j in presc.justificativa)
```

Se alguém mexer no `_qualquer_termo_no_cluster` removendo o word boundary,
esse teste falha e bloqueia o merge.

---

## 9. Troubleshooting

### Sintoma 1: Motor não inicia (erro de import)

```
ModuleNotFoundError: No module named 'X'
```

**Causa:** dependência faltando.

**Solução:**
```bash
pip install -r requirements.txt
```

### Sintoma 2: "config.ini não encontrado"

```
FileNotFoundError: config.ini não encontrado. Defina CONFIG_PATH ou coloque...
```

**Causa:** arquivo não está em `../config.ini` nem em `./config.ini`.

**Soluções:**
- Mover o arquivo para o local certo.
- OU definir env: `CONFIG_PATH=/caminho/completo/config.ini`.

### Sintoma 3: "permission denied for relation motor_execucao"

```
ERROR | notifier_db | Falha na persistência Postgres — JSON ainda foi gravado: ...
```

**Causa:** conta do motor não tem permissão.

**Solução:** seguir seção 1.5 para conceder GRANT INSERT/SELECT (e opcionalmente
DELETE).

### Sintoma 4: "Falha no cleanup TTL — permission denied"

```
WARNING | notifier_db | Falha no cleanup TTL — seguindo sem purgar: permission denied
```

**Causa:** conta do motor tem INSERT mas não DELETE.

**Soluções (escolha uma):**
- Conceder GRANT DELETE à conta + setar `CLEANUP_TTL_HABILITADO=true`.
- OU manter `CLEANUP_TTL_HABILITADO=false` (default) e DBA cuida manualmente
  (seção 7.7).

### Sintoma 5: "0 alertas Slack enviados" em produção

```
INFO | notifier | Alertas Slack enviados: 0.
```

**Causas possíveis:**
- `SLACK_WEBHOOK_URL` não configurado. Verificar env.
- `SLACK_HABILITADO=false`. Verificar.
- Nenhum cluster crítico nem cliente recorrente nesse ciclo (esperado em
  períodos calmos).

**Diagnosticar:**
```bash
grep "Slack" logs/motor-prb-$(date +%F).log | head -20
```

### Sintoma 6: Ciclo lento (>2min)

**Baseline esperada após calibração (2026-06-02):** 30-60s com índices criados.
Se passar de 2min, algo está errado.

**Diagnosticar via SQL:**
```sql
SELECT id, timestamp_utc, duracao_ciclo_ms, total_clusters, total_saude_clientes
FROM lwsa.motor_execucao
ORDER BY duracao_ciclo_ms DESC NULLS LAST
LIMIT 10;
```

**Causas possíveis:**
- **Índices ausentes no banco** (mais comum). Validar com:
  ```sql
  EXPLAIN (ANALYZE) SELECT idchamado FROM dynamics.chamados
   WHERE datacriacao >= NOW() - INTERVAL '24 hours';
  ```
  Espera ver `Index Scan using idx_dyn_chamados_datacriacao`. Se vir `Seq Scan`,
  pedir DBA criar os 4 índices (ver Apêndice de índices em ARQUITETURA.md ou no
  commit b0ff9c4..HEAD).
- Banco lento (rede, carga). Validar carga do DW com DBA.
- Volume alto de INCs (>800 na janela). Improvável — DW costuma ser estável.

### Sintoma 9: Python do venv "trava" sem produzir output

**Sintoma:** `python main.py` ou qualquer `python -c "..."` fica parado
indefinidamente sem retorno.

**Causa observada:** o arquivo
`.venv/Lib/site-packages/pip_system_certs.pth` executa `bootstrap()` em todo
startup do interpretador e em algumas máquinas Windows fica esperando o
Certificate Store responder.

**Workaround:**
```powershell
Move-Item .venv/Lib/site-packages/pip_system_certs.pth `
          .venv/Lib/site-packages/pip_system_certs.pth.disabled
```
Roda o motor (`python main.py`). Depois pode restaurar movendo de volta —
o problema é transiente.

### Sintoma 7: Cluster com classificação inesperada

**Exemplo:** cluster que esperaria ser P3 saiu como P1.

**Diagnosticar:**
1. Abrir `output/dashboard_state.json`.
2. Encontrar a prescrição do cluster.
3. **Ler `justificativa`** — explica por quê o motor decidiu.

Se justificativa não bate com o que você esperava, há bug na regra ou nos
termos heurísticos do `config.py`.

### Sintoma 8: Dashboard JSON desatualizado

**Verificar:**
```bash
ls -l output/dashboard_state.json
```

Compare com a hora atual. Se > 20 min atrás, motor não rodou.

**Verificar processo:**
```bash
ps aux | grep "python main.py"
```

Se não há processo, motor caiu. Verificar logs do supervisor.

---

## 10. Checklist de deploy em produção

### Antes de subir

- [ ] `pip install -r requirements.txt` na máquina/container.
- [ ] `config.ini` presente com seção `[database]`.
- [ ] DDL executada no banco (`sql/motor_tables.sql`).
- [ ] Conta do motor tem `SELECT` nos schemas `lwsa.*`, `dynamics.*`,
      `kinghost.*`, `lw_octadesk.*`.
- [ ] Conta do motor tem `INSERT, SELECT` em `lwsa.motor_*`.
- [ ] (Opcional) Conta tem `DELETE` em `lwsa.motor_execucao` + env
      `CLEANUP_TTL_HABILITADO=true`.
- [ ] Webhook Slack configurado em `SLACK_WEBHOOK_URL`.
- [ ] Canal Slack existe e webhook tem permissão.
- [ ] **DBA criou os 5 índices de performance** (sem eles, ciclo demora >1h):
      ```sql
      CREATE INDEX IF NOT EXISTS idx_sni_data_abertura
        ON lwsa.service_now_incidentes (data_abertura);
      CREATE INDEX IF NOT EXISTS idx_dyn_chamados_datacriacao
        ON dynamics.chamados (datacriacao);
      CREATE INDEX IF NOT EXISTS idx_kh_chamados_datacriacao
        ON kinghost.chamados (datacriacao);
      CREATE INDEX IF NOT EXISTS idx_sni_data_tipo
        ON lwsa.service_now_incidentes (data_abertura, tipo_usuario);
      -- V2 do ValidadorEntrega + enriquecimento via dynamics
      CREATE INDEX IF NOT EXISTS idx_dyn_chamados_inc
        ON dynamics.chamados (inc) WHERE inc IS NOT NULL;
      ```
- [ ] **DDL do ValidadorEntrega V2 + V3 executada** — adiciona **10 colunas**
      em `lwsa.motor_validacao_entrega` via DO block idempotente
      (`sql/motor_tables.sql`, seção "ALTER condicional"):
      8 da V2 (grupo_designado, data_abertura_prb, volumetria pré, Δ chamados)
      + 2 da V3 (qtd_prbs_novos_pos_resolucao, prbs_novos). Sem isso, a
      persistência do `validar_entregas.py` falha com `column "grupo_designado"
      does not exist`.
- [ ] **2ª tarefa no Task Scheduler para o ValidadorEntrega** apontando para
      `Motor-PRB-Validador.bat` (cadência 6h, em `\TarefasTrafego\`). Sem isso o validador nunca roda
      automaticamente — apenas o `main.py` (preventivo) é agendado por default.
- [ ] **DDL do Painel Change Team executada** — `motor_change_team` (master com
      `numero` UNIQUE + soft delete) e `motor_change_team_painel` (snapshot com
      18 colunas). Ambas em `sql/motor_tables.sql`. Sem isso o 3º bloco
      try/except do `validar_entregas.py` falha silenciosamente.
- [ ] **Ownership das tabelas Change Team transferido** para a conta do motor
      via `ALTER TABLE ... OWNER TO <conta>` (na Locaweb: `automatizacoes`).
      `TRUNCATE+RESTART IDENTITY` exige owner da sequência — só `GRANT` não basta.
      Erro típico se faltar: `must be owner of relation motor_change_team_painel_id_seq`.
- [ ] **Seed inicial dos 84 PRBs Change Team** via `sql/seed_change_team.sql`
      (DO block PL/pgSQL idempotente compatível com Postgres 9.2.19).
- [ ] **Backfill do espelho SNow para PRBs históricos** via
      `projetos/problemas/backfill.py`. `lwsa.service_now_problems` na Locaweb
      só replica PRBs recentes — sem o backfill, painel Change Team fica
      subdimensionado (ex.: 10/84 em vez de 84/84).

### Validação antes de agendar no Task Scheduler

Rodar manualmente em modo produção:

```bash
USAR_MOCKS=false python main.py 2>&1 | tee /tmp/motor-validacao.log
```

Verificar no log:
- [ ] `Modo mocks: False`.
- [ ] `INCs lidas (24h):` > 0 (a menos que seja meio da noite com pouquíssimo volume).
- [ ] `Persistência Postgres OK: execucao_id=...`.
- [ ] Sem `ERROR` (warnings esperados são OK).

Verificar Postgres:
```sql
SELECT COUNT(*) FROM lwsa.motor_execucao WHERE timestamp_utc > NOW() - INTERVAL '5 minutes';
```
Deve retornar 1.

### Subir o loop

Sob supervisor (systemd, Docker, etc.):

```bash
USAR_MOCKS=false python main.py
```

### Pós-deploy (primeiros 30 min)

- [ ] Verificar log: `tail -f logs/motor-prb-$(date +%F).log`.
- [ ] Confirmar 2 ciclos seguidos completos.
- [ ] Verificar Slack: alertas críticos chegando (se há clusters críticos).
- [ ] Verificar Postgres: `SELECT MAX(timestamp_utc) FROM lwsa.motor_execucao;`
      atualizado.
- [ ] Verificar JSON: `ls -l output/dashboard_state.json` atualizado.

### Monitoração contínua

Configurar alerta externo (Site24x7, Datadog, etc.) que verifica:

1. **Motor está vivo:**
   ```sql
   SELECT NOW() - MAX(timestamp_utc) FROM lwsa.motor_execucao;
   ```
   Alerta se > 20 min.

2. **Motor não está com lentidão crescente:**
   ```sql
   SELECT AVG(duracao_ciclo_ms) FROM lwsa.motor_execucao
   WHERE timestamp_utc > NOW() - INTERVAL '1 hour';
   ```
   Alerta se > 30000 (30s).

3. **Sem erros recorrentes:**
   ```sql
   SELECT COUNT(*) FROM lwsa.motor_execucao
   WHERE timestamp_utc > NOW() - INTERVAL '6 hours'
     AND jsonb_array_length(erros::jsonb) > 0;
   ```
   Alerta se > 2 (cadência PROD 1h preventivo → ~6 ciclos por janela; mais que 2 com erro = padrão sistêmico).

---

## Referências cruzadas

- **[ARQUITETURA.md](ARQUITETURA.md):** como o motor foi construído.
- **[REGRAS.md](REGRAS.md):** matriz oficial P1-P5 e critérios de negócio.
- **[../GLOSSARIO.md](../GLOSSARIO.md):** termos técnicos.
- **`sql/motor_tables.sql`:** DDL para executar no banco.
- **`config.py`:** todas as configs do motor.

---

_Documento mantido sob responsabilidade dos contribuidores do motor. Última
atualização: 2026-06-09 (refactor single-run + Task Scheduler 1h preventivo
e 6h validador + Painel Change Team em PROD)._