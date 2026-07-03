# =============================================================================
# Motor Prescritivo PRB — Entry point do ValidadorEntrega (prisma retrospectivo)
# =============================================================================
# Separado do main.py por design: rodada longa (~6h) que olha PRBs já
# entregues, enquanto o motor preventivo roda a cada 15 min em main.py.
#
# Uso:
#   python validar_entregas.py    → executa um ciclo e encerra
#
# A cadência é controlada pelo Windows Task Scheduler (Motor-PRB-Validador.bat)
# — não há mais loop interno. Cada disparo executa uma rodada e sai.
#
# Grava na mesma motor_execucao do banco (compartilha schema). O JSON do
# dashboard fica em arquivo separado pra não sobrescrever o do preventivo.
# =============================================================================
from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime

import config
import time_utils
from extractor import criar_fonte_incidentes, criar_fonte_chamados
from models import ExecucaoMotor
from notifier import disparar_alertas_criticos, gravar_payload_dashboard
from notifier_db import persistir_execucao
from validador_entrega import gerar_validacoes_entrega


JSON_OUTPUT_PATH = "./output/validacoes_entrega.json"


def configurar_logging() -> None:
    """Mesmo formato do main.py, mas arquivo separado para isolar logs."""
    os.makedirs(config.LOG_DIR, exist_ok=True)
    arquivo = os.path.join(
        config.LOG_DIR, f"validador-entrega-{datetime.now().strftime('%Y-%m-%d')}.log"
    )

    nivel = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)-22s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    raiz = logging.getLogger()
    raiz.setLevel(nivel)
    raiz.handlers.clear()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, Exception):
        pass

    handler_console = logging.StreamHandler(sys.stdout)
    handler_console.setFormatter(formatter)
    raiz.addHandler(handler_console)

    handler_arquivo = logging.FileHandler(arquivo, encoding="utf-8")
    handler_arquivo.setFormatter(formatter)
    raiz.addHandler(handler_arquivo)

    logging.getLogger("urllib3").setLevel(logging.WARNING)


def executar_validacao() -> ExecucaoMotor:
    """Roda um ciclo do prisma retrospectivo. Não toca cluster/prescrição/saúde
    — apenas valida entregas. Retorna a ExecucaoMotor para persistência.
    """
    log = logging.getLogger("validador")
    inicio = time.monotonic()

    fonte_inc = criar_fonte_incidentes()
    fonte_chamados = criar_fonte_chamados()
    execucao = ExecucaoMotor(timestamp=time_utils.agora_utc())

    try:
        execucao.validacoes_entrega = gerar_validacoes_entrega(
            fonte_inc, fonte_chamados
        )
    except Exception as exc:
        log.exception("Falha no ValidadorEntrega: %s", exc)
        execucao.erros.append(f"validador_entrega: {exc}")

    # --- BLOCO NOVO Phase 1: Painel Change Team (Defense in Depth — DEC-010) ----
    # Falha aqui NÃO altera execucao.validacoes_entrega (V3.1 CON-012 LOCKED).
    # Imports lazy dentro do `if` pra que ImportError em modulos novos não
    # derrube o ciclo do validador.
    if config.CHANGE_TEAM_HABILITADO:
        try:
            from change_team import gerar_painel_change_team
            from notifier_db import persistir_painel_change_team
            rows_change_team = gerar_painel_change_team(fonte_inc, fonte_chamados)
            persistir_painel_change_team(rows_change_team)
        except Exception as exc:
            log.exception("Falha no Painel Change Team: %s", exc)
            execucao.erros.append(f"change_team: {exc}")
    # ----------------------------------------------------------------------------

    # Persistência: JSON sempre (rede de segurança), Postgres se habilitado.
    try:
        gravar_payload_dashboard(execucao, caminho=JSON_OUTPUT_PATH)
    except Exception as exc:
        log.exception("Falha ao gravar JSON: %s", exc)
        execucao.erros.append(f"json_dashboard: {exc}")

    execucao.duracao_ciclo_ms = int((time.monotonic() - inicio) * 1000)
    persistir_execucao(execucao)

    # Slack — apenas reincidências detectadas.
    # TEMPORÁRIO: desabilitado enquanto refinamos o que mostrar à coordenação.
    _slack_cfg = config.SlackConfig(habilitado=False)
    disparar_alertas_criticos(execucao, _slack_cfg)

    return execucao


def main() -> int:
    configurar_logging()
    log = logging.getLogger("main")

    log.info("ValidadorEntrega iniciado (prisma retrospectivo).")
    log.info(
        "Modo mocks: %s | Janela: %d dias | Logs em %s",
        config.USAR_MOCKS,
        config.JANELA_VALIDACAO_ENTREGA_DIAS,
        config.LOG_DIR,
    )

    execucao = executar_validacao()
    reincidencias = len(execucao.reincidencias_detectadas)
    log.info(
        "Validação concluída: %d validações totais, %d reincidências.",
        len(execucao.validacoes_entrega), reincidencias,
    )
    return 0 if not execucao.erros else 1


if __name__ == "__main__":
    sys.exit(main())
