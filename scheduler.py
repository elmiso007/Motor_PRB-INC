# =============================================================================
# Motor Prescritivo PRB — Pipeline de execução
# =============================================================================
# Orquestra o pipeline completo de uma rodada. Tratamento de erro é defensivo:
# qualquer falha é logada mas NÃO interrompe o pipeline — o motor precisa
# sobreviver a flakiness das APIs ServiceNow/Dynamics.
#
# A cadência é externa (Windows Task Scheduler chama main.py periodicamente).
# Esse módulo expõe apenas executar_ciclo() — não há mais loop interno.
# =============================================================================
from __future__ import annotations

import logging

import config
import time_utils
from models import ExecucaoMotor
import analyzer
import customer_monitor
import notifier
import notifier_db
import rules_engine
from extractor import (
    FonteIncidentes,
    FonteChamados,
)

log = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Pipeline de uma execução
# -----------------------------------------------------------------------------
def executar_ciclo(
    fonte_inc: FonteIncidentes,
    fonte_chamados: FonteChamados,
) -> ExecucaoMotor:
    """Executa uma rodada completa do motor.

    Pipeline:
      1. Extrai INCs (24h) + chamados (24h) + PRBs abertos.
      2. Clusteriza + calcula scores + cruza com volume de chamados.
      3. Aplica regras P1..P5 + sugere repriorizações.
      4. Avalia Saúde dos clientes com volume.
      5. Persiste estado para o dashboard e dispara Slack para críticos.
    """
    inicio = time_utils.agora_utc()
    execucao = ExecucaoMotor(timestamp=inicio)

    # 1. Extração
    try:
        incidentes = fonte_inc.listar_incidentes_recentes(config.JANELA_INC_HORAS)
        execucao.total_incs_lidas = len(incidentes)
        log.info("INCs lidas (24h): %d.", len(incidentes))
    except Exception as exc:
        log.exception("Falha ao extrair INCs: %s", exc)
        execucao.erros.append(f"extrair_incs: {exc}")
        execucao.duracao_ciclo_ms = int(
            (time_utils.agora_utc() - inicio).total_seconds() * 1000
        )
        return execucao

    try:
        chamados = fonte_chamados.listar_chamados_periodo(config.JANELA_DYNAMICS_HORAS)
        execucao.total_chamados = len(chamados)
        log.info("Chamados (24h): %d.", len(chamados))
    except Exception as exc:
        log.warning("Falha ao extrair chamados — seguindo sem cruzamento: %s", exc)
        execucao.erros.append(f"extrair_chamados: {exc}")
        chamados = []

    try:
        prbs_abertos = fonte_inc.listar_prbs_abertos()
        log.info("PRBs abertos lidos: %d.", len(prbs_abertos))
    except Exception as exc:
        log.warning("Falha ao listar PRBs abertos — sem sugestão de repriorização: %s", exc)
        execucao.erros.append(f"listar_prbs: {exc}")
        prbs_abertos = []

    # 2. Análise
    try:
        execucao.clusters = analyzer.analisar(incidentes, chamados)
    except Exception as exc:
        log.exception("Falha na análise: %s", exc)
        execucao.erros.append(f"analisar: {exc}")

    # 3. Regras
    try:
        execucao.prescricoes = rules_engine.prescrever_lote(
            execucao.clusters, prbs_abertos
        )
        log.info(
            "Prescrições geradas: %d (críticas: %d).",
            len(execucao.prescricoes),
            len(execucao.alertas_criticos),
        )
    except Exception as exc:
        log.exception("Falha no rules_engine: %s", exc)
        execucao.erros.append(f"rules_engine: {exc}")

    # 4. Saúde do Cliente
    try:
        execucao.saude_clientes = customer_monitor.gerar_saude_clientes(
            incidentes, fonte_inc, fonte_chamados
        )
    except Exception as exc:
        log.exception("Falha no customer_monitor: %s", exc)
        execucao.erros.append(f"saude_cliente: {exc}")

    # 5. Saídas (não bloqueiam execução em caso de falha)
    # 5a. Dashboard JSON (fallback / consumo simples)
    try:
        notifier.gravar_payload_dashboard(execucao)
    except Exception as exc:
        log.exception("Falha ao gravar dashboard JSON: %s", exc)
        execucao.erros.append(f"dashboard_json: {exc}")

    # Métrica de duração até aqui (tempo de processamento) — populada ANTES da
    # persistência Postgres para ser gravada na coluna duracao_ciclo_ms.
    # Não inclui Slack (que pode demorar muito com rate limit defensivo).
    execucao.duracao_ciclo_ms = int(
        (time_utils.agora_utc() - inicio).total_seconds() * 1000
    )

    # 5b. Persistência Postgres (lwsa.motor_*) — fonte para análises temporais
    try:
        notifier_db.persistir_execucao(execucao)
    except Exception as exc:
        log.exception("Falha ao persistir no banco: %s", exc)
        execucao.erros.append(f"dashboard_db: {exc}")

    # 5c. Slack (alertas críticos)
    try:
        notifier.disparar_alertas_criticos(execucao)
    except Exception as exc:
        log.exception("Falha ao disparar Slack: %s", exc)
        execucao.erros.append(f"slack: {exc}")

    # Log final mostra ambos (persistido vs. total incluindo Slack).
    duracao_total_ms = int((time_utils.agora_utc() - inicio).total_seconds() * 1000)
    log.info(
        "Ciclo executado em %d ms (processamento: %d ms, Slack: %d ms).",
        duracao_total_ms,
        execucao.duracao_ciclo_ms,
        duracao_total_ms - execucao.duracao_ciclo_ms,
    )

    return execucao