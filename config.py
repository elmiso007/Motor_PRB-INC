# =============================================================================
# Motor Prescritivo PRB — Configuração centralizada
# =============================================================================
# Thresholds, credenciais (via env vars) e parâmetros operacionais. Toda lógica
# de regras lê daqui; ajustes de calibração não devem espalhar pelo código.
# =============================================================================
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


# -----------------------------------------------------------------------------
# Janelas temporais
# -----------------------------------------------------------------------------
JANELA_INC_HORAS = 24                 # ServiceNow: INCs abertas nas últimas N horas
JANELA_DYNAMICS_HORAS = 24            # Dynamics: chamados/interações do dia anterior
JANELA_SAUDE_CLIENTE_MESES = 6        # Histórico de cliente para alerta de recorrência
JANELA_RECORRENCIA_CI_DIAS = 15       # Detecção de mesmo CI repetindo em N dias
INTERVALO_JOB_MINUTOS = 15            # Cadência recomendada do Task Scheduler (Motor-PRB.bat)


# -----------------------------------------------------------------------------
# Thresholds da Matriz Oficial PRB (P1-P5) — extraídos da documentação interna
# -----------------------------------------------------------------------------
# Sem solução de contorno
LIMIAR_P2_INCS_SEM_CONTORNO = 5       # >= INCs sem contorno → P2 (Alta)

# Com solução de contorno
LIMIAR_P2_INCS_COM_CONTORNO = 100     # >= INCs com contorno → P2
LIMIAR_P3_INCS_COM_CONTORNO_MIN = 20  # faixa P3 começa aqui
LIMIAR_P3_INCS_COM_CONTORNO_MAX = 100 # exclusivo (vai para P2 acima disso)
LIMIAR_P4_INCS_COM_CONTORNO_MAX = 20  # < 20 INCs e contorno → P4

# Tempo de solução de contorno (em minutos)
LIMIAR_P2_CONTORNO_MIN = 60           # >= 60 min → P2
LIMIAR_P3_CONTORNO_MIN_INICIO = 10    # faixa P3: 10-60 min
LIMIAR_P3_CONTORNO_MIN_FIM = 60
LIMIAR_P4_CONTORNO_MAX_MIN = 10       # < 10 min → P4

# Gatilho proativo de PRB pela regra das "5 P3 idênticas"
LIMIAR_PRB_PROATIVO_INCS_P3 = 5

# Recorrência por cliente (Saúde do Cliente)
LIMIAR_INCS_SAUDE_CLIENTE = 3         # >= 3 INCs em 6 meses → recorrência alta
JANELA_RECENCIA_ALERTA_DIAS = 7       # cliente precisa ter INC recente para alertar (evita alert fatigue)

# Janela usada SÓ pra identificar candidatos a Saúde do Cliente. Maior que
# JANELA_INC_HORAS porque cliente real raramente abre 3 INCs em 24h — precisa
# de mais dias pra atingir o limiar. NÃO afeta clusterização nem prescrições
# (essas continuam usando JANELA_INC_HORAS=24).
#
# Quando esse valor (em horas) for > JANELA_INC_HORAS, o customer_monitor faz
# uma 2ª query ao extractor com a janela ampliada. Caso seja menor/igual, usa
# a lista de INCs que o scheduler já carregou (sem custo extra).
JANELA_CANDIDATOS_SAUDE_DIAS = 30

# Filtro de tipo_usuario na Saúde do Cliente.
# Por design do ServiceNow, INCs com tipo_usuario = "Integração" são abertas
# por monitoração (Zabbix/Nagios) e NÃO têm cliente associado — login_cliente
# vem vazio. "Saúde do Cliente" só faz sentido sobre INCs realmente abertas em
# nome de cliente (tipo_usuario = "Nominal"). Lista vazia desativa o filtro.
TIPOS_USUARIO_SAUDE_CLIENTE: tuple = ("Nominal",)

# Mapeamento de prioridade → peso numérico para score de severidade média.
# Range 0.0 (menos grave) a 1.0 (mais grave), linear inverso.
# Usado em customer_monitor.SaudeCliente.severidade_media para distinguir
# cliente com 3 P1s (crítico) de cliente com 3 P4s (rotineiro).
PESO_PRIORIDADE_SEVERIDADE = {
    "P1": 1.00,
    "P2": 0.75,
    "P3": 0.50,
    "P4": 0.25,
    "P5": 0.00,
}


# -----------------------------------------------------------------------------
# Parâmetros de Clusterização Semântica
# -----------------------------------------------------------------------------
# DBSCAN: eps menor = clusters mais coesos. Calibrar empiricamente.
DBSCAN_EPS = 0.55                     # raio de vizinhança em distância de cosseno
DBSCAN_MIN_SAMPLES = 2                # mínimo de INCs para formar um cluster
TFIDF_MAX_FEATURES = 5000             # vocabulário máximo do TF-IDF
TFIDF_NGRAM_RANGE = (1, 2)            # unigrams + bigrams capturam termos técnicos
MIN_INCS_PARA_CLUSTERIZAR = 2         # abaixo disso, pula clusterização


# -----------------------------------------------------------------------------
# Scores
# -----------------------------------------------------------------------------
# Score de criticidade: combinação ponderada
PESO_VOLUME_CRITICIDADE = 0.35        # volume relativo de INCs no cluster
PESO_INDISPONIBILIDADE = 0.30         # presença de termos de indisponibilidade total
PESO_SEM_CONTORNO = 0.25              # ausência de solução de contorno
PESO_RECORRENCIA_CI = 0.10            # mesmo CI já tinha aparecido antes

# Score de ineficiência — composição ponderada de DOIS sinais:
#   - Volume: média de updates por INC (proxy do trabalho acumulado).
#   - Velocidade: média de updates/hora (proxy de patinação intensa vs. lenta).
# 10 updates em 1h ≠ 10 updates em 7d — esse score captura a diferença.
LIMIAR_UPDATES_INEFICIENTE = 8        # volume: acima disso, componente volume satura em 1.0
LIMIAR_UPDATES_POR_HORA = 2.0         # velocidade: acima disso, componente velocidade satura
PESO_INEFICIENCIA_VOLUME = 0.6        # peso do componente volume na composição
PESO_INEFICIENCIA_VELOCIDADE = 0.4    # peso do componente velocidade na composição
# Soma dos pesos = 1.0 (intencional — score máximo permanece 1.0)
MIN_HORAS_INC_INEFICIENCIA = 0.1      # clamp para evitar divisão por zero (6 min)


# -----------------------------------------------------------------------------
# Termos heurísticos (substring match case-insensitive)
# -----------------------------------------------------------------------------
TERMOS_INDISPONIBILIDADE_TOTAL: List[str] = [
    "fora do ar", "indisponivel", "indisponível", "não pinga", "nao pinga",
    "servidor fora", "sem acesso", "tudo fora", "ambiente fora", "down",
    "erro ao montar", "system rescue",
]

TERMOS_RECLAME_AQUI: List[str] = [
    "reclame aqui", "reclameaqui", "reclame-aqui", "ra", "ra.com",
]

TERMOS_RISCO_SEGURANCA: List[str] = [
    "vazamento", "invasao", "invasão", "ataque", "ransomware",
    "credencial exposta", "leak",
]

TERMOS_CONTRATACAO: List[str] = [
    "contratacao", "contratação", "carrinho", "checkout", "pagamento",
    "compra", "central do cliente", "cal", "painel do produto",
]

TERMOS_SEM_CONTORNO: List[str] = [
    "sem contorno", "sem solucao", "sem solução", "no workaround",
    "nenhum contorno",
]


# -----------------------------------------------------------------------------
# Credenciais e endpoints (via env vars — nunca commitar segredos)
# -----------------------------------------------------------------------------
# Schema/tabelas do data warehouse onde os dumps do ServiceNow são ingeridos.
# Centralizado aqui para o extractor não ter strings SQL mágicas.
SCHEMA_BANCO = "lwsa"
TABELA_INCIDENTES = "service_now_incidentes"
TABELA_PROBLEMAS = "service_now_problems"

# Filtro de organizações ativas. Restringe INCs/PRBs do ServiceNow e tabelas
# de chamados às organizações listadas. Tupla vazia = sem filtro (todas as
# orgs). Hoje o motor está focado em "Locaweb"; pra incluir KingHost, basta
# acrescentar à tupla:
#   ORGANIZACOES_ATIVAS = ("Locaweb", "KingHost")
ORGANIZACOES_ATIVAS: tuple = ("Locaweb",)

# Padrões substring (case-insensitive) que devem EXCLUIR INCs do levantamento
# da Saúde do Cliente. Complementa ORGANIZACOES_ATIVAS para casos onde o DW
# classifica a INC como 'Locaweb' mas o `login_cliente` indica outra origem
# (ex.: URL `intranet.kinghost.com.br/.../ficha=NNN`). ILIKE substring.
LOGIN_CLIENTE_PADROES_EXCLUIDOS: tuple = ("kinghost",)

# Status que indicam PRB ainda ATIVO (relevante para sugestão de repriorização).
# INCs não são filtradas por status — o motor olha o fluxo de 24h, não o estado.
STATUS_PRB_ATIVOS = (
    "Aberto",
    "Em andamento",
    "Aguardando Validação da Resolução",
    "Aguardando Projeto",
    "Congelado",
)

# Status que indicam PRB já entregue pelo Change Team (alvo do ValidadorEntrega).
# Restrito a status com `data_encerrado` confiável no DW. "Aguardando Validação
# da Resolução" foi excluído porque no banco real esse status sempre tem
# data_encerrado=NULL (decisão registrada em 2026-05-28).
STATUS_PRB_ENCERRADOS = (
    "Encerrado Automaticamente",
    "Concluído",
)

# Tabelas do motor Change Team (Phase 1 do painel — 2026-06-05).
TABELA_CHANGE_TEAM = "motor_change_team"               # master list soft-deleted (D-01)
TABELA_CHANGE_TEAM_PAINEL = "motor_change_team_painel"  # snapshot materializado (D-04)

# -----------------------------------------------------------------------------
# Thresholds do ValidadorEntrega (prisma retrospectivo do motor)
# -----------------------------------------------------------------------------
JANELA_VALIDACAO_ENTREGA_DIAS = 14  # PRBs com data_encerrado dentro dessa janela entram
LIMIAR_INCS_REINCIDENCIA = 3        # >= INCs no mesmo (produto,servidor) pós-resolução = reincidência
MIN_DIAS_PARA_VALIDAR = 7           # PRB precisa ter >= N dias pós-resolução para virar ENTREGA_VALIDADA
                                    # (abaixo disso, sem INCs novas = INCONCLUSIVO)

# Volumetria pré-resolução: olhar janela ampla para capturar todo o histórico
# que o PRB consolidou (PRBs grandes nascem após meses de INCs recorrentes).
JANELA_VOLUMETRIA_PRE_DIAS = 60     # INCs no mesmo (produto,servidor) antes da resolução

# Delta de chamados pré vs pós-resolução: KPI "os contatos respiraram?".
# Match exato por produto: WHERE chamados.produto = prb.produto. Janela
# simétrica em ambos lados da data_encerrado.
JANELA_CHAMADOS_DELTA_DIAS = 14
# Limiares simétricos para destacar variação significativa no alerta Slack.
# Δ <= LIMIAR_REDUCAO ⇒ ↓ (fix funcionou).
# Δ >= LIMIAR_AUMENTO ⇒ ↑ (fix piorou).
# Default ±0.5 (queda/subida >= 50%). Podem ser calibrados separadamente:
# ex.: LIMIAR_AUMENTO=0.3 alerta subida mais cedo que reduzir o LIMIAR_REDUCAO.
# Valem para o Δ global (V3) e para o Δ por equipe (V3.1, §10 do
# VALIDADOR_ENTREGA.md).
LIMIAR_REDUCAO_CHAMADOS_PCT = -0.5
LIMIAR_AUMENTO_CHAMADOS_PCT = 0.5

# Top N de times internos (dynamics.chamados.equipeproprietaria) reportados no
# bloco "Times impactados" do ValidadorEntrega. Pega as N equipes com mais
# chamados vinculados na janela pré-resolução e mede a redução de cada uma
# na janela simétrica pós-resolução. Original 5 (V3.1, 2026-06-03), ajustado
# para 7 logo em seguida a pedido — equipes com cauda longa cabem no recorte.
TOP_EQUIPES_IMPACTADAS = 7

# -----------------------------------------------------------------------------
# Registry declarativo de tabelas de chamados por organização (Abordagem 2)
# -----------------------------------------------------------------------------
# Cada entrada descreve EXATAMENTE como construir a query SQL para aquela org:
#   - schema/tabela/alias: identificação da tabela principal
#   - join: dict opcional para LEFT JOIN com tabela de classificações (None = sem)
#   - colunas: mapa NOME_LOGICO → EXPRESSAO_SQL (com alias quando há JOIN)
#
# O ChamadosExtractor itera este dict e usa _montar_sql_chamados() para construir
# a SQL final. Adicionar nova organização = só editar este dict (zero código novo).
#
# SEGURANÇA: schema/tabela/alias/colunas SÓ devem vir DAQUI — nunca de input
# externo. Esta é a whitelist que mitiga risco de SQL injection na construção
# dinâmica de SQL.
TABELAS_CHAMADOS_POR_ORGANIZACAO = {
    "Locaweb": {
        "schema": "dynamics",
        "tabela": "chamados",
        "alias": "c",
        "join": {
            "schema": "lw_octadesk",
            "tabela": "classificacoes",
            "alias": "class",
            "chaves": ["nivel1", "nivel2", "nivel3", "nivel4", "nivel5"],
        },
        "colunas": {
            "chamado_id": "c.idchamado",
            "login_cliente": "c.logincliente",
            "data": "c.datacriacao",
            "assunto": "c.assunto",
            "origem": "c.origem",
            "produto": "class.produto",
            "qtd_interacoes_cliente": "c.quantidadeinteracoes",
        },
    },
    "Kinghost": {
        "schema": "kinghost",
        "tabela": "chamados",
        "alias": None,
        "join": None,
        "colunas": {
            "chamado_id": "idchamado",
            "login_cliente": "logincliente",
            "data": "datacriacao",
            "assunto": "assunto",
            "origem": "origem",
            "produto": "fila",
            "qtd_interacoes_cliente": "quantidadedeinteracoescliente",
        },
    },
}

# Chaves obrigatórias em colunas — validadas no startup. Se uma org omitir
# alguma chave, o motor falha rápido (em vez de gerar SQL inválido).
COLUNAS_OBRIGATORIAS_CHAMADOS = (
    "chamado_id", "login_cliente", "data", "assunto",
    "origem", "produto", "qtd_interacoes_cliente",
)


@dataclass
class BancoConfig:
    """Marcador de configuração do banco. A conexão real é resolvida em db.py
    via config.ini compartilhado (mesmo do projeto locapredict).

    Mantém uma propriedade `configurado` para checagens defensivas equivalentes
    às que existiam no antigo ServiceNowConfig (REST).
    """

    @property
    def configurado(self) -> bool:
        try:
            from db import resolve_config_path
            resolve_config_path()
            return True
        except (FileNotFoundError, ImportError):
            return False


def _ler_slack_do_config_ini() -> tuple[str, list[str]]:
    """Lê (bot_token, channels) da seção [slack] do config.ini compartilhado.

    Retorna ("", []) silenciosamente se config.ini não existir ou não tiver [slack].
    Env vars `SLACK_BOT_TOKEN` e `SLACK_CHANNELS` (csv) sobrescrevem.
    """
    import configparser
    token = (os.environ.get("SLACK_BOT_TOKEN") or "").strip()
    channels_env = (os.environ.get("SLACK_CHANNELS") or "").strip()
    canais = [c.strip() for c in channels_env.split(",") if c.strip()] if channels_env else []

    try:
        from db import resolve_config_path
        caminho = resolve_config_path()
        cfg = configparser.ConfigParser()
        cfg.read(caminho, encoding="utf-8")
        if "slack" in cfg:
            if not token:
                token = (cfg["slack"].get("bot_token") or cfg["slack"].get("token_robot") or "").strip()
            if not canais:
                texto = (cfg["slack"].get("channels") or cfg["slack"].get("canais") or "").strip()
                canais = [c.strip() for c in texto.split(",") if c.strip()]
    except (FileNotFoundError, ImportError, Exception):
        pass

    return token, canais


@dataclass
class SlackConfig:
    """Configuração unificada do Slack.

    Suporta dois modos (preferência: Bot Token API, fallback: Webhook):
      - Bot Token (preferido, igual ao locapredict): lê bot_token+channels do
        config.ini [slack] (ou env SLACK_BOT_TOKEN + SLACK_CHANNELS). Usa
        slack_sdk.WebClient.chat_postMessage. Suporta C... (canal) e U... (DM).
      - Webhook (legado): SLACK_WEBHOOK_URL via env. POST direto, canal único.
    """
    bot_token: str = ""
    channels: list[str] = None  # type: ignore[assignment]
    webhook_url: str = os.environ.get("SLACK_WEBHOOK_URL", "")
    canal_criticos: str = os.environ.get("SLACK_CANAL_CRITICOS", "#prb-alertas")
    # Default = true (Slack ligado em produção a partir de 2026-06-03).
    # Pra desligar temporariamente (ex.: dry-run local): $env:SLACK_HABILITADO = "false".
    # Pra desligar permanente: trocar o segundo argumento de "true" pra "false".
    habilitado: bool = os.environ.get("SLACK_HABILITADO", "true").lower() == "true"

    def __post_init__(self) -> None:
        # Resolve dinamicamente do config.ini se ainda vazio (permite
        # instanciar com overrides manuais nos testes sem tocar I/O).
        if not self.bot_token or self.channels is None:
            token, canais = _ler_slack_do_config_ini()
            if not self.bot_token:
                self.bot_token = token
            if self.channels is None:
                self.channels = canais

    @property
    def configurado(self) -> bool:
        if not self.habilitado:
            return False
        return bool(self.bot_token and self.channels) or bool(self.webhook_url)

    @property
    def usa_bot_token(self) -> bool:
        return bool(self.bot_token and self.channels)


# -----------------------------------------------------------------------------
# Modo de operação
# -----------------------------------------------------------------------------
# Quando True, os extractors devolvem dados sintéticos para validação local.
# Default = false: o motor sempre vai ao banco real. Pra ativar o mock localmente,
# seta env USAR_MOCKS=true (ou troca o segundo argumento aqui).
USAR_MOCKS: bool = os.environ.get("USAR_MOCKS", "false").lower() == "true"

# Persistir estado do motor em Postgres (lwsa.motor_*) a cada ciclo.
# Funciona em paralelo ao JSON do dashboard (notifier.gravar_payload_dashboard).
# Quando true, exige que sql/motor_tables.sql tenha sido executado no banco.
PERSISTIR_NO_BANCO: bool = os.environ.get("PERSISTIR_NO_BANCO", "true").lower() == "true"

# TTL para purga automática de execuções antigas (DELETE FROM motor_execucao
# WHERE timestamp_utc < NOW() - INTERVAL 'N days'). Cleanup roda no início de
# cada persistência. ON DELETE CASCADE remove clusters/prescrições/saúdes.
JANELA_TTL_BANCO_DIAS: int = int(os.environ.get("JANELA_TTL_BANCO_DIAS", "30"))

# Habilita/desabilita o cleanup TTL automático. Desabilite (false) se a conta
# do banco não tiver permissão de DELETE — neste caso, limpeza fica a cargo do
# DBA (cron externo, pg_cron, ou manual periódico). Sem cleanup, o banco
# acumula execuções indefinidamente (não é problema operacional até 1-2 anos).
CLEANUP_TTL_HABILITADO: bool = os.environ.get("CLEANUP_TTL_HABILITADO", "false").lower() == "true"

# Habilita/desabilita o snapshot do painel Change Team dentro do ciclo do
# ValidadorEntrega. Default = "true" (feature ligada em produção). Para
# desligar temporariamente (ex.: investigação de issue), no PowerShell:
#   $env:CHANGE_TEAM_HABILITADO = "false"
CHANGE_TEAM_HABILITADO: bool = (
    os.environ.get("CHANGE_TEAM_HABILITADO", "true").lower() == "true"
)

# Fuso horário assumido para as colunas `text` de data no banco (sem tz info).
# Convencionado America/Sao_Paulo (BRT) — confirmar com time de dados se ETL
# upstream usa outro fuso. Mudar aqui basta — time_utils + _parse_datetime
# converte automaticamente para UTC no parse.
TIMEZONE_BANCO = "America/Sao_Paulo"

# Caminho de saída do JSON do dashboard (consumido pelo front-end)
DASHBOARD_OUTPUT_PATH = os.environ.get(
    "DASHBOARD_OUTPUT_PATH",
    "./output/dashboard_state.json",
)

# Diretório de logs
LOG_DIR = os.environ.get("LOG_DIR", "./logs")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")