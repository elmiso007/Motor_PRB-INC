# =============================================================================
# Motor Prescritivo PRB — Entry point
# =============================================================================
# Uso:
#   python main.py    → executa um ciclo e encerra
#
# A cadência é controlada pelo Windows Task Scheduler (Motor-PRB.bat) — não
# há mais loop interno. Cada disparo do scheduler chama esse script que roda
# uma única rodada do pipeline e sai com 0 (sucesso) ou 1 (houve erro).
# =============================================================================
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime

import config
from extractor import criar_fonte_incidentes, criar_fonte_chamados
from scheduler import executar_ciclo


def configurar_logging() -> None:
    """Logging para console + arquivo rotacionado por dia."""
    os.makedirs(config.LOG_DIR, exist_ok=True)
    # Nome de arquivo usa data LOCAL (BRT) propositalmente — operador olhando
    # a pasta de logs prefere ver datas no fuso local. Demais usos do motor
    # padronizam UTC via time_utils.agora_utc().
    arquivo = os.path.join(
        config.LOG_DIR, f"motor-prb-{datetime.now().strftime('%Y-%m-%d')}.log"
    )

    nivel = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)-22s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    raiz = logging.getLogger()
    raiz.setLevel(nivel)
    # Evita handlers duplicados quando o módulo é re-importado
    raiz.handlers.clear()

    # Console em UTF-8 (cp1252 padrão do Windows quebra com emojis/setas).
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

    # Silencia ruído de libs externas
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def main() -> int:
    configurar_logging()
    log = logging.getLogger("main")

    log.info("Motor Prescritivo PRB iniciado.")
    log.info("Modo mocks: %s | Logs em %s", config.USAR_MOCKS, config.LOG_DIR)

    # Slack — escolha uma das opções abaixo:
    # slack_cfg = config.SlackConfig(channels=["C07NSPQ69TL"])  # canal de teste
    slack_cfg = config.SlackConfig(channels=["C08C34VKB5Y", "U06V8A8GF5L"])  # canal oficial
    # slack_cfg = config.SlackConfig(habilitado=False)  # desabilitado
    log.info("Disparo Slack habilitado: %s", slack_cfg.configurado)

    fonte_inc = criar_fonte_incidentes()
    fonte_chamados = criar_fonte_chamados()
    execucao = executar_ciclo(
        fonte_inc,
        fonte_chamados,
        slack_cfg=slack_cfg,
    )
    log.info(
        "Execução concluída: %d clusters, %d prescrições, %d saúde de clientes.",
        len(execucao.clusters), len(execucao.prescricoes), len(execucao.saude_clientes),
    )
    return 0 if not execucao.erros else 1


if __name__ == "__main__":
    sys.exit(main())
