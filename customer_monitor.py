# =============================================================================
# Motor Prescritivo PRB — Customer Monitor (Saúde do Cliente)
# =============================================================================
# Requisito original (Emerson/Bruno): para cada cliente com >= 3 INCs nos
# últimos 6 meses, montar a linha do tempo consolidada (ServiceNow + Dynamics) e
# emitir alerta de recorrência alta. Poupa o trabalho manual do analista de
# garimpar histórico chamado-a-chamado no plantão.
# =============================================================================
from __future__ import annotations

import logging
from collections import Counter
from datetime import timedelta
from typing import Dict, List, Sequence

import config
import time_utils
from extractor import FonteIncidentes, FonteChamados
from models import SaudeCliente, Incidente, InteracaoChamado

log = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Identificação de clientes com volume relevante
# -----------------------------------------------------------------------------
def _clientes_com_volume(
    incidentes: Sequence[Incidente], limiar: int = config.LIMIAR_INCS_SAUDE_CLIENTE
) -> List[str]:
    """Retorna logins com >= `limiar` INCs nas INCs já carregadas (janela atual).

    Filtra por tipo_usuario quando config.TIPOS_USUARIO_SAUDE_CLIENTE estiver
    populado. INCs de monitoração (tipo_usuario = "Integração") são abertas
    por sistema e não têm cliente associado — não fazem sentido para Saúde
    do Cliente. Se a tupla estiver vazia, todas as INCs são consideradas.
    """
    tipos_aceitos = config.TIPOS_USUARIO_SAUDE_CLIENTE
    contagem: Counter[str] = Counter(
        i.login_cliente for i in incidentes
        if i.login_cliente
        and (not tipos_aceitos or i.tipo_usuario in tipos_aceitos)
    )
    return [login for login, n in contagem.items() if n >= limiar]


# -----------------------------------------------------------------------------
# Detecção de atividade recente (anti alert fatigue)
# -----------------------------------------------------------------------------
def _tem_inc_recente(incs: Sequence[Incidente], dias: int) -> bool:
    """True se o cliente tem ao menos uma INC nos últimos N dias.

    Critério complementar ao volume — evita disparar alerta crônico para cliente
    com histórico antigo mas sem atividade recente (cliente que 'acalmou' não
    deve inundar Slack pelos próximos meses só porque ainda está na janela de
    6 meses).
    """
    if not incs:
        return False
    corte = time_utils.agora_utc() - timedelta(days=dias)
    return any(i.abertura >= corte for i in incs)


# -----------------------------------------------------------------------------
# Cálculo de severidade média do cliente
# -----------------------------------------------------------------------------
def _calcular_severidade_media(incs: Sequence[Incidente]) -> float:
    """Média ponderada das prioridades das INCs do cliente.

    Range 0.0 (cliente com tudo P5 — rotineiro) a 1.0 (tudo P1 — crítico).
    Mapeamento em config.PESO_PRIORIDADE_SEVERIDADE.

    Default 0.0 se lista vazia. Prioridade desconhecida (fora do mapa) é
    contada como peso 0.0 — equivalente a P5 — comportamento conservador.
    """
    if not incs:
        return 0.0
    pesos = [
        config.PESO_PRIORIDADE_SEVERIDADE.get(i.prioridade_atual, 0.0)
        for i in incs
    ]
    return round(sum(pesos) / len(pesos), 3)


# -----------------------------------------------------------------------------
# Construção da linha do tempo consolidada
# -----------------------------------------------------------------------------
def _montar_linha_do_tempo(
    incs: Sequence[Incidente], chamados: Sequence[InteracaoChamado]
) -> List[Dict]:
    """Mescla INCs e chamados em ordem cronológica decrescente."""
    eventos: List[Dict] = []
    for inc in incs:
        eventos.append({
            "fonte": "ServiceNow",
            "tipo": "INC",
            "id": inc.inc_id,
            "data": inc.abertura.isoformat(),
            "produto": inc.produto,
            "ci": inc.servidor,
            "prioridade": inc.prioridade_atual,
            "resumo": inc.descricao_curta,
            "tem_contorno": inc.tem_solucao_contorno,
        })
    for chamado in chamados:
        eventos.append({
            "fonte": chamado.organizacao or "Chamado",  # "Locaweb" ou "Kinghost"
            "tipo": "Chamado",
            "id": chamado.chamado_id,
            "data": chamado.data.isoformat(),
            "produto": chamado.produto,
            "origem": chamado.origem,
            "resumo": chamado.assunto,
        })
    eventos.sort(key=lambda e: e["data"], reverse=True)
    return eventos


# -----------------------------------------------------------------------------
# API pública
# -----------------------------------------------------------------------------
def gerar_saude_clientes(
    incidentes_janela: Sequence[Incidente],
    fonte_incidentes: FonteIncidentes,
    fonte_chamados: FonteChamados,
) -> List[SaudeCliente]:
    """Para cada cliente com volume >= limiar na janela de candidatos, busca o
    histórico completo de 6 meses (ServiceNow + chamados Locaweb/Kinghost) e
    devolve uma avaliação de Saúde do Cliente.

    Janela de candidatos: se JANELA_CANDIDATOS_SAUDE_DIAS resulta em mais horas
    que JANELA_INC_HORAS, abre uma 2ª query ao extractor para olhar período
    maior — cliente real raramente acumula 3 INCs em 24h. Caso contrário,
    reusa `incidentes_janela` (sem custo extra).
    """
    horas_candidatos = config.JANELA_CANDIDATOS_SAUDE_DIAS * 24
    if horas_candidatos > config.JANELA_INC_HORAS:
        # Janela longa: usa query agregada (GROUP BY login) — leve, não estoura
        # memória mesmo com 30+ dias de histórico.
        try:
            contagem = fonte_incidentes.contar_clientes_com_inc_recente(
                horas_candidatos, config.TIPOS_USUARIO_SAUDE_CLIENTE
            )
            candidatos = [
                login for login, n in contagem.items()
                if n >= config.LIMIAR_INCS_SAUDE_CLIENTE
            ]
            log.info(
                "Saúde do Cliente: janela ampliada para %d dias (%d clientes Nominais, %d com >= %d INCs).",
                config.JANELA_CANDIDATOS_SAUDE_DIAS,
                len(contagem),
                len(candidatos),
                config.LIMIAR_INCS_SAUDE_CLIENTE,
            )
        except Exception as exc:
            log.warning(
                "Falha ao ampliar janela — caindo para janela padrão (%dh): %s",
                config.JANELA_INC_HORAS, exc,
            )
            candidatos = _clientes_com_volume(
                list(incidentes_janela), limiar=config.LIMIAR_INCS_SAUDE_CLIENTE
            )
    else:
        candidatos = _clientes_com_volume(
            list(incidentes_janela), limiar=config.LIMIAR_INCS_SAUDE_CLIENTE
        )

    log.info(
        "Clientes candidatos a avaliacao de saude (>=%d INCs): %d -> %s",
        config.LIMIAR_INCS_SAUDE_CLIENTE, len(candidatos), candidatos,
    )

    # Bulk: 1 query SQL traz histórico de TODOS os candidatos (vs N×2 antes).
    # Reduz round-trips de ~36 para ~3 — vitória grande contra latência de VPN/rede.
    try:
        incs_por_cliente = fonte_incidentes.listar_incidentes_para_saude(
            candidatos, meses=config.JANELA_SAUDE_CLIENTE_MESES
        )
    except Exception as exc:
        log.warning("Bulk INCs indisponível — saúde será baseada só na janela atual: %s", exc)
        incs_por_cliente = {
            login: [i for i in incidentes_janela if i.login_cliente == login]
            for login in candidatos
        }

    try:
        chamados_por_cliente = fonte_chamados.listar_chamados_para_saude(
            candidatos, meses=config.JANELA_SAUDE_CLIENTE_MESES
        )
    except Exception as exc:
        log.warning("Bulk chamados indisponível — saúde sem chamados: %s", exc)
        chamados_por_cliente = {login: [] for login in candidatos}

    saude_clientes: List[SaudeCliente] = []
    for login in candidatos:
        incs_historicas = incs_por_cliente.get(login, [])
        chamados = chamados_por_cliente.get(login, [])

        qtd_incs = len(incs_historicas)
        qtd_chamados = len(chamados)
        # Veredicto exige volume (recorrência) E atividade recente (anti alert
        # fatigue). Cliente com histórico antigo mas inativo agora não inunda Slack.
        recorrencia_alta = (
            qtd_incs >= config.LIMIAR_INCS_SAUDE_CLIENTE
            and _tem_inc_recente(incs_historicas, config.JANELA_RECENCIA_ALERTA_DIAS)
        )
        severidade = _calcular_severidade_media(incs_historicas)

        saude_clientes.append(SaudeCliente(
            cliente_login=login,
            qtd_incs_periodo=qtd_incs,
            qtd_chamados_periodo=qtd_chamados,
            severidade_media=severidade,
            incs=list(incs_historicas),
            chamados=list(chamados),
            alerta_recorrencia_alta=recorrencia_alta,
            linha_do_tempo=_montar_linha_do_tempo(incs_historicas, chamados),
        ))

    # Ordena por volume total decrescente (cliente "mais barulhento" primeiro)
    saude_clientes.sort(
        key=lambda c: c.qtd_incs_periodo + c.qtd_chamados_periodo,
        reverse=True,
    )
    log.info("Saude de clientes avaliada: %d.", len(saude_clientes))
    return saude_clientes