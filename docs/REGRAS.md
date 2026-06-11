# Regras de Negócio — Motor Prescritivo PRB

> **Audiência:** PO, coordenadores, analistas de negócio, auditoria. Para
> entender **como o motor funciona por dentro**, veja
> [ARQUITETURA.md](ARQUITETURA.md). Para **como usar**, veja [MANUAL.md](MANUAL.md).
> Para termos técnicos, veja [../GLOSSARIO.md](../GLOSSARIO.md).

Este documento contém **todas as regras de negócio** que o motor aplica para
classificar problemas, sugerir ações e monitorar clientes. É a referência
oficial para auditoria, calibração e validação de decisões.

**Fonte das regras:** documentação interna oficial da Locaweb sobre matriz de
priorização de Problemas (PRBs) e Incidentes (INCs), levantada em reunião com
Jéssica, Victor e Bruno.

---

## Sumário

1. [Matriz Oficial P1-P5](#1-matriz-oficial-p1-p5)
2. [P1 — Crise](#2-p1--crise)
3. [P2 — Alta](#3-p2--alta)
4. [P3 — Média](#4-p3--média)
5. [P4 — Baixa](#5-p4--baixa)
6. [P5 — Planejado](#6-p5--planejado)
7. [Gatilho proativo dos 5 P3](#7-gatilho-proativo-dos-5-p3)
8. [Sugestão de repriorização](#8-sugestão-de-repriorização)
9. [Saúde do Cliente](#9-saúde-do-cliente)
10. [Termos heurísticos (lista completa)](#10-termos-heurísticos-lista-completa)
11. [Como ajustar uma regra](#11-como-ajustar-uma-regra)
12. [Clusterização — regras de agrupamento](#12-clusterização--regras-de-agrupamento)
13. [Filtros de organização e login](#13-filtros-de-organização-e-login)
14. [ValidadorEntrega — prisma retrospectivo](#14-validadorentrega--prisma-retrospectivo)
15. [Painel Change Team — força-tarefa](#15-painel-change-team--força-tarefa)

---

## 1. Matriz Oficial P1-P5

A matriz determina **a urgência e o prazo** de cada tipo de problema. **5
níveis em ordem decrescente de gravidade:**

| Nível | Urgência | Prazo de avaliação | Prazo de solução |
|---|---|---|---|
| **P1** | Crise | Imediato | ASAP |
| **P2** | Alta | 1 dia útil | 4 dias úteis |
| **P3** | Média | 4 dias úteis | 20 dias úteis |
| **P4** | Baixa | (sem urgência) | (sem urgência) |
| **P5** | Planejado | Sob confirmação de Coordenador/PO | (sem urgência definida) |

### Como o motor avalia

1. **Cascata** P1 → P2 → P3 → P4 → P5: **a primeira regra que casa vence**.
2. **Gatilho proativo** pode **promover P3 para P2** se detectar ≥5 INCs P3
   idênticas (mesmo cluster).
3. **Sugestão de repriorização** comparando PRB já aberto vs. realidade atual.

### Como a cascata é implementada

No código, em `rules_engine.py:_avaliar_cascata`:

```python
for urgencia, avaliador in [
    ("CRITICA", _avaliar_p1),   # tentativa 1
    ("ALTA", _avaliar_p2),       # tentativa 2 se P1 não casou
    ("MEDIA", _avaliar_p3),
    ("BAIXA", _avaliar_p4),
]:
    resultado = avaliador(cluster)
    if resultado:
        return urgencia, ..., resultado
# Default: P5 ou fallback P4
```

**Princípio:** **a regra mais grave aplicável é a que prevalece**. Cluster que
satisfaz P1 e P3 simultaneamente é classificado P1.

---

## 2. P1 — Crise

### Definição oficial

> **P1 (Crise — Resolução ASAP):**
> - Reclame Aqui sem solução de contorno **COM** OLA estourado, **OU**
> - Contratação Indisponível (sem solução contorno total), **OU**
> - Funcionalidade do CAL/Central do Cliente/Painel do Produto Indisponível
>   Total, **OU**
> - Risco para o negócio / Falha de segurança.

### Critérios implementados

#### Critério P1.A — Reclame Aqui + sem contorno + OLA estourado

**Condições (todas):**
1. Cluster contém termos de **Reclame Aqui** em qualquer INC.
2. **Todas** as INCs do cluster estão sem solução de contorno.
3. **OLA estourado** (heurística: `score_ineficiencia >= 0.6 AND qtd_sem_contorno > 0`).

**Justificativa que aparece no Slack/dashboard:**
> *"Reclame Aqui sem solução de contorno e OLA estourado (P1)."*

**Limitação atual:** o banco do motor não recebe o campo `breach_time` real do
ServiceNow. Por isso, "OLA estourado" é **heurística** baseada em score de
ineficiência alto + presença de INCs sem contorno. Quando o ETL upstream
passar a expor `breach_time`, substituir essa heurística por checagem direta.

#### Critério P1.B — Contratação indisponível sem contorno

**Condições (todas):**
1. Cluster contém termos de **contratação** (carrinho, checkout, pagamento, CAL,
   Central do Cliente, Painel do Produto, etc.).
2. Cluster contém termos de **indisponibilidade total** (fora do ar, não pinga,
   indisponível, sem acesso, tudo fora, etc.).
3. **Todas** as INCs do cluster estão sem solução de contorno.

**Justificativa:**
> *"Contratação indisponível, sem solução de contorno total (P1)."*

**Por que P1:** contratação indisponível **impede que clientes paguem**.
Impacto financeiro direto + impacto reputacional. Crise por definição.

#### Critério P1.C — CAL/Central/Painel indisponível total

**Condições (todas):**
1. Cluster contém termos de **indisponibilidade total**.
2. `cluster.produto` é **CAL**, **Central do Cliente** ou **Painel do Produto**.

**Justificativa:**
> *"Funcionalidade do [produto] indisponível total (P1)."*

**Por que P1:** funcionalidades core dos clientes. Indisponibilidade total
impede o cliente de usar.

#### Critério P1.D — Risco de segurança

**Condições (qualquer uma):**
1. Cluster contém **qualquer** termo de risco de segurança (vazamento, invasão,
   ataque, ransomware, credencial exposta, leak).

**Justificativa:**
> *"Risco para o negócio / falha de segurança detectado (P1)."*

**Por que P1 isolado:** segurança **por definição** é crise. Não importa
volume — uma única menção de ransomware merece resposta imediata.

### Exemplos práticos

| Cenário | Casa P1? | Critério |
|---|---|---|
| 3 INCs sem contorno mencionando "reclame aqui" + score_ineficiencia=0.8 | ✅ | P1.A |
| 5 INCs com termos "checkout indisponível" + "não pinga" + todas sem contorno | ✅ | P1.B |
| 2 INCs sobre "CAL fora do ar" | ✅ | P1.C |
| 1 INC mencionando "possível vazamento de credenciais" | ✅ | P1.D |
| 10 INCs sobre "lentidão pontual" (sem indisponibilidade) | ❌ | Nenhum critério P1 |

---

## 3. P2 — Alta

### Definição oficial

> **P2 (Alta — Avaliação em 1 dia útil / Solução em 4 dias úteis):**
> - Reclame Aqui sem solução de contorno (sem OLA estourado).
> - Contratação Indisponível Parcial (sem solução contorno parcial).
> - **Sem solução de contorno E ≥ 5 incidentes associados.**
> - **Com solução de contorno E ≥ 100 INCs associadas OU contorno ≥ 1 hora.**
> - Funcionalidade do CAL/Central/Painel Indisponível Parcial OU Ferramenta
>   Interna Total.
> - Impacto na instalação de novos servidores dedicados.

### Critérios implementados

#### Critério P2.A — Reclame Aqui com INCs sem contorno

**Condições:**
1. Cluster contém termos de **Reclame Aqui**.
2. **Pelo menos 1** INC do cluster está sem contorno.

**Justificativa:**
> *"Reclame Aqui com INCs sem solução de contorno (P2)."*

**Diferença vs. P1.A:** mais relaxado. Aqui basta 1 INC sem contorno, não
todas. E não exige OLA estourado.

#### Critério P2.B — Volume sem contorno ≥ 5

**Condições:**
1. `qtd_sem_contorno >= LIMIAR_P2_INCS_SEM_CONTORNO` (default **5**).

**Justificativa:**
> *"5 INCs sem contorno (limiar P2: 5)."*

**Por que P2:** 5 INCs sem contorno conhecido sinaliza padrão sistêmico. Não
crise (não há ainda evidência de OLA estourado ou indisponibilidade), mas
**alta atenção**.

**Threshold:** `config.LIMIAR_P2_INCS_SEM_CONTORNO = 5`.

#### Critério P2.C — Volume com contorno ≥ 100

**Condições:**
1. `qtd_com_contorno >= LIMIAR_P2_INCS_COM_CONTORNO` (default **100**).

**Justificativa:**
> *"100 INCs com contorno (limiar P2: 100)."*

**Por que P2:** mesmo com contorno, 100+ incidentes representam **carga
operacional alta** + impacto cumulativo nos clientes. Vale virar PRB para
resolver definitivamente.

**Threshold:** `config.LIMIAR_P2_INCS_COM_CONTORNO = 100`.

#### Critério P2.D — Tempo de contorno ≥ 60 min

**Condições:**
1. Cluster **tem solução de contorno** (maioria das INCs).
2. `tempo_contorno_min_medio >= LIMIAR_P2_CONTORNO_MIN` (default **60** min).

**Justificativa:**
> *"Tempo médio de contorno 60min >= 60min (P2)."*

**Por que P2:** contorno demorado (≥1h) é custo operacional alto. Vale resolver
o problema raiz.

**Threshold:** `config.LIMIAR_P2_CONTORNO_MIN = 60`.

#### Critério P2.E — Impacto em instalação de novos servidores dedicados

**Condições:**
1. Nome do cluster contém "instalacao" ou "instalação".
2. Pelo menos uma INC do cluster tem `produto` contendo "dedicado".

**Justificativa:**
> *"Impacto na instalação de novos servidores dedicados (P2)."*

**Por que P2:** instalação de servidor dedicado é **revenue-critical**. Falha
impacta entrega de produto pago.

### Exemplos práticos

| Cenário | Casa P2? | Critério |
|---|---|---|
| 6 INCs sem contorno sobre kernel panic | ✅ | P2.B |
| 120 INCs sobre "lentidão", todas com workaround simples | ✅ | P2.C |
| Cluster "instalação dedicado provisionamento travado" (2 INCs) | ✅ | P2.E |
| 4 INCs sem contorno | ❌ | < 5, não casa P2.B |

---

## 4. P3 — Média

### Definição oficial

> **P3 (Média — Avaliação em 4 dias úteis / Solução em 20 dias úteis):**
> - Reclame Aqui com solução de contorno.
> - **Sem solução de contorno E < 5 incidentes associados.**
> - **Com solução de contorno E entre 20 e 100 incidentes associados.**
> - Com solução de contorno entre 10 min e 1 hora.
> - Funcionalidade de Ferramenta Interna Indisponível Parcial.

### Critérios implementados

#### Critério P3.A — Reclame Aqui com contorno

**Condições:**
1. Cluster contém termos de **Reclame Aqui**.
2. Cluster **tem solução de contorno** (maioria das INCs).

**Justificativa:**
> *"Reclame Aqui com solução de contorno (P3)."*

#### Critério P3.B — Volume sem contorno entre 1 e 4

**Condições:**
1. `0 < qtd_sem_contorno < LIMIAR_P2_INCS_SEM_CONTORNO` (entre 1 e 4).

**Justificativa:**
> *"3 INCs sem contorno (< 5) → P3."*

**Por que P3:** começou a aparecer padrão mas ainda pouco volume. Sinal precoce.

#### Critério P3.C — Volume com contorno na faixa 20-99

**Condições:**
1. `LIMIAR_P3_INCS_COM_CONTORNO_MIN <= qtd_com_contorno < LIMIAR_P3_INCS_COM_CONTORNO_MAX`
   (default 20 a 99).

**Justificativa:**
> *"55 INCs com contorno (faixa 20-100) → P3."*

**Thresholds:**
- `config.LIMIAR_P3_INCS_COM_CONTORNO_MIN = 20`.
- `config.LIMIAR_P3_INCS_COM_CONTORNO_MAX = 100`.

#### Critério P3.D — Tempo de contorno na faixa 10-59 min

**Condições:**
1. Cluster tem solução de contorno.
2. `LIMIAR_P3_CONTORNO_MIN_INICIO <= tempo_contorno_min_medio < LIMIAR_P3_CONTORNO_MIN_FIM`
   (default 10 a 59).

**Justificativa:**
> *"Tempo médio de contorno 30min (faixa P3)."*

**Thresholds:**
- `config.LIMIAR_P3_CONTORNO_MIN_INICIO = 10`.
- `config.LIMIAR_P3_CONTORNO_MIN_FIM = 60`.

### Exemplos práticos

| Cenário | Casa P3? | Critério |
|---|---|---|
| 25 INCs com contorno de 30 min cada | ✅ | P3.C + P3.D |
| 2 INCs sem contorno | ✅ | P3.B (entre 1 e 4) |
| 1 INC reclame aqui com contorno | ✅ | P3.A |
| 5 INCs sem contorno | ❌ | Vira P2 (≥5) |

---

## 5. P4 — Baixa

### Definição oficial

> **P4 (Baixa):** Com solução de contorno **E** (< 20 incidentes **OU** Solução
> de Contorno < 10 minutos).

### Critério implementado

#### Critério P4.A — Com contorno + baixa intensidade

**Condições (AND da primeira + OR das outras):**
1. Cluster **tem solução de contorno** (obrigatório).
2. **`qtd_com_contorno < LIMIAR_P4_INCS_COM_CONTORNO_MAX`** (default **20**), **OU**
3. **`tempo_contorno_min_medio < LIMIAR_P4_CONTORNO_MAX_MIN`** (default **10**) com `tempo > 0`.

**Justificativa:**
> *"P4: 5 INCs com contorno (< 20)."*
> *"P4: contorno rápido (5min < 10)."*
> *"P4: 5 INCs com contorno (< 20) e contorno rápido (5min < 10)."*

**Thresholds:**
- `config.LIMIAR_P4_INCS_COM_CONTORNO_MAX = 20`.
- `config.LIMIAR_P4_CONTORNO_MAX_MIN = 10`.

**Por que P4:** problema conhecido + facilmente mitigado. Acompanhar mas sem
urgência.

### Exemplos práticos

| Cenário | Casa P4? |
|---|---|
| 5 INCs com contorno de 5 min cada | ✅ |
| 18 INCs com contorno de 8 min cada | ✅ |
| 25 INCs com contorno de 30 min cada | ❌ (vira P3 — entre faixas) |
| 5 INCs sem contorno | ❌ (não tem contorno) |

### Limitação consciente

**O tempo de contorno (`tempo_solucao_contorno_min`) é hoje hardcoded em 0** no
extractor real — o motor não extrai esse valor do banco. Significa que o
critério P4 de "contorno < 10 min" raramente dispara em produção (cai para o
critério de volume "< 20 INCs"). Mitigação: derivar do texto da resolução via
NLP — não está no MVP.

---

## 6. P5 — Planejado

### Definição oficial

> **P5 (Planejado):** Erro conhecido, mediante confirmação do Coordenador/PO,
> sem atuação para resolução definitiva e com Solução de Contorno existente.

### Critério implementado

**P5 não é classificação automática.** É o **default da cascata** quando
nenhuma regra P1-P4 casa, com condições adicionais:

1. Cluster **tem solução de contorno**.
2. `qtd_incs < 5`.

**Justificativa:**
> *"Erro conhecido com solução de contorno e baixo volume — aguarda
> confirmação de Coordenador/PO para P5."*

**Decisão de design:** o motor **sugere** P5 mas **não decide sozinho**. Texto
explícito de "aguarda confirmação" sinaliza ao coordenador que essa
classificação requer decisão humana.

**Por que essa restrição:** P5 = "estamos cientes do erro e decidimos não
consertar agora". Decisão de **produto/priorização**, não de máquina.

### Fallback genérico

Se as condições P5 não baterem **e** nenhuma regra P1-P4 casou:

**Justificativa:**
> *"Nenhuma regra mais grave acionada — classificado como P4."*

Cluster recebe **P4 default**. Cenário improvável na prática — quase todo
cluster bate em alguma regra.

---

## 7. Gatilho proativo dos 5 P3

### Requisito original

> *"Se o motor detectar 5 ou mais INCs do tipo P3 idênticas/do mesmo assunto,
> ele deve disparar proativamente a sugestão de abertura de um PRB,
> antecipando-se antes que o volume escale ou afete mais clientes."*

### Mecânica

**Após a cascata classificar o cluster:**

1. Motor conta quantas INCs do cluster estão **atualmente em P3** (campo
   `prioridade_atual` na INC, não no veredicto da cascata).
2. Se `qtd_p3_idênticas >= LIMIAR_PRB_PROATIVO_INCS_P3` (default **5**):
   - **Adiciona justificativa textual** ao cluster.
   - **Se a cascata classificou como P3, promove para P2.**
   - Se já era P1/P2, mantém prioridade (só adiciona justificativa).
   - Se era P4/P5, mantém (só adiciona justificativa).

**Threshold:** `config.LIMIAR_PRB_PROATIVO_INCS_P3 = 5`.

### Justificativas geradas

Quando dispara:
> *"Gatilho proativo: 6 INCs P3 idênticas detectadas — sugere abertura de PRB
> antes que escale."*

Quando promove P3 → P2:
> *"Prioridade elevada para P2 pelo gatilho proativo."*

### Por que **só promove até P2**

Decisão deliberadamente conservadora:
- **P3 → P2:** promove. Sinal volumétrico forte.
- **P2 → P1:** **não promove.** P1 exige critério qualitativo (Reclame Aqui,
  contratação, segurança), não só volume.
- **P4/P5 → P2:** **não promove.** Garante que P4/P5 mantém status mesmo com
  P3s históricas idênticas.

### Exemplo prático

**Cluster com 6 INCs todas atualmente em P3, com contorno de 30 min:**

1. Cascata classifica P3 (faixa P3.D — tempo 10-60 min).
2. Gatilho proativo: 6 P3 idênticas ≥ 5 → promove para P2.
3. **Resultado:** prioridade sugerida = P2, com **2 justificativas**:
   - "Tempo médio de contorno 30min (faixa P3)."
   - "Gatilho proativo: 6 INCs P3 idênticas detectadas..."
   - "Prioridade elevada para P2 pelo gatilho proativo."

---

## 8. Sugestão de repriorização

### Requisito original

> *"O sistema deve analisar os PRBs que já estão abertos no produto. Se um PRB
> atual for P3, mas o motor identificar que ele já acumulou novos incidentes
> que batem com os critérios de P2, o motor deve sugerir explicitamente:
> 'Mudar prioridade de P3 para P2'."*

### Mecânica

**Após a cascata + gatilho proativo:**

1. **Buscar PRB correspondente** via match por (`produto` + `servidor`) entre
   cluster e PRBs abertos.
2. **Comparar prioridade do PRB existente vs. prioridade sugerida pelo motor:**
   - Se nova prioridade for **mais grave** (P3 → P1, P3 → P2, P2 → P1), **sugere upgrade**.
   - Se for **igual ou menos grave**, **não sugere** (mantém prioridade atual).

### Match por (produto + servidor)

```python
prb_matched = primeiro PRB onde:
    prb.produto.lower() == cluster.produto.lower()
    AND prb.servidor.lower() == cluster.servidor_principal.lower()
```

**Primeiro match vence.** Se há 2 PRBs com mesmo (produto, servidor), só o
primeiro é considerado. Em produção real isso é raro — dois PRBs idênticos
seria erro de processo.

### Comparação de prioridades

Mapa de ordem (em `rules_engine.ORDEM_PRIORIDADE`):

```
P1 = 1   (mais grave)
P2 = 2
P3 = 3
P4 = 4
P5 = 5   (menos grave)
```

Comparação: `if nova_int < atual_int` → upgrade sugerido.

### Justificativa gerada

> *"Mudar prioridade de P3 para P2 (PRB PRB0000123)."*

Inclui:
- Prioridade atual do PRB.
- Prioridade sugerida.
- ID do PRB para click-through.

### Por que **só upgrade, nunca downgrade**

Decisão consciente:
1. **Conservadorismo operacional.** Rebaixar prioridade pode fazer time perder
   foco em problema que vai voltar a piorar.
2. **Visibilidade.** Manter P2 com pouca atividade atual chama atenção do
   coordenador para **fechar** o PRB (ou rebaixar manualmente).
3. **Histórico.** PRB é sobre **causa raiz**. Mesmo que sintoma diminua, causa
   pode persistir.

### Ações resultantes

Quando há PRB correspondente:

| Condição | Ação |
|---|---|
| Sugestão de upgrade existe | `REPRIORIZAR_PRB` (sugere mudança) |
| Sugestão de upgrade NÃO existe (PRB já na prioridade certa ou inferior) | `MONITORAR` (PRB já cuidando) |

Quando NÃO há PRB correspondente:

| Condição | Ação |
|---|---|
| Cluster em P1 ou P2 | `ABRIR_PRB` (novo) |
| Cluster em P3 | `MONITORAR` (sem urgência de abrir) |
| Cluster em P4/P5 | `NENHUMA` (não age) |

### Exemplo prático

**Cluster:** 6 INCs sem contorno em VPS, classificado P2.
**PRB existente:** `PRB0000123`, produto=VPS, servidor=vps-prod-01, prioridade=P3.

1. **Match:** PRB matched (mesmo produto + servidor).
2. **Comparação:** P3 atual vs. P2 sugerido → P2 é mais grave → sugere upgrade.
3. **Ação:** `REPRIORIZAR_PRB`.
4. **Slack:**
   > *"Mudar prioridade de P3 para P2 (PRB PRB0000123)."*

---

## 9. Saúde do Cliente

### Requisito original

> *"Criar um módulo paralelo de monitoramento por Cliente Login. Se um cliente
> tiver ≥ 3 INCs nos últimos 6 meses, o sistema deve gerar um alerta de
> recorrência alta e consolidar a linha do tempo desse cliente (histórico de
> chamados do Dynamics e INCs do ServiceNow) para poupar o trabalho manual de
> busca dos analistas."*

### Critério de avaliação

**Fase 1 — Identificação de candidatos** (`customer_monitor.gerar_saude_clientes`):

A identificação tem 3 filtros aplicados via **SQL agregado** (`GROUP BY login_canonico`):

1. **Janela de 30 dias** (`JANELA_CANDIDATOS_SAUDE_DIAS`) — cliente real raramente
   acumula 3 INCs em 24h; ampliamos para capturar recorrência natural. Janela
   afeta APENAS a Saúde do Cliente — clusterização/prescrição continuam em 24h.
2. **Tipo de usuário Nominal** (`TIPOS_USUARIO_SAUDE_CLIENTE = ("Nominal",)`) —
   só INCs abertas por analista em nome de cliente real entram. INCs
   `tipo_usuario = 'Integração'` (~92% do volume, geradas por Zabbix/Nagios)
   têm `login_cliente` vazio por design e não fazem sentido aqui.
3. **Login canônico** — `login_cliente` é normalizado via
   `sql_normalizar_login_cliente` antes do GROUP BY, unificando formatos:
   `username (Cód. NNN)`, `ficha=NNN`, dígitos puros, texto puro.
4. **Limiar de volume** — `>= LIMIAR_INCS_SAUDE_CLIENTE` (default **3**)
   INCs por cliente canônico na janela.

**Fase 2 — Avaliação (bulk + slim):**

Uma única query `SELECT ... WHERE login_canonico IN (...) AND data_abertura >=
NOW() - 6mo` traz histórico de TODOS os candidatos. O mesmo padrão se aplica a
chamados (1 query Locaweb + 1 KingHost). Reduziu de ~36 round-trips por ciclo
para 3 (~5min → ~30s na fase). Métodos: `listar_incidentes_para_saude` e
`listar_chamados_para_saude`.

Colunas trazidas no SELECT slim: `numero, descricao_curta, prioridade, produto,
data_abertura, servidor, login_canonico, tem_contorno` — esta última
pré-computada via regex SQL com a mesma lista de termos da função Python
`_detectar_contorno`.

### Veredicto: `alerta_recorrencia_alta`

Disparado **se ambas** as condições:

1. **Volume:** `qtd_incs_periodo >= LIMIAR_INCS_SAUDE_CLIENTE` (3 INCs em 6m).
2. **Recência:** pelo menos 1 INC **nos últimos 7 dias** (`JANELA_RECENCIA_ALERTA_DIAS`).

### Por que critério de recência (anti alert-fatigue)

**Sem recência:** cliente que teve 5 INCs em janeiro continuaria sendo
alertado todo dia até julho — 6 meses de alertas idênticos. Slack inutilizado.

**Com recência:**
- Cliente com 5 INCs em janeiro e **sem nova INC em fevereiro** → para de
  alertar.
- Cliente abre nova INC em março → alerta volta automaticamente.

**Operacional:** "cliente acalmou" não enche Slack. "Cliente voltou a abrir
incidente" volta a alertar.

### Severidade média

Cálculo: média ponderada das prioridades das INCs do cliente.

**Mapeamento** (`config.PESO_PRIORIDADE_SEVERIDADE`):
- P1 = 1.00
- P2 = 0.75
- P3 = 0.50
- P4 = 0.25
- P5 = 0.00

**Resultado:** valor 0.0-1.0. Quanto maior, mais grave.

### Como cruzar volume + severidade (operacional)

| Volume | Severidade | Interpretação |
|---|---|---|
| Alto + alta | **Atenção do gerente de conta** |
| Alto + baixa | "Cliente ruidoso", acompanhar |
| Baixo + alta | Casos isolados graves, monitorar |
| Baixo + baixa | Não dispara alerta |

### Linha do tempo consolidada

Para cada cliente em alerta, motor consolida **eventos cronológicos** de duas
fontes:

```
[mais recente]
🟢 INC1000050  ServiceNow      2h atrás · P3
   "Servidor VPS fora — kernel panic"

💬 CAS-500023  Locaweb         3h atrás
   "Servidor lento"

🟢 INC1000047  ServiceNow      8h atrás · P3
   "Servidor VPS fora — kernel panic"

💬 CAS-500012  Kinghost        2 dias atrás
   "Não consigo acessar"

🟢 INC0900150  ServiceNow      1 mês atrás · P2
   "Checkout indisponível"
[mais antigo]
```

**Disponível no dashboard JSON** (não no Slack — Slack só mostra resumo
numérico).

### Roteamento por organização

| Coluna `organizacao` na INC/PRB | Tabela de chamados consultada |
|---|---|
| "Locaweb" | `dynamics.chamados` (+ JOIN em `lw_octadesk.classificacoes` para produto) |
| "Kinghost" | `kinghost.chamados` (produto = `fila` direto) |

Configurável em `config.TABELAS_CHAMADOS_POR_ORGANIZACAO`. Adicionar nova
organização = editar dict, zero código.

---

## 10. Termos heurísticos (lista completa)

Listas de palavras-chave usadas pelas regras P1-P5. Match via **word boundary
regex** (`\b...\b`) — termos só casam como **palavras completas**, evitando
falsos positivos com siglas curtas (ex.: "ra" NÃO casa em "fora").

Localização: `config.py`. Editáveis sem mexer em código.

### `TERMOS_RECLAME_AQUI`

Casam em regras P1.A, P2.A, P3.A.

```python
[
    "reclame aqui",
    "reclameaqui",
    "reclame-aqui",
    "ra",          # sigla — protegida por word boundary
    "ra.com",
]
```

### `TERMOS_CONTRATACAO`

Casam em regra P1.B.

```python
[
    "contratacao",
    "contratação",
    "carrinho",
    "checkout",
    "pagamento",
    "compra",
    "central do cliente",
    "cal",         # sigla — protegida por word boundary
    "painel do produto",
]
```

### `TERMOS_INDISPONIBILIDADE_TOTAL`

Casam em regras P1.B, P1.C + componente de criticidade.

```python
[
    "fora do ar",
    "indisponivel",
    "indisponível",
    "não pinga",
    "nao pinga",
    "servidor fora",
    "sem acesso",
    "tudo fora",
    "ambiente fora",
    "down",
    "erro ao montar",
    "system rescue",
]
```

### `TERMOS_RISCO_SEGURANCA`

Casam em regra P1.D (isolado).

```python
[
    "vazamento",
    "invasao",
    "invasão",
    "ataque",
    "ransomware",
    "credencial exposta",
    "leak",
]
```

### `TERMOS_SEM_CONTORNO`

Heurística reservada para evolução futura. Hoje não é usada explicitamente nas
regras P-N (sem contorno é detectado via campo booleano).

```python
[
    "sem contorno",
    "sem solucao",
    "sem solução",
    "no workaround",
    "nenhum contorno",
]
```

### `_TERMOS_INDICADORES_CONTORNO` (em `extractor.py`)

Usados pelo parser `_detectar_contorno` para inferir se INC tem contorno (na
ausência de campo booleano direto no banco).

```python
[
    "contorno",
    "workaround",
    "solucao alternativa",
    "solução alternativa",
    "paliativo",
    "temporariamente",
    "temporário",
    "temporario",
]
```

### Como adicionar/remover um termo

1. Abrir `config.py`.
2. Encontrar a lista certa (`TERMOS_RECLAME_AQUI`, etc.).
3. Adicionar ou remover string.
4. Rodar `python -m pytest tests/` para confirmar que não quebrou nada.
5. Commit com mensagem explicando o porquê.

---

## 11. Como ajustar uma regra

### Cenário 1: ajustar um threshold

**Exemplo:** "P2 agora é >=8 INCs sem contorno, não 5."

1. Abrir `config.py`.
2. Mudar:
   ```python
   LIMIAR_P2_INCS_SEM_CONTORNO = 8   # antes: 5
   ```
3. Rodar testes — alguns vão falhar (esperam ainda 5). Ajustar os testes em
   `tests/test_rules_engine.py`.
4. Commit:
   ```
   matriz P1-P5: P2 sem contorno passa de 5 para 8 INCs

   Decisão de calibração de 2026-05-27 — volume aumentou ao ponto do
   antigo limiar virar permissivo demais.
   ```

### Cenário 2: adicionar/remover termo heurístico

**Exemplo:** "Time decidiu que 'reclamação no Facebook' também deveria entrar
em Reclame Aqui."

1. Abrir `config.py`.
2. Adicionar à lista:
   ```python
   TERMOS_RECLAME_AQUI = [
       ...
       "facebook",   # ← NOVO (cuidado com word boundary — funciona)
   ]
   ```
3. Rodar testes.
4. Commit.

### Cenário 3: nova regra na matriz

**Exemplo:** "Vamos criar P2.F — Ferramenta interna indisponível total."

1. Abrir `rules_engine.py`.
2. Adicionar condição em `_avaliar_p2`:
   ```python
   ferramenta_interna_total = _qualquer_termo_no_cluster(
       cluster, config.TERMOS_FERRAMENTA_INTERNA
   )
   if ferramenta_interna_total and indisponivel:
       justificativas.append(
           "Ferramenta interna indisponível total (P2)."
       )
   ```
3. Adicionar lista em `config.py`:
   ```python
   TERMOS_FERRAMENTA_INTERNA = ["ferramenta interna", "tool", ...]
   ```
4. Adicionar teste em `tests/test_rules_engine.py`:
   ```python
   def test_ferramenta_interna_indisponivel_vira_p2(self):
       ...
   ```
5. Rodar `pytest`.
6. Atualizar este documento (REGRAS.md) com a nova subseção.
7. Commit.

### Cenário 4: ajustar gatilho proativo (de 5 P3 para 7)

1. `config.py`:
   ```python
   LIMIAR_PRB_PROATIVO_INCS_P3 = 7   # antes: 5
   ```
2. Ajustar testes em `tests/test_rules_engine.py::TestGatilhoProativo`.
3. Atualizar seção 7 deste documento.
4. Commit.

### Cenário 5: ajustar critério de Saúde do Cliente

**Exemplo:** "Aumentar janela de recência de 7 para 14 dias."

1. `config.py`:
   ```python
   JANELA_RECENCIA_ALERTA_DIAS = 14   # antes: 7
   ```
2. Atualizar seção 9 deste documento.
3. Commit.

### Checklist universal de ajuste

- [ ] Mudei `config.py` (não código de regra) sempre que possível.
- [ ] Adicionei/ajustei teste correspondente.
- [ ] Rodei `pytest tests/` — todos passam.
- [ ] Rodei `python main.py` — pipeline completo sem erros.
- [ ] Atualizei este documento (REGRAS.md) refletindo a mudança.
- [ ] Commit message explica **o porquê** da mudança, não só **o quê**.

---

## 12. Clusterização — regras de agrupamento

Como duas INCs viram (ou não) o mesmo cluster.

### Caminho principal: TF-IDF + DBSCAN

INCs com **texto semanticamente similar** (descrição curta + descrição) entram
no mesmo cluster. Configurado em `config.py`:

- `DBSCAN_EPS = 0.55` — raio de vizinhança (cosseno). Menor = clusters mais coesos.
- `DBSCAN_MIN_SAMPLES = 2` — mínimo de INCs para formar cluster.
- `TFIDF_NGRAM_RANGE = (1, 2)` — unigrams + bigrams (capta termos técnicos).

INCs que o DBSCAN não consegue agrupar viram **singletons** (label `-1`).

### Fusão por (produto, servidor) — fallback de CI

Depois do DBSCAN, o motor varre os singletons e funde os que compartilham
**mesmo `produto` E mesmo `servidor`** (ambos truthy). Implementado em
`analyzer._fundir_singletons_por_ci`.

**Por que isso é regra de negócio:**
> "Duas INCs no mesmo servidor para o mesmo produto são, operacionalmente, o
> mesmo problema — mesmo que o analista tenha descrito diferente."

**Critério estrito:**
- `produto` truthy E não-vazio
- `servidor` truthy E não-vazio
- Singletons com CI incompleto **permanecem singletons** (evita falso match
  via campo vazio).

**Exemplo:** INC com `"kernel panic"` e INC com `"disco cheio"`, ambas em
`servidor='vps-prod-01'` e `produto='VPS'`, viram **um cluster fundido**.

### Filtragem de singletons na persistência

Clusters de tamanho 1 (`qtd_incs == 1`) **não são gravados** em
`lwsa.motor_cluster`. Implementado em `notifier_db.persistir_execucao`.

**Por quê:**
- A tabela ficava com ~70% de ruído (singletons sem agrupamento real).
- Singletons não geram prescrição PRB (volume insuficiente).
- Eles continuam **em memória** alimentando a Saúde do Cliente (que precisa
  de INCs individuais por cliente).

**Onde aparecem mesmo assim:**
- `output/dashboard_state.json` (UI pode mostrar se quiser).
- Saúde do Cliente — agrupados por `login_cliente`, não por CI.

### Normalização de `login_cliente`

Antes de qualquer GROUP BY ou WHERE por cliente, o login passa por
`sql_normalizar_login_cliente` (expressão PostgreSQL, port do projeto irmão
locapredict). Resolve 5 formatos diferentes para a mesma chave:

| Formato no banco | Normalizado |
|---|---|
| `govonifelipe` | `govonifelipe` |
| `govonifelipe (Cód. 1100035861)` | `1100035861` |
| `https://intranet.kinghost.com.br/.../ficha=424593` | `424593` |
| `1100035861` (dígitos puros) | `1100035861` |
| `MZ-Viagens.Br` | `mzviagensbr` |

Aplicada em todas as queries do customer_monitor + chamados.

### Enriquecimento via `dynamics.chamados` — login efetivo

Quando uma INC do SNow tem chamado correspondente em `dynamics.chamados.inc`,
o motor **prefere** o `logincliente` da Dynamics em vez do `login_cliente`
do SNow. Funciona via JOIN com CTE `chamados_por_inc` (DISTINCT ON, limitada
por `datacriacao` recente).

```
login_efetivo = COALESCE(
    NULLIF(TRIM(dynamics.chamados.logincliente), ''),
    service_now_incidentes.login_cliente
)
```

**Por que isso é regra de negócio:** o `logincliente` da Dynamics vem **limpo**
(`trieste1`, `dougdonda`, `webcolors3`), enquanto o `login_cliente` do SNow
pode estar vazio, com URL, ou com formato `(Cód. NNN)`. Cobertura observada:
~5-10% das INCs em 24h cruzam, mais em janelas longas.

**Efeito mensurado**: passou de **9 → 12 candidatos** a Saúde do Cliente, com
5 clientes novos com login real (`novon`, `doverroll`, `webcolors3`,
`diegopdias`, `dmsolucoestec`) que antes ficavam invisíveis. Recomenda-se
índice `CREATE INDEX ON dynamics.chamados (inc) WHERE inc IS NOT NULL`.

---

## 13. Filtros de organização e login

Configurações em `config.py` que delimitam o escopo de dados que o motor
processa. Hoje o motor está **focado em Locaweb**.

### `ORGANIZACOES_ATIVAS`

```python
ORGANIZACOES_ATIVAS: tuple = ("Locaweb",)
```

Restringe **INCs**, **PRBs** e **tabelas de chamados** às orgs listadas:

| Camada | Como |
|---|---|
| INCs (`service_now_incidentes`) | `AND organizacao IN ('Locaweb')` |
| PRBs (`service_now_problems`) | `AND organizacao IN ('Locaweb')` |
| Chamados | Itera só as orgs do registry presentes na tupla |

Tupla vazia `()` = sem filtro (todas as orgs do DW). Pra incluir KingHost:
`("Locaweb", "KingHost")`.

### `LOGIN_CLIENTE_PADROES_EXCLUIDOS`

```python
LOGIN_CLIENTE_PADROES_EXCLUIDOS: tuple = ("kinghost",)
```

Complementa o filtro por organização para o caso de INCs classificadas como
`organizacao = 'Locaweb'` no DW mas com `login_cliente` que indica outra
origem — ex.: URL `intranet.kinghost.com.br/.../ficha=NNN`. Aplicado via
`NOT ILIKE '%padrão%'` no `login_cliente` (substring case-insensitive).

Aplicado **apenas** em `contar_clientes_com_inc_recente` (a identificação de
candidatos a Saúde do Cliente). Outras queries não são afetadas.

---

## 14. ValidadorEntrega — prisma retrospectivo

Complemento ao prisma preventivo (Rules Engine): olha PRBs **já entregues**
pelo Change Team e verifica se o problema realmente foi resolvido. Entry-point
separado (`validar_entregas.py`, cadência default 6h).

### Os 3 veredictos (matriz inalterada)

| Veredicto | Condição | Slack? |
|---|---|---|
| `REINCIDENCIA` | ≥ `LIMIAR_INCS_REINCIDENCIA` (**3**) INCs novas em `(produto, servidor)` após `data_encerrado` | ✅ |
| `ENTREGA_VALIDADA` | **0** INCs pós-resolução E ≥ `MIN_DIAS_PARA_VALIDAR` (**7** dias) decorridos | ❌ |
| `INCONCLUSIVO` | Casos intermediários (janela curta, INCs sub-limiar) | ❌ |

Reincidência tem **precedência** sobre tempo: 3+ INCs no 2º dia ainda é
reincidência.

### Contexto enriquecedor (V3, 2026-06-02)

Cada `ValidacaoEntrega` carrega, além do veredicto, **3 sinais adicionais**:

**1. Volumetria pré-resolução** (`JANELA_VOLUMETRIA_PRE_DIAS = 60` dias antes
da entrega):

- `qtd_incs_pre_resolucao` — quantas INCs o PRB cobriu antes do fix
- `clientes_unicos_pre` — clientes distintos impactados
- `categorias_pre` — diversidade de categorização

Diferencia PRB "que apagou 50 INCs em 60d" de PRB "que apagou 2".

**2. Δ chamados vinculados pré/pós-resolução** (`JANELA_CHAMADOS_DELTA_DIAS = 14`
dias em cada lado):

- `chamados_pre` — chamados vinculados ao PRB antes de `data_encerrado`
- `chamados_pos` — chamados vinculados depois de `data_encerrado`
- `delta_chamados_pct` — `(pos - pre) / pre`

Match via colunas `dynamics.chamados.prb` E/OU `dynamics.chamados.inc`:
chamado conta se `prb = prb_id` **OU** `inc IN (INCs do CI no período)`.
Substituiu o match V2 por produto (genérico/ruidoso). Cobertura cai mas
precisão sobe drasticamente: PRBs sem chamados vinculados marcam `0/0`
honesto (em vez de inflar com ruído de outros produtos).

Quando `delta_chamados_pct ≤ LIMIAR_REDUCAO_CHAMADOS_PCT` (−0.5 = queda ≥ 50%),
o alerta Slack mostra ↓ indicando que o fix funcionou.

**3. PRBs novos pós-resolução** (mesma janela do veredicto):

- `qtd_prbs_novos_pos_resolucao` — quantos PRBs **novos** foram abertos no
  mesmo `(produto, servidor)` depois de `data_encerrado`
- `prbs_novos` — lista de `numero` (ex.: `["PRB0012345"]`)

Sinal complementar à reincidência por INCs: se um PRB novo foi criado,
indica que o problema **voltou em outra forma** — possivelmente fix tratou
sintoma, não causa raiz. Requisito da coordenação (2026-06-02). O PRB
sendo validado é excluído por `numero <> %s` (defensivo contra
auto-referência).

### Como interpretar (operacional)

| Cenário | Volumetria pré | Δ chamados (vinculados) | PRBs novos | Veredicto | Leitura |
|---|---|---|---|---|---|
| PRB resolveu um problema gigante e zerou contato | Alta (50+ INCs) | ↓ (>50%) | 0 | ENTREGA_VALIDADA | **Fix excelente.** |
| PRB pequeno, sem ruído | Baixa (2-5 INCs) | 0/0 | 0 | ENTREGA_VALIDADA | OK. Sem cobertura no Dynamics, mas sem reincidência também. |
| Problema voltou em outra forma | Qualquer | Qualquer | ≥1 PRB | REINCIDENCIA OU INCONCLUSIVO | **Reabrir/investigar a causa raiz.** |
| Fix piorou (contato subiu) | Qualquer | ↑ (>50%) | 0 | REINCIDENCIA | **Re-investigar urgente.** |
| Janela curta, sem dado novo | — | — | 0 | INCONCLUSIVO | Aguardar próximo ciclo. |

---

## 15. Painel Change Team — força-tarefa

A **Change Team** é uma força-tarefa interdisciplinar da Locaweb dedicada à
resolução de **84 PRBs específicos** (lista deduplicada da onda inicial de
2026-06-05). O Painel Change Team materializa o estado atual desses PRBs num
snapshot Postgres atualizado **a cada 6h**, consumido via chart **"PRB Change
Team"** no Superset corporativo. Phase 1 do GSD concluída 2026-06-05; **go-live
PROD 2026-06-09** (6 reincidências surfaceadas, PRB0055284 com 726 dias
pós-resolução em destaque).

### Decisões locked (Phase 1, CONTEXT.md)

| ID | Decisão |
|---|---|
| D-01 | Lista master em tabela dedicada `lwsa.motor_change_team` (coluna `numero`) com **soft delete** (`ativo` + `removido_em`) — nunca usar `DELETE`. |
| D-02 | Entry-point é o **ValidadorEntrega** (cadência 6h, `validar_entregas.py`, 3º bloco try/except). |
| D-03 | Query SEM janela temporal — captura PRBs antigos que o V3.1 normal (14d) jamais pegaria. |
| D-04 | Persistência **TRUNCATE+INSERT atômico** em `lwsa.motor_change_team_painel`. |
| D-05 | Colunas para PRBs abertos: status SNow, idade, prioridade, grupo designado, última atualização. |
| D-06 | Colunas para PRBs resolvidos: D-05 + 7 sinais V3.1 (reusa `validador_entrega._avaliar_prb`, CON-012 LOCKED). |
| D-07 | Consumo via Superset corporativo (chart manual, fora do escopo automatizado). |
| D-08 | Feature key = `change_team`; Chart name = "PRB Change Team". |

### CON-012 LOCKED — preservar V3.1 do ValidadorEntrega

A integração Change Team **NÃO PODE** afetar o veredicto do ValidadorEntrega V3.1.
Implementação: try/except do Change Team é **separado** do try/except do V3.1
no `validar_entregas.py`. Falha do Change Team registra warning + zera o
snapshot, mas `motor_validacao_entrega` continua sendo populada normalmente.

### Veredicto reusado (PRBs resolvidos)

Para PRBs Change Team **já resolvidos** (`data_encerrado IS NOT NULL`), o
painel reusa o `validador_entrega._avaliar_prb` — herda automaticamente
`REINCIDENCIA / ENTREGA_VALIDADA / INCONCLUSIVO` (§14) + os 5 sinais V3.1
(volumetria pré, Δ chamados, PRBs novos pós, times impactados). Sem
duplicação de lógica.

### Critério de seleção dos 84 PRBs

Lista **manual e curada** pela coordenação Change Team, persistida em
`lwsa.motor_change_team` com `ativo = true`. **NÃO** há regra automática —
adicionar/remover PRB é operação SQL explícita (ver [DASHBOARD_CHANGE_TEAM.md §5](DASHBOARD_CHANGE_TEAM.md#5-gestão-da-lista-master)).

### Toggle de runtime

Env var `CHANGE_TEAM_HABILITADO` (default `"true"`). Set `"false"` desliga o
painel sem deploy. O ValidadorEntrega V3.1 continua rodando independente.

### Como ajustar

- **Adicionar/remover PRB:** SQL `INSERT` / `UPDATE ativo=false` em
  `lwsa.motor_change_team` (ver DASHBOARD_CHANGE_TEAM.md §5).
- **Mudar cadência:** ajustar Task Scheduler do `Motor-PRB-Validador.bat`
  (mesma task que dispara V3.1 + Change Team).
- **Mudar Top N de PRBs no chart:** ajustar query do chart no Superset (não
  toca código).

Detalhes operacionais completos em [DASHBOARD_CHANGE_TEAM.md](DASHBOARD_CHANGE_TEAM.md).

---

## Referências cruzadas

- **[ARQUITETURA.md](ARQUITETURA.md):** como o motor implementa essas regras.
- **[MANUAL.md](MANUAL.md):** como usar o motor.
- **[SAUDE_DO_CLIENTE.md](SAUDE_DO_CLIENTE.md):** processo completo do prisma de Saúde do Cliente (ponta a ponta).
- **[VALIDADOR_ENTREGA.md](VALIDADOR_ENTREGA.md):** processo completo do prisma retrospectivo (ponta a ponta).
- **[DASHBOARD_CHANGE_TEAM.md](DASHBOARD_CHANGE_TEAM.md):** guia operacional do Painel Change Team (Phase 1 GSD).
- **[../GLOSSARIO.md](../GLOSSARIO.md):** termos técnicos (CI, PRB, INC, OLA, etc.).
- **`config.py`:** todos os thresholds e termos heurísticos.
- **`rules_engine.py`:** implementação da cascata P1-P5.
- **`change_team.py`:** orquestrador do Painel Change Team.
- **`tests/test_rules_engine.py`:** testes que validam cada regra.

---

_Documento mantido sob responsabilidade do PO + contribuidores do motor.
Reflete a matriz oficial vigente. Última atualização: 2026-06-09 (Painel
Change Team em PROD — Phase 1 GSD concluída; ValidadorEntrega V3.1)._