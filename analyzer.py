# =============================================================================
# Motor Prescritivo PRB — Analyzer (clusterização semântica + scores)
# =============================================================================
# Recebe uma lista de Incidentes e devolve uma lista de Clusters com:
#   - Agrupamento semântico via TF-IDF (1-2 grams) + DBSCAN sobre distância
#     de cosseno. Sklearn é a dependência mais leve que entrega NLP utilizável
#     para textos curtos e técnicos das INCs.
#   - Score de Criticidade: combinação ponderada de volume, presença de termos
#     de indisponibilidade, ausência de contorno e recorrência por CI.
#   - Score de Ineficiência: derivado da média de atualizações por INC do
#     cluster (proxy para "time patinando no mesmo problema").
#   - Detecção de recorrência por Item de Configuração: mesmo CI gerando INCs
#     repetidas em janela de 15 dias (requisito do Victor).
# =============================================================================
from __future__ import annotations

import logging
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Sequence, Tuple

import config
import time_utils
from models import Cluster, Incidente

log = logging.getLogger(__name__)


# Stop-words PT-BR — descartadas antes do TF-IDF para o vetorizador priorizar
# termos técnicos discriminativos ("kernel", "panic", "checkout").
_STOP_WORDS_PT = {
    "a", "ao", "aos", "as", "ate", "com", "como", "da", "das", "de", "do", "dos",
    "e", "em", "entre", "era", "essa", "esse", "esta", "este", "eu", "foi", "ha",
    "isso", "isto", "ja", "la", "mais", "mas", "me", "mesmo", "muito", "na", "nas",
    "nem", "no", "nos", "num", "numa", "o", "os", "ou", "para", "pela", "pelo",
    "por", "quando", "que", "se", "sem", "ser", "seu", "sua", "tambem", "tem",
    "ter", "um", "uma", "voce", "voces", "ja", "nao", "sim",
}


# -----------------------------------------------------------------------------
# Pré-processamento
# -----------------------------------------------------------------------------
def _normalizar(texto: str) -> str:
    """Lower-case, remove acentos e pontuação não-alfanumérica."""
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    sem_acento = sem_acento.lower()
    sem_acento = re.sub(r"[^a-z0-9\s]", " ", sem_acento)
    sem_acento = re.sub(r"\s+", " ", sem_acento).strip()
    return sem_acento


def _preparar_textos(incs: Sequence[Incidente]) -> List[str]:
    return [
        _normalizar(f"{i.descricao_curta} {i.descricao}")
        for i in incs
    ]


# -----------------------------------------------------------------------------
# Clusterização
# -----------------------------------------------------------------------------
def _clusterizar_sklearn(textos: List[str]) -> List[int]:
    """Retorna labels (mesmo tamanho de textos). -1 = ruído (singleton)."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.cluster import DBSCAN

    vectorizer = TfidfVectorizer(
        max_features=config.TFIDF_MAX_FEATURES,
        ngram_range=config.TFIDF_NGRAM_RANGE,
        stop_words=list(_STOP_WORDS_PT),
        min_df=1,
    )
    matriz = vectorizer.fit_transform(textos)

    # Distância de cosseno: 1 - similaridade. DBSCAN aceita matriz pré-computada.
    dbscan = DBSCAN(
        eps=config.DBSCAN_EPS,
        min_samples=config.DBSCAN_MIN_SAMPLES,
        metric="cosine",
    )
    labels = dbscan.fit_predict(matriz)
    return labels.tolist()


def _clusterizar_heuristico(textos: List[str]) -> List[int]:
    """Fallback se sklearn indisponível: agrupa por sobreposição de tokens."""
    log.warning("sklearn indisponível — usando clusterização heurística de fallback.")
    tokens_por_texto = [set(t.split()) - _STOP_WORDS_PT for t in textos]
    labels = [-1] * len(textos)
    cluster_atual = 0
    for i, tokens_i in enumerate(tokens_por_texto):
        if labels[i] != -1:
            continue
        labels[i] = cluster_atual
        for j in range(i + 1, len(textos)):
            if labels[j] != -1:
                continue
            tokens_j = tokens_por_texto[j]
            if not tokens_i or not tokens_j:
                continue
            jaccard = len(tokens_i & tokens_j) / len(tokens_i | tokens_j)
            if jaccard >= 0.45:
                labels[j] = cluster_atual
        cluster_atual += 1
    return labels


def _clusterizar(textos: List[str]) -> List[int]:
    try:
        return _clusterizar_sklearn(textos)
    except ImportError:
        return _clusterizar_heuristico(textos)
    except Exception as exc:
        log.error("Falha na clusterização sklearn: %s. Caindo para heurística.", exc)
        return _clusterizar_heuristico(textos)


# -----------------------------------------------------------------------------
# Pós-processamento: fusão de singletons por (produto, servidor)
# -----------------------------------------------------------------------------
def _fundir_singletons_por_ci(
    incidentes: Sequence[Incidente], labels: List[int]
) -> List[int]:
    """Funde singletons (label == -1) que compartilham (produto, servidor).

    Por que: o TF-IDF agrupa por similaridade textual, mas duas INCs do mesmo
    servidor + produto com descrições muito diferentes (ex.: "kernel panic" e
    "disco cheio" no mesmo `vps-prod-01`) são operacionalmente o mesmo "caso"
    para o coordenador. Esse fallback captura recorrência por CI que o texto
    sozinho não vê.

    Critério estrito: só funde quando produto E servidor são truthy E iguais.
    Singletons sem CI completo permanecem como singleton (evita falso match
    via campos vazios).
    """
    if not labels:
        return labels

    proximo_label = max(labels) + 1 if any(l >= 0 for l in labels) else 0
    indices_por_chave: Dict[Tuple[str, str], List[int]] = defaultdict(list)
    for idx, label in enumerate(labels):
        if label != -1:
            continue
        inc = incidentes[idx]
        produto = (inc.produto or "").strip()
        servidor = (inc.servidor or "").strip()
        if not produto or not servidor:
            continue
        indices_por_chave[(produto, servidor)].append(idx)

    novos_labels = list(labels)
    fundidos = 0
    for chave, indices in indices_por_chave.items():
        if len(indices) < 2:
            continue
        for idx in indices:
            novos_labels[idx] = proximo_label
        fundidos += len(indices)
        proximo_label += 1

    if fundidos:
        log.info(
            "Fusão por (produto, servidor): %d singletons agrupados em %d novos clusters.",
            fundidos,
            proximo_label - (max(labels) + 1 if any(l >= 0 for l in labels) else 0),
        )
    return novos_labels


# -----------------------------------------------------------------------------
# Métricas do cluster
# -----------------------------------------------------------------------------
def _termos_dominantes(incs: Sequence[Incidente], top_n: int = 5) -> List[str]:
    """Termos mais frequentes (descontando stop-words)."""
    counter: Counter[str] = Counter()
    for inc in incs:
        for tok in _normalizar(f"{inc.descricao_curta} {inc.descricao}").split():
            if tok in _STOP_WORDS_PT or len(tok) < 3 or tok.isdigit():
                continue
            counter[tok] += 1
    return [t for t, _ in counter.most_common(top_n)]


def _moda_string(valores: Sequence[str]) -> str:
    if not valores:
        return ""
    return Counter(valores).most_common(1)[0][0]


def _detectar_termo(texto: str, termos: Sequence[str]) -> bool:
    return any(t in texto for t in termos)


def _score_criticidade(
    cluster_incs: List[Incidente],
    total_incs: int,
    cis_recorrentes: List[str],
) -> float:
    """Combinação ponderada — todos os componentes em [0, 1]."""
    if total_incs == 0:
        return 0.0

    qtd = len(cluster_incs)
    componente_volume = min(qtd / max(total_incs, 1), 1.0)

    texto_concat = " ".join(i.texto_busca for i in cluster_incs)
    componente_indisp = 1.0 if _detectar_termo(
        texto_concat, config.TERMOS_INDISPONIBILIDADE_TOTAL
    ) else 0.0

    qtd_sem_contorno = sum(1 for i in cluster_incs if not i.tem_solucao_contorno)
    componente_sem_contorno = qtd_sem_contorno / qtd

    componente_recorrencia = (
        1.0 if any(i.servidor in cis_recorrentes for i in cluster_incs)
        else 0.0
    )

    score = (
        config.PESO_VOLUME_CRITICIDADE * componente_volume
        + config.PESO_INDISPONIBILIDADE * componente_indisp
        + config.PESO_SEM_CONTORNO * componente_sem_contorno
        + config.PESO_RECORRENCIA_CI * componente_recorrencia
    )
    return round(min(score, 1.0), 3)


def _score_ineficiencia(cluster_incs: List[Incidente]) -> float:
    """Composição ponderada de dois sinais:
      - Volume: média de updates por INC (acima de LIMIAR_UPDATES_INEFICIENTE → 1.0).
      - Velocidade: média de updates/hora (acima de LIMIAR_UPDATES_POR_HORA → 1.0).

    Por que dois componentes: 10 updates em 1h indica patinação intensa;
    10 updates em 7 dias indica caso arrastando lentamente. Mesmo total, sinais
    operacionais diferentes — coordenador prioriza diferente.
    """
    if not cluster_incs:
        return 0.0

    # Componente 1: volume (média de updates por INC)
    media_updates = sum(i.qtd_atualizacoes for i in cluster_incs) / len(cluster_incs)
    componente_volume = min(media_updates / config.LIMIAR_UPDATES_INEFICIENTE, 1.0)

    # Componente 2: velocidade (updates por hora, em média)
    # Duração de cada INC com clamp mínimo para evitar divisão por zero.
    horas_por_inc = [
        max(
            (i.atualizacao - i.abertura).total_seconds() / 3600,
            config.MIN_HORAS_INC_INEFICIENCIA,
        )
        for i in cluster_incs
    ]
    media_horas = sum(horas_por_inc) / len(horas_por_inc)
    updates_por_hora = media_updates / media_horas
    componente_velocidade = min(updates_por_hora / config.LIMIAR_UPDATES_POR_HORA, 1.0)

    score = (
        config.PESO_INEFICIENCIA_VOLUME * componente_volume
        + config.PESO_INEFICIENCIA_VELOCIDADE * componente_velocidade
    )
    return round(min(score, 1.0), 3)


# -----------------------------------------------------------------------------
# Recorrência por CI (requisito do Victor)
# -----------------------------------------------------------------------------
def detectar_cis_recorrentes(
    incidentes: Sequence[Incidente],
    janela_dias: int = config.JANELA_RECORRENCIA_CI_DIAS,
    limiar_ocorrencias: int = 2,
) -> Dict[str, int]:
    """Mapeia CI → contagem de INCs nos últimos `janela_dias`.

    Útil quando analistas diferentes trataram pontualmente em plantões e a
    recorrência sistêmica passou despercebida.
    """
    corte = time_utils.agora_utc() - timedelta(days=janela_dias)
    contagem: Counter[str] = Counter()
    for inc in incidentes:
        if inc.abertura >= corte and inc.servidor:
            contagem[inc.servidor] += 1
    return {ci: n for ci, n in contagem.items() if n >= limiar_ocorrencias}


# -----------------------------------------------------------------------------
# Cruzamento com Dynamics (impacto real)
# -----------------------------------------------------------------------------
def _contar_chamados_por_produto(
    chamados: Sequence,
) -> Dict[str, int]:
    """Conta chamados por produto (assumindo 1 row = 1 chamado de cliente).

    Para Kinghost a tabela já separa interações cliente vs. analista nativamente;
    para Locaweb (dynamics.chamados) cada row já representa um caso aberto pelo
    cliente. Por isso não filtramos por `origem` aqui — o filtro pode ser
    reintroduzido se confirmarmos semântica diferente.
    """
    contagem: Counter[str] = Counter()
    for chamado in chamados:
        contagem[chamado.produto] += 1
    return dict(contagem)


# -----------------------------------------------------------------------------
# Pipeline público
# -----------------------------------------------------------------------------
def analisar(
    incidentes: List[Incidente],
    chamados: Sequence = (),
) -> List[Cluster]:
    """Executa o pipeline completo de análise.

    Passos:
      1. Normaliza texto, clusteriza com TF-IDF + DBSCAN.
      2. Detecta CIs recorrentes em 15 dias.
      3. Conta chamados Dynamics por produto para cruzar impacto real.
      4. Constrói objetos Cluster com scores prontos.

    Singletons (label == -1 do DBSCAN) viram clusters de tamanho 1 — relevantes
    para a Saúde do Cliente mesmo que não acionem regras de volume.
    """
    if len(incidentes) < config.MIN_INCS_PARA_CLUSTERIZAR:
        log.info("Apenas %d INCs — pulando clusterização.", len(incidentes))
        return []

    textos = _preparar_textos(incidentes)
    labels = _clusterizar(textos)
    labels = _fundir_singletons_por_ci(incidentes, labels)

    # Agrupar incidentes por label (-1 = singleton: cada um vira seu próprio cluster)
    grupos: Dict[str, List[Incidente]] = defaultdict(list)
    for inc, label in zip(incidentes, labels):
        chave = f"singleton-{inc.inc_id}" if label == -1 else f"cluster-{label}"
        grupos[chave].append(inc)

    cis_recorrentes_map = detectar_cis_recorrentes(incidentes)
    cis_recorrentes = list(cis_recorrentes_map.keys())
    log.info("CIs recorrentes detectados (>=2 INCs em 15d): %s", cis_recorrentes_map)

    chamados_por_produto = _contar_chamados_por_produto(chamados)
    total_incs = len(incidentes)

    clusters: List[Cluster] = []
    for chave, incs_grupo in grupos.items():
        servidor_principal = _moda_string([i.servidor for i in incs_grupo])
        produto = _moda_string([i.produto for i in incs_grupo])
        termos = _termos_dominantes(incs_grupo)
        nome = " ".join(termos[:3]) or "indefinido"

        qtd_sem_contorno = sum(1 for i in incs_grupo if not i.tem_solucao_contorno)
        tem_contorno_majoritario = qtd_sem_contorno < (len(incs_grupo) / 2)

        tempos = [
            i.tempo_solucao_contorno_min for i in incs_grupo
            if i.tem_solucao_contorno and i.tempo_solucao_contorno_min > 0
        ]
        tempo_medio = int(sum(tempos) / len(tempos)) if tempos else 0

        cis_recorrentes_no_cluster = [
            ci for ci in {i.servidor for i in incs_grupo}
            if ci in cis_recorrentes_map
        ]

        cluster = Cluster(
            cluster_id=chave,
            nome=nome,
            incidentes=incs_grupo,
            servidor_principal=servidor_principal,
            produto=produto,
            qtd_incs=len(incs_grupo),
            score_criticidade=_score_criticidade(
                incs_grupo, total_incs, cis_recorrentes
            ),
            score_ineficiencia=_score_ineficiencia(incs_grupo),
            tem_solucao_contorno=tem_contorno_majoritario,
            tempo_contorno_min_medio=tempo_medio,
            chamados_relacionados=chamados_por_produto.get(produto, 0),
            cis_recorrentes_15d=cis_recorrentes_no_cluster,
            termos_dominantes=termos,
        )
        clusters.append(cluster)

    # Ordena por criticidade decrescente para o consumidor já receber priorizado
    clusters.sort(key=lambda c: (c.score_criticidade, c.qtd_incs), reverse=True)
    log.info("Análise concluída: %d clusters formados.", len(clusters))
    return clusters