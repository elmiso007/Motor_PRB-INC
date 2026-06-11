# =============================================================================
# Motor Prescritivo PRB — Rules Engine (matriz oficial P1-P5)
# =============================================================================
# Coração regulatório do motor. Implementa a matriz oficial de priorização de
# PRBs/INCs em cascata (P1 → P5, a primeira que casar vence) e produz uma
# PrescricaoPRB auditável (todas as justificativas são acumuladas como bullets).
#
# Regras implementadas:
#   - Avaliação P1..P5 conforme matriz da documentação interna.
#   - Gatilho proativo: >= 5 INCs P3 com mesmo assunto → sugerir abertura de PRB.
#   - Sugestão de repriorização: PRB já aberto cuja realidade atual bate em
#     prioridade mais alta (Jéssica: "Mudar de P3 para P2").
#
# Decisões importantes:
#   - Funções puras (recebem Cluster, devolvem PrescricaoPRB). Sem I/O aqui.
#   - Cada regra grava uma string de justificativa — o front-end e o Slack
#     podem renderizar essa lista verbatim para fins de auditoria.
# =============================================================================
from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import List, Optional, Sequence

import config
from models import Cluster, Incidente, PrescricaoPRB, PRBExistente

log = logging.getLogger(__name__)


# Mapeamento urgência (cascata) → P-level oficial
MAPA_URGENCIA_PRIORIDADE = {
    "CRITICA": "P1",
    "ALTA": "P2",
    "MEDIA": "P3",
    "BAIXA": "P4",
    "PLANEJADO": "P5",
}

# Ordem numérica para comparar prioridades (menor = mais grave)
ORDEM_PRIORIDADE = {"P1": 1, "P2": 2, "P3": 3, "P4": 4, "P5": 5}


# -----------------------------------------------------------------------------
# Helpers de detecção textual
# -----------------------------------------------------------------------------
@lru_cache(maxsize=None)
def _compilar_pattern_termos(termos: tuple) -> "re.Pattern":
    """Compila regex case-insensitive que casa termos como palavras/expressões
    completas (word boundary `\\b`).

    Crucial para evitar falso positivo de siglas curtas — ex.: "ra" não pode
    casar dentro de "fora", "agora", "para". A boundary garante que só
    casamentos em posições reais de palavra contam.

    O resultado é cacheado: mesma tupla de termos não recompila a regex.
    """
    escaped = [re.escape(t) for t in termos]
    return re.compile(r"\b(?:" + "|".join(escaped) + r")\b", re.IGNORECASE)


def _qualquer_termo_no_cluster(cluster: Cluster, termos: Sequence[str]) -> bool:
    """True se qualquer INC do cluster contém qualquer termo como palavra/expressão completa."""
    pattern = _compilar_pattern_termos(tuple(termos))
    for inc in cluster.incidentes:
        if pattern.search(inc.texto_busca):
            return True
    return False


def _qtd_sem_contorno(cluster: Cluster) -> int:
    return sum(1 for i in cluster.incidentes if not i.tem_solucao_contorno)


def _qtd_com_contorno(cluster: Cluster) -> int:
    return sum(1 for i in cluster.incidentes if i.tem_solucao_contorno)


def _ola_estourado_implicito(cluster: Cluster) -> bool:
    """Heurística MVP: cluster com ineficiência alta + sem contorno sugere OLA
    estourado. Em produção, ler `breach_time` do ServiceNow."""
    return cluster.score_ineficiencia >= 0.6 and _qtd_sem_contorno(cluster) > 0


# -----------------------------------------------------------------------------
# Avaliação P1 (Crise)
# -----------------------------------------------------------------------------
def _avaliar_p1(cluster: Cluster) -> Optional[List[str]]:
    """Retorna lista de justificativas se P1, senão None.

    Critérios oficiais (qualquer um):
      - Reclame Aqui sem contorno COM OLA estourado
      - Contratação indisponível (sem contorno total)
      - Funcionalidade do CAL/Central/Painel Indisponível Total
      - Risco para o negócio / falha de segurança
    """
    justificativas: List[str] = []

    tem_reclame_aqui = _qualquer_termo_no_cluster(cluster, config.TERMOS_RECLAME_AQUI)
    tem_sem_contorno_explicito = _qualquer_termo_no_cluster(
        cluster, config.TERMOS_SEM_CONTORNO
    )
    sem_contorno = _qtd_sem_contorno(cluster) == cluster.qtd_incs

    if tem_reclame_aqui and sem_contorno and _ola_estourado_implicito(cluster):
        justificativas.append(
            "Reclame Aqui sem solução de contorno e OLA estourado (P1)."
        )
        return justificativas

    contratacao = _qualquer_termo_no_cluster(cluster, config.TERMOS_CONTRATACAO)
    indisponivel = _qualquer_termo_no_cluster(
        cluster, config.TERMOS_INDISPONIBILIDADE_TOTAL
    )

    if contratacao and indisponivel and sem_contorno:
        justificativas.append(
            "Contratação indisponível, sem solução de contorno total (P1)."
        )
        return justificativas

    if indisponivel and any(
        t in (cluster.produto or "").lower()
        for t in ["cal", "central do cliente", "painel"]
    ):
        justificativas.append(
            f"Funcionalidade do {cluster.produto} indisponível total (P1)."
        )
        return justificativas

    if _qualquer_termo_no_cluster(cluster, config.TERMOS_RISCO_SEGURANCA):
        justificativas.append("Risco para o negócio / falha de segurança detectado (P1).")
        return justificativas

    return None


# -----------------------------------------------------------------------------
# Avaliação P2 (Alta)
# -----------------------------------------------------------------------------
def _avaliar_p2(cluster: Cluster) -> Optional[List[str]]:
    """Critérios oficiais (qualquer um):
      - Reclame Aqui sem solução de contorno (mas sem OLA estourado, senão é P1)
      - Contratação indisponível parcial sem contorno
      - >= 5 INCs sem solução de contorno
      - >= 100 INCs com contorno OR contorno >= 60 min
      - Funcionalidade do CAL/Central/Painel Indisponível Parcial OR
        Ferramenta Interna Indisponível Total
      - Impacto na instalação de novos servidores dedicados
    """
    justificativas: List[str] = []

    tem_reclame_aqui = _qualquer_termo_no_cluster(cluster, config.TERMOS_RECLAME_AQUI)
    qtd_sem = _qtd_sem_contorno(cluster)
    qtd_com = _qtd_com_contorno(cluster)

    if tem_reclame_aqui and qtd_sem > 0:
        justificativas.append(
            "Reclame Aqui com INCs sem solução de contorno (P2)."
        )

    if qtd_sem >= config.LIMIAR_P2_INCS_SEM_CONTORNO:
        justificativas.append(
            f"{qtd_sem} INCs sem contorno (limiar P2: "
            f"{config.LIMIAR_P2_INCS_SEM_CONTORNO})."
        )

    if qtd_com >= config.LIMIAR_P2_INCS_COM_CONTORNO:
        justificativas.append(
            f"{qtd_com} INCs com contorno (limiar P2: "
            f"{config.LIMIAR_P2_INCS_COM_CONTORNO})."
        )

    if (
        cluster.tem_solucao_contorno
        and cluster.tempo_contorno_min_medio >= config.LIMIAR_P2_CONTORNO_MIN
    ):
        justificativas.append(
            f"Tempo médio de contorno {cluster.tempo_contorno_min_medio}min "
            f">= {config.LIMIAR_P2_CONTORNO_MIN}min (P2)."
        )

    if "instalacao" in cluster.nome.lower() or "instalação" in cluster.nome.lower():
        if any(
            "dedicado" in (i.produto or "").lower() for i in cluster.incidentes
        ):
            justificativas.append(
                "Impacto na instalação de novos servidores dedicados (P2)."
            )

    return justificativas if justificativas else None


# -----------------------------------------------------------------------------
# Avaliação P3 (Média)
# -----------------------------------------------------------------------------
def _avaliar_p3(cluster: Cluster) -> Optional[List[str]]:
    """Critérios oficiais (qualquer um):
      - Reclame Aqui com solução de contorno
      - Sem solução de contorno E < 5 INCs
      - Com contorno E entre 20-100 INCs
      - Com contorno entre 10-60 min
      - Ferramenta interna indisponível parcial
    """
    justificativas: List[str] = []

    qtd_sem = _qtd_sem_contorno(cluster)
    qtd_com = _qtd_com_contorno(cluster)

    tem_reclame_aqui = _qualquer_termo_no_cluster(cluster, config.TERMOS_RECLAME_AQUI)
    if tem_reclame_aqui and cluster.tem_solucao_contorno:
        justificativas.append("Reclame Aqui com solução de contorno (P3).")

    if 0 < qtd_sem < config.LIMIAR_P2_INCS_SEM_CONTORNO:
        justificativas.append(
            f"{qtd_sem} INCs sem contorno (< {config.LIMIAR_P2_INCS_SEM_CONTORNO}) → P3."
        )

    if (
        config.LIMIAR_P3_INCS_COM_CONTORNO_MIN
        <= qtd_com
        < config.LIMIAR_P3_INCS_COM_CONTORNO_MAX
    ):
        justificativas.append(
            f"{qtd_com} INCs com contorno (faixa "
            f"{config.LIMIAR_P3_INCS_COM_CONTORNO_MIN}-"
            f"{config.LIMIAR_P3_INCS_COM_CONTORNO_MAX}) → P3."
        )

    if (
        cluster.tem_solucao_contorno
        and config.LIMIAR_P3_CONTORNO_MIN_INICIO
        <= cluster.tempo_contorno_min_medio
        < config.LIMIAR_P3_CONTORNO_MIN_FIM
    ):
        justificativas.append(
            f"Tempo médio de contorno {cluster.tempo_contorno_min_medio}min "
            f"(faixa P3)."
        )

    return justificativas if justificativas else None


# -----------------------------------------------------------------------------
# Avaliação P4 (Baixa)
# -----------------------------------------------------------------------------
def _avaliar_p4(cluster: Cluster) -> Optional[List[str]]:
    """Critérios: com contorno E (< 20 INCs OR contorno < 10 min)."""
    if not cluster.tem_solucao_contorno:
        return None

    qtd_com = _qtd_com_contorno(cluster)
    poucas_incs = qtd_com < config.LIMIAR_P4_INCS_COM_CONTORNO_MAX
    contorno_rapido = (
        0 < cluster.tempo_contorno_min_medio < config.LIMIAR_P4_CONTORNO_MAX_MIN
    )

    if poucas_incs or contorno_rapido:
        partes = []
        if poucas_incs:
            partes.append(f"{qtd_com} INCs com contorno (< 20)")
        if contorno_rapido:
            partes.append(f"contorno rápido ({cluster.tempo_contorno_min_medio}min < 10)")
        return [f"P4: {' e '.join(partes)}."]
    return None


# -----------------------------------------------------------------------------
# Cascata principal
# -----------------------------------------------------------------------------
def _avaliar_cascata(cluster: Cluster) -> tuple[str, str, List[str]]:
    """Avalia P1→P5 em ordem. Retorna (urgencia, prioridade, justificativas).

    P5 é PLANEJADO e exige confirmação humana — só atribuímos quando nenhuma
    outra regra casou e há contorno conhecido (erro conhecido em estado estável).
    """
    for urgencia, avaliador in [
        ("CRITICA", _avaliar_p1),
        ("ALTA", _avaliar_p2),
        ("MEDIA", _avaliar_p3),
        ("BAIXA", _avaliar_p4),
    ]:
        resultado = avaliador(cluster)
        if resultado:
            return urgencia, MAPA_URGENCIA_PRIORIDADE[urgencia], resultado

    # Default: P5 (Planejado) — erro conhecido com contorno e sem volume
    if cluster.tem_solucao_contorno and cluster.qtd_incs < 5:
        return "PLANEJADO", "P5", [
            "Erro conhecido com solução de contorno e baixo volume — "
            "aguarda confirmação de Coordenador/PO para P5."
        ]

    # Fallback genérico
    return "BAIXA", "P4", ["Nenhuma regra mais grave acionada — classificado como P4."]


# -----------------------------------------------------------------------------
# Gatilho proativo: >= 5 P3 idênticas → sugerir abertura de PRB
# -----------------------------------------------------------------------------
def _gatilho_proativo_p3(cluster: Cluster) -> Optional[str]:
    """Requisito explícito: detectar 5+ INCs P3 do mesmo assunto e antecipar."""
    qtd_p3 = cluster.qtd_p3_idênticas
    if qtd_p3 >= config.LIMIAR_PRB_PROATIVO_INCS_P3:
        return (
            f"Gatilho proativo: {qtd_p3} INCs P3 idênticas detectadas — "
            f"sugere abertura de PRB antes que escale."
        )
    return None


# -----------------------------------------------------------------------------
# Sugestão de repriorização (requisito da Jéssica)
# -----------------------------------------------------------------------------
def _buscar_prb_correspondente(
    cluster: Cluster, prbs: Sequence[PRBExistente]
) -> Optional[PRBExistente]:
    """Match PRB existente por (produto + CI). Em produção, considerar também
    similaridade de título ou tags de assunto."""
    for prb in prbs:
        mesmo_produto = (prb.produto or "").lower() == (cluster.produto or "").lower()
        mesmo_ci = (
            (prb.servidor or "").lower()
            == (cluster.servidor_principal or "").lower()
        )
        if mesmo_produto and mesmo_ci:
            return prb
    return None


def _sugerir_repriorizacao(
    cluster: Cluster,
    prioridade_sugerida: str,
    prbs: Sequence[PRBExistente],
) -> tuple[Optional[PRBExistente], Optional[str]]:
    """Retorna (prb_alvo, sugestão_texto) se houver PRB que merece upgrade."""
    prb = _buscar_prb_correspondente(cluster, prbs)
    if not prb:
        return None, None

    atual = ORDEM_PRIORIDADE.get(prb.prioridade_atual, 99)
    nova = ORDEM_PRIORIDADE.get(prioridade_sugerida, 99)

    if nova < atual:  # mais grave
        return prb, (
            f"Mudar prioridade de {prb.prioridade_atual} para "
            f"{prioridade_sugerida} (PRB {prb.prb_id})."
        )
    return prb, None


# -----------------------------------------------------------------------------
# Determinação da ação final
# -----------------------------------------------------------------------------
def _determinar_acao(
    cluster: Cluster,
    prioridade_sugerida: str,
    prb_existente: Optional[PRBExistente],
    sugestao_repri: Optional[str],
    gatilho_proativo: Optional[str],
) -> str:
    """Decisão final da ação prescrita."""
    if sugestao_repri and prb_existente:
        return "REPRIORIZAR_PRB"
    if prb_existente:
        return "MONITORAR"  # PRB já existe e prioridade atual ainda condiz
    if gatilho_proativo or prioridade_sugerida in ("P1", "P2"):
        return "ABRIR_PRB"
    if prioridade_sugerida == "P3":
        return "MONITORAR"
    return "NENHUMA"


# -----------------------------------------------------------------------------
# API pública
# -----------------------------------------------------------------------------
def prescrever(
    cluster: Cluster,
    prbs_abertos: Sequence[PRBExistente] = (),
) -> PrescricaoPRB:
    """Recebe um cluster e devolve a PrescricaoPRB completa."""
    urgencia, prioridade, justificativas = _avaliar_cascata(cluster)

    gatilho = _gatilho_proativo_p3(cluster)
    if gatilho:
        justificativas.append(gatilho)
        # Promove para P2 se ainda estava em P3, já que o gatilho é justamente
        # antecipar a escalada.
        if prioridade == "P3":
            prioridade = "P2"
            urgencia = "ALTA"
            justificativas.append("Prioridade elevada para P2 pelo gatilho proativo.")

    prb_match, sugestao_repri = _sugerir_repriorizacao(
        cluster, prioridade, prbs_abertos
    )
    if sugestao_repri:
        justificativas.append(sugestao_repri)

    if cluster.cis_recorrentes_15d:
        justificativas.append(
            f"CI(s) com recorrência em 15 dias: "
            f"{', '.join(cluster.cis_recorrentes_15d)}."
        )

    if cluster.chamados_relacionados > 0:
        justificativas.append(
            f"{cluster.chamados_relacionados} chamados no último dia para o "
            f"produto {cluster.produto} (impacto real, Locaweb/Kinghost)."
        )

    acao = _determinar_acao(
        cluster, prioridade, prb_match, sugestao_repri, gatilho
    )

    return PrescricaoPRB(
        cluster_id=cluster.cluster_id,
        acao=acao,
        prioridade_sugerida=prioridade,
        urgencia=urgencia,
        justificativa=justificativas,
        prb_existente=prb_match,
        prioridade_atual_prb=prb_match.prioridade_atual if prb_match else None,
        sugestao_repriorizacao=sugestao_repri,
    )


def prescrever_lote(
    clusters: Sequence[Cluster],
    prbs_abertos: Sequence[PRBExistente] = (),
) -> List[PrescricaoPRB]:
    """Aplica `prescrever` a uma lista de clusters."""
    saida: List[PrescricaoPRB] = []
    for cluster in clusters:
        try:
            saida.append(prescrever(cluster, prbs_abertos))
        except Exception as exc:
            log.exception(
                "Falha ao prescrever cluster %s: %s", cluster.cluster_id, exc
            )
    return saida