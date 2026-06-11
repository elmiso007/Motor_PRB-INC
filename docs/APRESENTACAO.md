<!--
Apresentação executiva do Motor PRB-INC.

Formato: cada slide separado por `---` (linha horizontal).
Compatível com:
  - Marp / Reveal.js / Pandoc para gerar PDF/PPT.
  - Leitura direta no GitHub/VSCode (renderiza como sequência de seções).

Para gerar PDF (opcional):
  npx @marp-team/marp-cli APRESENTACAO.md --pdf
-->

# Motor PRB-INC

### O vigia automático que enxerga o que ninguém vê

**Apresentação executiva** · Junho/2026
**Audiência:** Liderança, Coordenação e Change Team
**Linguagem:** direta, sem jargão técnico

---

## Em uma frase

> *O Motor PRB-INC é um robô que lê o tempo todo as reclamações dos
> clientes e os chamados internos, percebe quando várias delas falam
> da mesma coisa, e avisa o time antes do problema virar uma crise.*

Pense nele como um **vigia 24h que nunca cansa** e que consegue ler
centenas de incidentes por dia, encontrar padrões que humanos
demorariam horas para enxergar — e cutucar a gente no Slack quando
algo cheira mal.

---

## O problema que ele resolve

### Antes do motor — um dia ruim típico

- 🕘 **Terça, 10h:** Analista A pega um chamado: *"servidor VPS-01
  não responde"*. Reinicia, fecha em 30 min.
- 🕡 **Terça, 18h:** Outro analista, plantão da tarde, pega o **mesmo
  servidor** com problema parecido. Reinicia de novo. Fecha.
- 🌙 **Quarta, 02h:** Plantão da madrugada — terceira vez. Reinicia,
  fecha.
- 🔥 **Sábado, 03h:** Servidor cai de vez. Crise no Reclame Aqui.
  Cliente perdido.

**O que aconteceu?** Cada analista tratou um chamado isolado.
**Ninguém viu o padrão.** Esse é o erro que o motor evita.

---

## O que o motor faz, no dia a dia

A cada **1 hora**, automaticamente:

1. 📥 **Lê tudo o que entrou** — chamados do ServiceNow (sistema oficial
   de incidentes da Locaweb) e tickets do suporte ao cliente.

2. 🔍 **Procura padrões** — agrupa incidentes que falam da mesma coisa,
   mesmo que estejam escritos com palavras diferentes.

3. 🚦 **Decide a urgência** — aplica a régua oficial da Locaweb
   (P1 = crise, P2 = alta, P3 = média, P4/P5 = baixa) com base no que
   ele encontrou.

4. 💬 **Sugere o que fazer** — abrir uma ficha de problema (PRB), elevar
   a prioridade de uma ficha existente, ou só monitorar.

5. 🌡️ **Vigia clientes ruidosos** — quando um cliente abre 3 ou mais
   incidentes em 6 meses, ele avisa a coordenação.

6. 📤 **Conta pra gente** — pelo Slack (quando é crítico) e por um
   painel visual atualizado.

---

## O que é "incidente" e "PRB"?

Dois termos que vão aparecer muito. Vamos descomplicar:

| Termo | O que é, em linguagem simples |
|---|---|
| **Incidente (INC)** | Um chamado de algo que está dando errado **agora**. *"Servidor caiu"*, *"meu painel não abre"*. Resolve-se reiniciando, restaurando, etc. — foco em **voltar a funcionar**. |
| **PRB (Problema)** | A **causa raiz** que está gerando vários incidentes. Se 5 INCs vêm do mesmo servidor caindo todo dia, abre-se 1 PRB para investigar o motivo de fundo. **Resolve-se o problema, não só o sintoma.** |
| **Change Team** | Time interdisciplinar da Locaweb que **entrega a solução** dos PRBs. Quando um PRB sai como "concluído", foi a Change Team que fez. |
| **OLA** | Acordo de prazo interno entre times (ex.: "time A entrega para o time B em até 4h"). |

> 💡 **Resumo:** INC é o sintoma. PRB é a doença. Change Team é o
> médico que cura.

---

## O motor olha por 3 ângulos diferentes

Hoje ele faz três trabalhos complementares:

### 1️⃣ Olha pra frente — *"o que pode dar problema?"*

A cada 1 hora, lê todos os incidentes ativos e identifica padrões.
Se 5 chamados parecidos surgem no mesmo servidor, ele avisa **antes**
de virar crise.

### 2️⃣ Olha pra trás — *"o que a gente entregou realmente funcionou?"*

A cada 6 horas, pega os PRBs que a Change Team marcou como
"concluídos" nos últimos 14 dias e checa: **o problema voltou?**
Se voltou (3+ incidentes novos no mesmo lugar), avisa que o fix
não pegou de verdade.

### 3️⃣ Olha pra força-tarefa — *"como estão os 84 PRBs prioritários?"*

A Change Team mantém uma lista de **84 PRBs específicos** que precisam
acompanhamento dedicado. O motor materializa essa lista num painel
sempre atualizado — quem ainda está aberto, quem foi resolvido, quem
voltou a dar problema.

---

## Como o motor "entende" os incidentes?

Sem entrar em detalhe técnico — o motor lê o texto livre de cada
chamado e **percebe similaridade semântica**. Exemplo:

```
INC 1: "Servidor caiu - kernel panic no VPS-01"
INC 2: "VPS-01 não está respondendo, parece travado"
INC 3: "Cliente reportando que servidor 01 fora do ar"
```

Para um humano, os três parecem assuntos diferentes. **Para o motor,
é o mesmo problema** — mesmo servidor, mesma natureza. Ele agrupa os
três como **um único caso** e dá uma só recomendação.

Isso é o que permite ele perceber padrões que escapam à leitura
incidente-a-incidente.

---

## Onde a informação chega para você

```
┌─────────────────────────────────────────────────────────┐
│  Sistema de chamados (ServiceNow + suporte ao cliente)  │
│                  Banco central da Locaweb               │
└──────────────────────────┬──────────────────────────────┘
                           │ a cada 1h (preventivo)
                           │ a cada 6h (validador + Change Team)
                           ▼
┌─────────────────────────────────────────────────────────┐
│                    MOTOR PRB-INC                         │
│                                                          │
│   Lê → Agrupa → Avalia → Recomenda → Avisa              │
└──────┬──────────────┬───────────────────┬───────────────┘
       │              │                   │
       ▼              ▼                   ▼
   ┌───────┐    ┌───────────┐       ┌──────────────┐
   │ Slack │    │  Painel   │       │  Histórico   │
   │ 🚨    │    │  visual   │       │  pra consulta│
   │ urgente│    │ (Superset)│       │  (Postgres)  │
   └───────┘    └───────────┘       └──────────────┘
```

**Cada saída atende uma audiência diferente:**

- **Slack** → plantão recebe avisos críticos no momento que acontecem
- **Painel** → coordenação abre de manhã e vê tudo organizado
- **Histórico** → liderança e PO consultam tendências mensais

---

## Exemplo concreto — alerta crítico no Slack

Quando o motor detecta uma crise, o time recebe assim:

```
🚨🆘 Motor PRB-INC — Alerta CRÍTICO
Sugestão: ABRIR PRB | Prioridade: P1

📦 Produto: CAL
🖥️ Servidor: cal-frontend-03
📈 6 incidentes parecidos nas últimas horas
💬 16 clientes ligaram falando do mesmo problema hoje
🔁 Esse servidor já apareceu 4x esta quinzena

Justificativas (por que P1):
• Contratação indisponível, sem solução temporária (P1).
• Mesmo servidor reaparecendo repetidamente.
• Volume alto de chamados de clientes.
```

> 🎯 **A vantagem:** o coordenador entende em 5 segundos *o que está
> acontecendo* e *por que é grave*. Sem precisar abrir 6 sistemas
> diferentes para confirmar.

---

## Saúde do Cliente — o "termômetro" do cliente recorrente

### Como era antes (manualmente)

Cliente liga reclamando na madrugada. Analista precisa:

1. Abrir ServiceNow, buscar histórico do cliente — **5 min**
2. Abrir sistema de suporte, buscar chamados antigos — **5 min**
3. Intercalar manualmente num Excel pra entender a história — **5 min**

**Total: ~15 minutos de garimpagem ANTES de começar a resolver.**

### Como ficou com o motor

Coordenador abre o painel de manhã. Cada cliente "barulhento" já
está com o card pronto:

```
🌡️ Cliente: govonifelipe — RECORRÊNCIA ALTA
11 incidentes em 6 meses · 25 tickets de suporte

⏰ Linha do tempo já consolidada:
🟢 Servidor fora — 2h atrás (P3)
💬 Cliente abriu ticket — 3h atrás
🟢 Mesmo erro — 8h atrás (P3)
💬 Outro ticket — 2 dias atrás
🟢 Painel travado — 1 mês atrás (P2)
```

**Tempo de leitura: 30 segundos** para os 11-13 clientes do dia.

---

## Painel Change Team — força-tarefa em 1 tela

A Change Team tem **84 PRBs específicos** sob acompanhamento
dedicado. Antes, acompanhar essa lista era abrir 84 fichas uma a
uma no ServiceNow.

Hoje, tem um **painel único no Superset** (sistema de relatórios da
Locaweb) que mostra de uma vez:

| Coluna | O que mostra |
|---|---|
| **PRB** | Número da ficha |
| **Status** | Aberto / Resolvido / Reincidente |
| **Dias em aberto** | Há quanto tempo está lá |
| **Veredicto** | Para resolvidos: o fix segurou? Voltou o problema? |
| **Times impactados** | Quais equipes internas estavam chamando antes do fix e pararam depois |

### Achados reais (go-live de 09/06/2026)

- ✅ **84 de 84 PRBs** no painel (depois de uma operação para trazer
  PRBs antigos do banco)
- ⚠️ **6 reincidências surfaceadas** — fixes que voltaram a dar
  problema
- 🚨 **Destaque: PRB0055284** — fechado há **726 dias**, mas continua
  gerando ~6 incidentes/mês no Hospedagem Compartilhada. O painel
  acendeu o alerta — sem ele, esse PRB ficaria invisível para
  sempre.

---

## Times impactados — quem o PRB realmente afetou?

Sinal novo entregue em 03/06/2026. Responde a pergunta da
coordenação:

> *"Esse PRB que a Change Team entregou — quais times internos da
> Locaweb deixaram de chamar depois?"*

Exemplo real:

```
PRB resolveu bug na ferramenta de cobrança
Antes do fix → Depois do fix:

  • Cobrança:       12 chamados → 0  ✅ zerou!
  • Faturamento:    8  chamados → 1  ↓ caiu 87%
  • Suporte Geral:  3  chamados → 2  (estável)
```

**Leitura operacional:** o fix foi excelente para Cobrança e bom para
Faturamento. Discreto para Suporte Geral. A coordenação pode parabenizar
quem entregou e investigar se os 2 chamados restantes do Suporte são
da mesma natureza.

---

## O que muda para cada um de vocês

### 👔 Liderança / Gestores

- Métricas de "saúde do produto" sempre disponíveis no banco — consulta
  SQL responde em segundos perguntas que antes exigiam horas de
  análise.
- Histórico de **30 dias** de execuções persistido — dá pra ver
  tendência por semana, por produto, por servidor.
- Visibilidade sobre **eficácia da Change Team** — quantos fixes
  realmente seguraram, quantos voltaram.

### 🎯 Coordenação

- Painel pronto de manhã, sem preparar slides manualmente.
- Alertas críticos no Slack — não precisa ficar abrindo sistemas para
  monitorar.
- Clientes ruidosos identificados automaticamente — proativo, não
  reativo.

### 🔧 Change Team

- Cada PRB resolvido recebe **veredicto automático** após 7-14 dias:
  - ✅ *Entrega Validada* — o fix segurou
  - ⚠️ *Reincidência* — o problema voltou, reabrir
  - 🤔 *Inconclusivo* — ainda cedo demais para decidir
- Sinais ricos no Slack quando alguma coisa volta: quantos incidentes
  novos, quantos clientes ligaram, quais times pararam de chamar.
- **Painel Change Team** com os 84 PRBs prioritários sempre atualizado.

### 🚨 Plantão

- Slack só toca quando é **realmente crítico** (P1 ou cliente em
  alerta). Sem ruído.
- Quando toca, vem com **justificativa por escrito** — entende em 5
  segundos o porquê.

---

## O que o motor decide sozinho — e o que NÃO

Importante entender as fronteiras:

### ✅ O motor faz sozinho

- Lê milhares de chamados.
- Agrupa por similaridade.
- Aplica a régua P1-P5 da Locaweb.
- **Sugere** abrir PRB, elevar prioridade, monitorar.
- Avisa no Slack quando é grave.
- Mantém o painel atualizado.

### ❌ O motor NÃO faz (por princípio de segurança)

- **Não abre PRB sozinho no ServiceNow.** Só sugere — humano confirma.
- **Não rebaixa prioridade automaticamente.** Só sugere elevar.
- **Não decide P5 sozinho** — exige confirmação do Coordenador/PO,
  porque P5 é "decidimos não consertar agora", e isso é decisão de
  produto, não de máquina.
- **Não aprende com feedback.** As regras são as oficiais da Locaweb
  — quem ajusta é a coordenação, não o motor.

> 🎯 **Filosofia:** o motor é uma ferramenta de **apoio à decisão
> humana**, não um substituto. Toda decisão importante passa por
> alguém com nome e crachá.

---

## Como saber se ele está funcionando?

Indicadores rápidos:

| O que olhar | Como verificar | Bom sinal |
|---|---|---|
| Motor preventivo está vivo? | Painel atualizou na última hora | ✅ sim |
| Validador rodou hoje? | Painel Change Team com "snapshot < 7h" | ✅ sim |
| Está achando coisas? | 5-10 prescrições por ciclo em média | ✅ esperado |
| Reincidências detectadas | 6 surfaceadas no go-live | ✅ funcionando |

Se algo parecer parado, a coordenação tem queries SQL prontas para
checar em segundos (documentadas em `docs/MANUAL.md`).

---

## Resultados reais — primeiro mês em produção

Dados do banco real da Locaweb, atualizados em 09/06/2026:

| O que mede | Valor |
|---|---|
| Incidentes processados por ciclo | **280-400** |
| Tickets de suporte cruzados | **500-700** |
| Grupos de incidentes parecidos identificados | **70-95** por ciclo |
| Clientes ruidosos detectados | **9-12 por ciclo** |
| PRBs com fix validado (avaliados a cada 6h) | **~10 por ciclo** |
| **Achado de destaque** | **PRB0055284 — 726 dias pós-resolução ainda gerando incidentes** |
| Tempo total do ciclo preventivo | **22-31 segundos** |
| Tempo do ciclo validador + Change Team | **~143 segundos** |
| Erros no período | **0** |

> 🚀 **Em produção desde:** maio/2026 (preventivo) | junho/2026
> (Validador + Painel Change Team).

---

## Quando o motor "ajustou" expectativas

Algumas coisas só viraram visíveis depois que ele entrou em operação:

### Aprendizado 1 — PRBs antigos esquecidos

O **PRB0055284** estava fechado há 2 anos. Ninguém olhava mais para
ele. Mas continuava gerando ~6 incidentes/mês no Hospedagem
Compartilhada. **Sem o painel Change Team, ninguém perceberia.**

### Aprendizado 2 — fixes que parecem ok mas voltam

Das **84 fichas** da Change Team, **6 viraram reincidências** depois
do go-live. Isso não significa que a Change Team trabalhou mal —
significa que algumas correções são complexas e merecem
re-investigação. **Antes, isso só apareceria quando o cliente
reclamasse no Reclame Aqui.**

### Aprendizado 3 — times impactados sumindo

Quando um PRB resolve um problema bem, dá pra **ver no chart**:
*"Cobrança chamou 12 vezes antes do fix → 0 depois"*. Isso vira
**reconhecimento concreto** da Change Team, com número.

---

## O que vem pela frente

### Em discussão (próximos 30 dias)

- **Ligar os alertas Slack** — hoje as 6 reincidências e 8 saúdes
  altas estão sendo registradas, mas o disparo no Slack está
  desligado por escolha (revisão antes de ativar).
- **Frente de relatório semanal** — resumir automaticamente para
  liderança "o que aconteceu essa semana".

### Em discussão (próximos 90 dias)

- **Painel visual para coordenação** — hoje a coordenação consulta
  via Superset (técnico). Pode existir uma versão mais leve no
  navegador.
- **Análise de tendência** — comparar este mês com o anterior:
  "Hospedagem está piorando? E-mail está estável?"

### Fora de cogitação (por enquanto)

- **Motor escrever no ServiceNow.** Continua sendo *"sugere, humano
  decide"* — segurança operacional acima de tudo.
- **Substituir analistas.** O motor é **apoio**, não substituição.

---

## Quem está atrás disso

**Construção:** Emerson Ramos (Locaweb)

**Requisitos originais:** Jéssica, Victor, Bruno, Emerson — reunião
de levantamento que deu origem ao projeto.

**Em produção desde:** maio/2026.

**Phase 1 (Painel Change Team) entregue:** 05/06/2026.
**Go-live em PROD:** 09/06/2026.

---

## Perguntas que costumam aparecer

**"O motor erra?"**
> Pode errar — qualquer ferramenta automática pode. Por isso ele
> **sugere**, nunca decide sozinho. Cada decisão tem **justificativa
> por escrito** auditável. Se algo parecer estranho, basta abrir a
> justificativa.

**"E se ele cair?"**
> O Windows Task Scheduler (sistema do Windows) dispara o motor de
> hora em hora. Se um ciclo crashar, o próximo simplesmente roda. Não
> há "motor caído" — há "ciclo que falhou", que se recupera no
> próximo.

**"Posso desligar uma frente sem mexer no resto?"**
> Sim. O Painel Change Team tem um interruptor próprio
> (`CHANGE_TEAM_HABILITADO`). Se houver problema com ele, desliga
> sem afetar o validador nem o motor preventivo.

**"Onde ficam os dados sensíveis?"**
> No banco da própria Locaweb (Postgres `lwsa.*`). O motor não
> manda nada para fora — só lê de dentro e devolve no Slack/painel
> internos.

**"Quem mexe nos limiares (P1, P2, etc.)?"**
> Coordenação + PO. Os limiares vivem num arquivo de configuração
> (`config.py`) — ajuste é 1 linha + reinício do motor.

---

## Para se aprofundar (opcional)

Se quiser ler mais sobre algum tópico específico, a documentação
técnica está organizada em audiências:

- **`docs/MANUAL.md`** — Para quem opera o motor no dia a dia
- **`docs/REGRAS.md`** — Para PO/auditoria — matriz oficial P1-P5
- **`docs/VALIDADOR_ENTREGA.md`** — Para Change Team — como ler
  veredictos
- **`docs/DASHBOARD_CHANGE_TEAM.md`** — Para quem mantém a lista
  da força-tarefa
- **`docs/SAUDE_DO_CLIENTE.md`** — Para coordenação — como funciona
  o termômetro de cliente
- **`docs/ARQUITETURA.md`** — Para quem quer mexer no código (técnico)
- **`GLOSSARIO.md`** — Dicionário de termos

---

## Resumo de bolso

🎯 **O motor é um vigia automático.**

📥 **Lê** todos os incidentes e tickets de suporte.

🔍 **Agrupa** o que é parecido.

🚦 **Decide** a urgência usando a régua oficial da Locaweb.

💡 **Sugere** o que fazer (mas não decide sozinho).

📊 **Mostra** tudo num painel + avisa no Slack quando é crítico.

🔁 **Acompanha** se o que a Change Team entregou realmente segurou.

🎯 **84 PRBs prioritários** num painel único, sempre atualizado.

⏰ **24/7**, sem cansar.

---

## Obrigado

**Motor PRB-INC** · Locaweb · Junho/2026

Dúvidas, sugestões ou pedidos de evolução: **Emerson Ramos**.

> *"O motor faz o trabalho braçal de comparar, agrupar e cruzar.
> Vocês fazem o trabalho que importa: decidir o que resolver primeiro
> e como."*
