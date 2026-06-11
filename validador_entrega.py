# =============================================================================
# Motor Prescritivo PRB — Validador de Entrega (prisma retrospectivo)
# =============================================================================
# Complementa os prismas preventivos (Rules Engine + Customer Monitor) com uma
# leitura retrospectiva: para cada PRB que o Change Team entregou nos últimos
# N dias, conta INCs novas no mesmo (produto, servidor) e emite veredicto.
#
# Veredictos:
#   - REINCIDENCIA      → ≥ LIMIAR_INCS_REINCIDENCIA INCs pós-resolução.
#                         Dispara Slack imediato pro Change Team.
#   - ENTREGA_VALIDADA  → 0 INCs pós-resolução E dias_pos_resolucao ≥
#                         MIN_DIAS_PARA_VALIDAR.
#                         Janela suficientemente longa sem regressão.
#   - INCONCLUSIVO      → caso intermediário (pouco tempo desde resolução,
#                         poucas INCs sob o limiar, etc.). Continua sob observação.
# =============================================================================
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Dict, List, Optional

import config
import time_utils
from extractor import FonteIncidentes, FonteChamados
from models import Incidente, PRBExistente, ValidacaoEntrega

log = logging.getLogger(__name__)


VEREDICTO_REINCIDENCIA = "REINCIDENCIA"
VEREDICTO_VALIDADA = "ENTREGA_VALIDADA"
VEREDICTO_INCONCLUSIVO = "INCONCLUSIVO"


def _classificar(qtd_incs: int, dias_pos: int) -> str:
    """Aplica a matriz simples de veredicto.

    A ordem importa: REINCIDENCIA tem precedência sobre tempo de janela —
    se aparecer reincidência ainda no 2º dia, é reincidência mesmo assim.
    """
    if qtd_incs >= config.LIMIAR_INCS_REINCIDENCIA:
        return VEREDICTO_REINCIDENCIA
    if qtd_incs == 0 and dias_pos >= config.MIN_DIAS_PARA_VALIDAR:
        return VEREDICTO_VALIDADA
    return VEREDICTO_INCONCLUSIVO


def _avaliar_prb(
    prb: PRBExistente,
    fonte_inc: FonteIncidentes,
    fonte_chamados: Optional[FonteChamados] = None,
) -> ValidacaoEntrega:
    """Calcula veredicto + contexto enriquecido de um único PRB.

    Sinais coletados:
      1. Veredicto (REINCIDENCIA / ENTREGA_VALIDADA / INCONCLUSIVO) baseado em
         INCs no mesmo (produto, servidor) após data_encerrado.
      2. Volumetria pré-resolução — INCs nos `JANELA_VOLUMETRIA_PRE_DIAS` antes
         do fix. Mede tamanho do problema que o Change Team resolveu.
      3. Delta de chamados pré vs pós — match exato por `chamados.produto =
         prb.produto`. Mede se o suporte respirou após o fix.

    PRBs sem data_resolucao (ex.: Aguardando Validação ainda sem encerramento
    formal) são tratados com data_resolucao = data_abertura como salvaguarda —
    veredicto fica INCONCLUSIVO até o status virar 'Encerrado Automaticamente'.
    """
    agora = time_utils.agora_utc()
    data_ref = prb.data_resolucao or prb.aberto_em or agora
    dias_pos = max(0, (agora - data_ref).days)

    # Sem produto ou servidor não dá pra fazer match — INCONCLUSIVO.
    if not prb.produto or not prb.servidor:
        log.debug(
            "PRB %s sem produto/servidor — pulando match de reincidência.", prb.prb_id
        )
        return ValidacaoEntrega(
            prb_id=prb.prb_id,
            descricao_curta=prb.descricao_curta,
            produto=prb.produto,
            servidor=prb.servidor,
            status_prb=prb.status,
            data_resolucao=data_ref,
            dias_pos_resolucao=dias_pos,
            qtd_incs_pos_resolucao=0,
            veredicto=VEREDICTO_INCONCLUSIVO,
            incs_reincidentes=[],
            grupo_designado=prb.grupo_designado,
            data_abertura_prb=prb.aberto_em,
        )

    incs_pos: List[Incidente] = fonte_inc.listar_incidentes_por_produto_servidor(
        produto=prb.produto, servidor=prb.servidor, desde=data_ref
    )

    qtd = len(incs_pos)
    veredicto = _classificar(qtd, dias_pos)

    # --- Volumetria pré-resolução -----------------------------------------
    try:
        vol_pre = fonte_inc.contar_incidentes_no_ci_periodo(
            produto=prb.produto,
            servidor=prb.servidor,
            desde=data_ref - timedelta(days=config.JANELA_VOLUMETRIA_PRE_DIAS),
            ate=data_ref,
        )
    except Exception as exc:
        log.warning("Falha ao calcular volumetria pré de %s: %s", prb.prb_id, exc)
        vol_pre = {"qtd": 0, "clientes_unicos": 0, "categorias": 0}

    # --- Delta de chamados pré vs pós (V3: match por prb/inc vinculados) ---
    # Substitui o match por produto (V2) — usa as colunas dynamics.chamados.prb
    # e dynamics.chamados.inc pra contar APENAS chamados realmente vinculados.
    # Inclui também o agrupamento por equipeproprietaria (top N): identifica
    # QUEM (time interno Locaweb) estava chamando antes do fix e o quanto
    # reduziu depois — pedido do coordenador (2026-06-03).
    chamados_pre = chamados_pos = 0
    equipes_pre: Dict[str, int] = {}
    equipes_pos: Dict[str, int] = {}
    equipes_delta_pct: Dict[str, float] = {}
    if fonte_chamados is not None:
        janela = timedelta(days=config.JANELA_CHAMADOS_DELTA_DIAS)
        try:
            # Levantar INCs do CI em cada janela (lista de inc_ids).
            incs_pre = fonte_inc.listar_incidentes_por_produto_servidor(
                produto=prb.produto, servidor=prb.servidor,
                desde=data_ref - janela, ate=data_ref,
            )
            incs_ids_pre = [i.inc_id for i in incs_pre if i.inc_id]
            incs_ids_pos = [i.inc_id for i in incs_pos if i.inc_id]

            chamados_pre = fonte_chamados.contar_chamados_vinculados(
                prb_id=prb.prb_id,
                incs_ids=incs_ids_pre,
                desde=data_ref - janela,
                ate=data_ref,
            )
            chamados_pos = fonte_chamados.contar_chamados_vinculados(
                prb_id=prb.prb_id,
                incs_ids=incs_ids_pos,
                desde=data_ref,
                ate=data_ref + janela,
            )

            # Top N times internos com chamados vinculados pré-resolução
            # (mais impactados pelo problema). Limita pelo PRÉ — são os
            # times que estavam chamando; depois medimos a redução de cada.
            ranking_pre = fonte_chamados.agrupar_chamados_vinculados_por_equipe(
                prb_id=prb.prb_id, incs_ids=incs_ids_pre,
                desde=data_ref - janela, ate=data_ref,
            )
            equipes_pre = dict(
                list(ranking_pre.items())[: config.TOP_EQUIPES_IMPACTADAS]
            )
            if equipes_pre:
                ranking_pos = fonte_chamados.agrupar_chamados_vinculados_por_equipe(
                    prb_id=prb.prb_id, incs_ids=incs_ids_pos,
                    desde=data_ref, ate=data_ref + janela,
                )
                for equipe, qtd_pre_equipe in equipes_pre.items():
                    qtd_pos_equipe = ranking_pos.get(equipe, 0)
                    equipes_pos[equipe] = qtd_pos_equipe
                    equipes_delta_pct[equipe] = (
                        round((qtd_pos_equipe - qtd_pre_equipe) / qtd_pre_equipe, 3)
                        if qtd_pre_equipe > 0 else 0.0
                    )
        except Exception as exc:
            log.warning(
                "Falha ao contar chamados pré/pós de %s: %s", prb.prb_id, exc
            )

    # Delta percentual relativo ao pré. Sem pré (0), reporta 0.0 (não pode
    # dividir por 0 — sem base, percentual não tem significado).
    delta_pct = (chamados_pos - chamados_pre) / chamados_pre if chamados_pre > 0 else 0.0

    # --- PRBs novos abertos no CI após a resolução ------------------------
    # Complementa a contagem de INCs reincidentes: se o mesmo (produto, servidor)
    # gerou um PRB NOVO depois do fechamento, indica retorno do problema.
    try:
        prbs_novos = fonte_inc.listar_prbs_novos_no_ci_periodo(
            produto=prb.produto,
            servidor=prb.servidor,
            desde=data_ref,
            ignorar_prb_id=prb.prb_id,
        )
    except Exception as exc:
        log.warning("Falha ao listar PRBs novos pós-resolução de %s: %s", prb.prb_id, exc)
        prbs_novos = []

    return ValidacaoEntrega(
        prb_id=prb.prb_id,
        descricao_curta=prb.descricao_curta,
        produto=prb.produto,
        servidor=prb.servidor,
        status_prb=prb.status,
        data_resolucao=data_ref,
        dias_pos_resolucao=dias_pos,
        qtd_incs_pos_resolucao=qtd,
        veredicto=veredicto,
        incs_reincidentes=incs_pos,
        grupo_designado=prb.grupo_designado,
        data_abertura_prb=prb.aberto_em,
        qtd_incs_pre_resolucao=vol_pre["qtd"],
        clientes_unicos_pre=vol_pre["clientes_unicos"],
        categorias_pre=vol_pre["categorias"],
        chamados_pre=chamados_pre,
        chamados_pos=chamados_pos,
        delta_chamados_pct=round(delta_pct, 3),
        qtd_prbs_novos_pos_resolucao=len(prbs_novos),
        prbs_novos=prbs_novos,
        equipes_impactadas_pre=equipes_pre,
        equipes_impactadas_pos=equipes_pos,
        equipes_delta_pct=equipes_delta_pct,
    )


def gerar_validacoes_entrega(
    fonte_incidentes: FonteIncidentes,
    fonte_chamados: Optional[FonteChamados] = None,
) -> List[ValidacaoEntrega]:
    """Roda o prisma retrospectivo: lista PRBs encerrados na janela e avalia cada um.

    `fonte_chamados` é opcional: quando presente, ativa o cálculo de delta
    de chamados pré/pós-resolução. Quando ausente, o validador devolve apenas
    veredicto + INCs reincidentes + volumetria pré (sem delta).

    Falha defensiva: se um PRB der erro durante a avaliação, registra e continua
    com os demais — não derruba o ciclo inteiro por causa de um caso ruim.
    """
    try:
        prbs = fonte_incidentes.listar_prbs_para_validacao(
            config.JANELA_VALIDACAO_ENTREGA_DIAS
        )
    except Exception as exc:
        log.error("Falha ao listar PRBs para validação: %s", exc)
        return []

    log.info("PRBs candidatos a validação de entrega: %d.", len(prbs))

    validacoes: List[ValidacaoEntrega] = []
    for prb in prbs:
        try:
            validacoes.append(_avaliar_prb(prb, fonte_incidentes, fonte_chamados))
        except Exception as exc:
            log.warning("Falha ao validar entrega de %s: %s", prb.prb_id, exc)

    # Ordena por urgência (reincidências primeiro, depois por dias_pos_resolucao desc)
    ordem_veredicto = {
        VEREDICTO_REINCIDENCIA: 0,
        VEREDICTO_INCONCLUSIVO: 1,
        VEREDICTO_VALIDADA: 2,
    }
    validacoes.sort(
        key=lambda v: (ordem_veredicto.get(v.veredicto, 9), -v.dias_pos_resolucao)
    )

    contagem = {v: 0 for v in (
        VEREDICTO_REINCIDENCIA, VEREDICTO_VALIDADA, VEREDICTO_INCONCLUSIVO
    )}
    for v in validacoes:
        contagem[v.veredicto] = contagem.get(v.veredicto, 0) + 1
    log.info(
        "Validações de entrega: %d (reincidência: %d, validada: %d, inconclusivo: %d).",
        len(validacoes),
        contagem[VEREDICTO_REINCIDENCIA],
        contagem[VEREDICTO_VALIDADA],
        contagem[VEREDICTO_INCONCLUSIVO],
    )
    return validacoes