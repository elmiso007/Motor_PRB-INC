# =============================================================================
# Motor Prescritivo PRB — Notifier (Slack + Dashboard JSON)
# =============================================================================
# Duas saídas:
#   1) Slack: alerta textual detalhado a cada 15 min, APENAS para cenários
#      críticos (urgência CRITICA). Inclui volume, severidade e ação sugerida.
#   2) Dashboard: estrutura JSON limpa (e DataFrame opcional) consumida pelo
#      front-end dos coordenadores — eles preferem "bater o olho em gráficos
#      e dados tabulados" em vez de ler alertas textuais.
# =============================================================================
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List

import config
from models import (
    SaudeCliente,
    Cluster,
    ExecucaoMotor,
    Incidente,
    PrescricaoPRB,
    ValidacaoEntrega,
)

log = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Slack — formatação do payload textual
# -----------------------------------------------------------------------------
_EMOJI_URGENCIA = {
    "CRITICA": ":rotating_light:",
    "ALTA": ":warning:",
    "MEDIA": ":mag:",
    "BAIXA": ":memo:",
    "PLANEJADO": ":calendar:",
}

# Emoji adicional por tipo de ação — combinado com emoji de urgência permite
# distinguir visualmente "crítico que precisa ABRIR PRB" de "crítico que precisa
# REPRIORIZAR PRB existente". Coordenador identifica o tipo de ação em 100ms.
_EMOJI_ACAO = {
    "ABRIR_PRB": ":sos:",          # 🆘 — novo problema, abrir PRB
    "REPRIORIZAR_PRB": ":wrench:", # 🔧 — PRB existe, ajustar prioridade
    "MONITORAR": ":eyes:",         # 👀 — observar sem ação ativa
    "NENHUMA": ":memo:",           # 📝 — apenas registrar
}


def _formatar_bullet_lista(itens: List[str], indent: str = "    ") -> str:
    return "\n".join(f"{indent}• {i}" for i in itens)


def formatar_alerta_slack(prescricao: PrescricaoPRB, cluster: Cluster) -> str:
    """Texto pronto para `chat.postMessage` (compatível com Block Kit simples)."""
    emoji_urg = _EMOJI_URGENCIA.get(prescricao.urgencia, "")
    emoji_acao = _EMOJI_ACAO.get(prescricao.acao, "")
    cabecalho = (
        f"{emoji_urg}{emoji_acao} *Motor Prescritivo PRB — Alerta {prescricao.urgencia}*\n"
        f"_Ação sugerida: *{prescricao.acao}* | Prioridade: *{prescricao.prioridade_sugerida}*_"
    )

    detalhes = [
        f"*Cluster:* {cluster.nome}",
        f"*Produto:* {cluster.produto or 'n/d'}",
        f"*Servidor/CI:* {cluster.servidor_principal or 'n/d'}",
        f"*INCs no cluster:* {cluster.qtd_incs}",
        f"*Score Criticidade:* {cluster.score_criticidade:.2f} "
        f"| *Ineficiência:* {cluster.score_ineficiencia:.2f}",
    ]
    if cluster.chamados_relacionados:
        detalhes.append(
            f"*Chamados (24h, produto):* {cluster.chamados_relacionados}"
        )
    if cluster.cis_recorrentes_15d:
        detalhes.append(
            f"*CIs recorrentes (15d):* {', '.join(cluster.cis_recorrentes_15d)}"
        )
    if prescricao.prb_existente:
        detalhes.append(
            f"*PRB existente:* {prescricao.prb_existente.prb_id} "
            f"(atual: {prescricao.prioridade_atual_prb})"
        )
    if prescricao.sugestao_repriorizacao:
        detalhes.append(f"*Sugestão:* {prescricao.sugestao_repriorizacao}")

    justificativas = _formatar_bullet_lista(prescricao.justificativa)

    return (
        f"{cabecalho}\n\n"
        + "\n".join(detalhes)
        + "\n\n*Justificativas:*\n"
        + justificativas
    )


def formatar_alerta_saude_cliente(saude: SaudeCliente) -> str:
    """Slack textual para clientes com recorrência alta."""
    return (
        f":thermometer: *Saúde do Cliente — Recorrência Alta*\n"
        f"*Cliente:* `{saude.cliente_login}`\n"
        f"*INCs em 6 meses:* {saude.qtd_incs_periodo}\n"
        f"*Chamados em 6 meses:* {saude.qtd_chamados_periodo}\n"
        f"*Severidade média:* {saude.severidade_media:.2f}\n"
        f"*Total de eventos consolidados:* {len(saude.linha_do_tempo)}\n"
        f"_Use o dashboard para ver a linha do tempo completa._"
    )


def formatar_alerta_reincidencia(v: ValidacaoEntrega) -> str:
    """Slack textual para Change Team quando reincidência é detectada.

    Inclui contexto enriquecido: tamanho do problema pré-resolução (INCs +
    clientes + categorias) e delta de chamados pré vs pós. Setas indicam
    queda ou subida significativa (limiares em config).
    """
    incs_resumo = ", ".join(
        f"{i.inc_id} ({i.prioridade_atual})" for i in v.incs_reincidentes[:5]
    )
    if len(v.incs_reincidentes) > 5:
        incs_resumo += f" (+{len(v.incs_reincidentes) - 5})"

    # Volumetria pré-resolução (só inclui se houver dado).
    linha_pre = ""
    if v.qtd_incs_pre_resolucao > 0:
        linha_pre = (
            f"*Pré-resolução ({config.JANELA_VOLUMETRIA_PRE_DIAS}d):* "
            f"{v.qtd_incs_pre_resolucao} INCs · "
            f"{v.clientes_unicos_pre} clientes · {v.categorias_pre} categorias\n"
        )

    # Delta de chamados (só inclui se houver dado pré ou pós).
    linha_delta = ""
    if v.chamados_pre > 0 or v.chamados_pos > 0:
        seta = ""
        if v.delta_chamados_pct <= config.LIMIAR_REDUCAO_CHAMADOS_PCT:
            seta = " :arrow_down:"  # queda significativa
        elif v.delta_chamados_pct >= config.LIMIAR_AUMENTO_CHAMADOS_PCT:
            seta = " :arrow_up:"  # aumento significativo
        linha_delta = (
            f"*Δ Chamados vinculados ({config.JANELA_CHAMADOS_DELTA_DIAS}d):* "
            f"{v.chamados_pre} → {v.chamados_pos} "
            f"({v.delta_chamados_pct * 100:+.1f}%){seta}\n"
        )

    linha_grupo = (
        f"*Grupo designado:* {v.grupo_designado}\n" if v.grupo_designado else ""
    )

    # PRBs novos abertos no mesmo CI após a resolução — sinal de problema que
    # voltou em outra forma. Só inclui se houver pelo menos 1.
    linha_prbs_novos = ""
    if v.qtd_prbs_novos_pos_resolucao > 0:
        prbs_resumo = ", ".join(v.prbs_novos[:3])
        if len(v.prbs_novos) > 3:
            prbs_resumo += f" (+{len(v.prbs_novos) - 3})"
        linha_prbs_novos = (
            f"*PRBs novos no CI:* {v.qtd_prbs_novos_pos_resolucao} "
            f"({prbs_resumo})\n"
        )

    # Times impactados — top N equipes proprietárias dos chamados vinculados
    # pré-resolução, com % de redução pós. Só inclui se houver pelo menos 1
    # equipe no top do pré (sem chamados pré não há "time impactado" a reportar).
    bloco_equipes = ""
    if v.equipes_impactadas_pre:
        linhas_equipes = []
        for equipe, qtd_pre in v.equipes_impactadas_pre.items():
            qtd_pos = v.equipes_impactadas_pos.get(equipe, 0)
            pct = v.equipes_delta_pct.get(equipe, 0.0)
            if qtd_pos == 0:
                marcador = " :white_check_mark: zerou"
            elif pct <= config.LIMIAR_REDUCAO_CHAMADOS_PCT:
                marcador = " :arrow_down:"
            elif pct >= config.LIMIAR_AUMENTO_CHAMADOS_PCT:
                marcador = " :arrow_up:"
            else:
                marcador = ""
            linhas_equipes.append(
                f"    • {equipe}: {qtd_pre} → {qtd_pos} ({pct * 100:+.1f}%){marcador}"
            )
        bloco_equipes = (
            f"*Times impactados (top {len(v.equipes_impactadas_pre)} — "
            f"{config.JANELA_CHAMADOS_DELTA_DIAS}d pré → pós):*\n"
            + "\n".join(linhas_equipes)
            + "\n"
        )

    return (
        f":warning::arrows_counterclockwise: *PRB {v.prb_id} — REINCIDÊNCIA DETECTADA*\n"
        f"*Descrição:* {v.descricao_curta}\n"
        f"*Produto:* {v.produto or 'n/d'}\n"
        f"*Servidor/CI:* {v.servidor or 'n/d'}\n"
        f"{linha_grupo}"
        f"*Resolvido em:* {v.data_resolucao.strftime('%Y-%m-%d')} "
        f"({v.dias_pos_resolucao}d atrás)\n"
        f"{linha_pre}"
        f"*Pós-resolução:* {v.qtd_incs_pos_resolucao} novas INCs no mesmo (produto, servidor)\n"
        f"{linha_delta}"
        f"{linha_prbs_novos}"
        f"{bloco_equipes}"
        f"*INCs:* {incs_resumo}\n"
        f"_Change Team: validar se o fix entregue cobre os novos casos._"
    )


# -----------------------------------------------------------------------------
# Slack — envio (com fallback para log se webhook não configurado)
# -----------------------------------------------------------------------------
def enviar_slack(texto: str, slack_cfg: config.SlackConfig | None = None) -> bool:
    """Envia alerta para o Slack. Retorna True se TODOS os destinos receberam OK.

    Preferência:
      1. Bot Token API (slack_sdk.WebClient.chat_postMessage) — igual locapredict.
         Para cada canal C..., posta direto. Para U..., abre DM antes.
      2. Webhook legado (POST direto em hooks.slack.com) — fallback.
    """
    cfg = slack_cfg or config.SlackConfig()
    if not cfg.configurado:
        log.info("[Slack desabilitado/sem token nem webhook] %s", texto[:200])
        return False

    if cfg.usa_bot_token:
        return _enviar_via_bot_token(texto, cfg)
    return _enviar_via_webhook(texto, cfg)


def _enviar_via_bot_token(texto: str, cfg: config.SlackConfig) -> bool:
    """Envia via slack_sdk.WebClient. True se TODOS os destinos receberam OK."""
    try:
        from slack_sdk import WebClient
        from slack_sdk.errors import SlackApiError
    except ImportError:
        log.error("slack_sdk não instalado — `pip install slack_sdk` ou caia no webhook.")
        return False

    cliente = WebClient(token=cfg.bot_token)
    todos_ok = True
    for destino in cfg.channels:
        try:
            if destino.startswith("U"):
                ch = cliente.conversations_open(users=destino)["channel"]["id"]
                cliente.chat_postMessage(channel=ch, text=texto)
            elif destino.startswith("C") or destino.startswith("#"):
                cliente.chat_postMessage(channel=destino, text=texto)
            else:
                log.warning("Destino Slack ignorado (use C... ou U... ou #canal): %r", destino)
                todos_ok = False
        except SlackApiError as exc:
            codigo = exc.response.get("error", exc) if exc.response is not None else exc
            log.error("Slack API erro em %s: %s", destino, codigo)
            todos_ok = False
        except Exception as exc:
            log.exception("Falha inesperada ao enviar Slack para %s: %s", destino, exc)
            todos_ok = False
    return todos_ok


def _enviar_via_webhook(texto: str, cfg: config.SlackConfig) -> bool:
    """Envio legado via Incoming Webhook (POST direto)."""
    try:
        import requests
        resp = requests.post(
            cfg.webhook_url,
            json={"text": texto, "channel": cfg.canal_criticos},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except ImportError:
        log.error("Biblioteca `requests` não instalada — Slack indisponível.")
    except Exception as exc:
        log.exception("Falha ao enviar Slack via webhook: %s", exc)
    return False


# Delay entre envios consecutivos ao Slack para respeitar rate limit do webhook
# (~1 req/s). Aplicado APENAS quando há webhook configurado — em modo
# desenvolvimento/mock (sem webhook), sleep seria overhead inútil.
# Em produção: 5 alertas adicionam 5s ao ciclo de 15 min — irrelevante.
# Evita 429 Too Many Requests em pico de alertas críticos.
_DELAY_ENTRE_ALERTAS_SEG = 1


def disparar_alertas_criticos(
    execucao: ExecucaoMotor,
    slack_cfg: config.SlackConfig | None = None,
) -> int:
    """Envia Slack para todas as prescrições CRITICAS e clientes com recorrência alta.
    Retorna a quantidade efetivamente enviada."""
    cfg = slack_cfg or config.SlackConfig()
    enviados = 0
    # Só aplicar delay se ambiente configurado — evita overhead em dev/mock.
    aplicar_delay = cfg.configurado

    clusters_por_id = {c.cluster_id: c for c in execucao.clusters}

    for presc in execucao.alertas_criticos:
        cluster = clusters_por_id.get(presc.cluster_id)
        if not cluster:
            continue
        texto = formatar_alerta_slack(presc, cluster)
        if enviar_slack(texto, cfg):
            enviados += 1
        if aplicar_delay:
            time.sleep(_DELAY_ENTRE_ALERTAS_SEG)

    for saude in execucao.saude_clientes:
        if saude.alerta_recorrencia_alta:
            texto = formatar_alerta_saude_cliente(saude)
            if enviar_slack(texto, cfg):
                enviados += 1
            if aplicar_delay:
                time.sleep(_DELAY_ENTRE_ALERTAS_SEG)

    for validacao in execucao.reincidencias_detectadas:
        texto = formatar_alerta_reincidencia(validacao)
        if enviar_slack(texto, cfg):
            enviados += 1
        if aplicar_delay:
            time.sleep(_DELAY_ENTRE_ALERTAS_SEG)

    log.info("Alertas Slack enviados: %d.", enviados)
    return enviados


# -----------------------------------------------------------------------------
# Dashboard — estrutura JSON (limpa, tabulável, agnóstica de front-end)
# -----------------------------------------------------------------------------
def _serialize_datetime(obj: Any) -> Any:
    """JSON encoder para datetime → ISO8601."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Não serializável: {type(obj)}")


def _cluster_para_dict(cluster: Cluster) -> Dict[str, Any]:
    """Remove o objeto pesado `incidentes` da serialização principal — manda
    só metadados resumidos. INCs completas vão para tabela separada."""
    return {
        "cluster_id": cluster.cluster_id,
        "nome": cluster.nome,
        "produto": cluster.produto,
        "servidor_principal": cluster.servidor_principal,
        "qtd_incs": cluster.qtd_incs,
        "score_criticidade": cluster.score_criticidade,
        "score_ineficiencia": cluster.score_ineficiencia,
        "tem_solucao_contorno": cluster.tem_solucao_contorno,
        "tempo_contorno_min_medio": cluster.tempo_contorno_min_medio,
        "chamados_relacionados": cluster.chamados_relacionados,
        "cis_recorrentes_15d": cluster.cis_recorrentes_15d,
        "termos_dominantes": cluster.termos_dominantes,
        "inc_ids": [i.inc_id for i in cluster.incidentes],
    }


def _prescricao_para_dict(p: PrescricaoPRB) -> Dict[str, Any]:
    return {
        "cluster_id": p.cluster_id,
        "acao": p.acao,
        "urgencia": p.urgencia,
        "prioridade_sugerida": p.prioridade_sugerida,
        "prb_existente": p.prb_existente.prb_id if p.prb_existente else None,
        "prioridade_atual_prb": p.prioridade_atual_prb,
        "sugestao_repriorizacao": p.sugestao_repriorizacao,
        "justificativa": p.justificativa,
    }


def _incidente_para_dict(i: Incidente) -> Dict[str, Any]:
    return {
        "inc_id": i.inc_id,
        "descricao_curta": i.descricao_curta,
        "produto": i.produto,
        "servidor": i.servidor,
        "login_cliente": i.login_cliente,
        "organizacao": i.organizacao,
        "prioridade_atual": i.prioridade_atual,
        "status": i.status,
        "categoria": i.categoria,
        "subcategoria": i.subcategoria,
        "grupo_designado": i.grupo_designado,
        "abertura": i.abertura.isoformat(),
        "atualizacao": i.atualizacao.isoformat(),
        "qtd_atualizacoes": i.qtd_atualizacoes,
        "tem_solucao_contorno": i.tem_solucao_contorno,
        "tempo_solucao_contorno_min": i.tempo_solucao_contorno_min,
    }


def _saude_cliente_para_dict(c: SaudeCliente) -> Dict[str, Any]:
    return {
        "cliente_login": c.cliente_login,
        "qtd_incs_periodo": c.qtd_incs_periodo,
        "qtd_chamados_periodo": c.qtd_chamados_periodo,
        "severidade_media": c.severidade_media,
        "alerta_recorrencia_alta": c.alerta_recorrencia_alta,
        "linha_do_tempo": c.linha_do_tempo,
    }


def _validacao_entrega_para_dict(v: ValidacaoEntrega) -> Dict[str, Any]:
    return {
        "prb_id": v.prb_id,
        "descricao_curta": v.descricao_curta,
        "produto": v.produto,
        "servidor": v.servidor,
        "status_prb": v.status_prb,
        "data_resolucao": v.data_resolucao.isoformat(),
        "dias_pos_resolucao": v.dias_pos_resolucao,
        "qtd_incs_pos_resolucao": v.qtd_incs_pos_resolucao,
        "veredicto": v.veredicto,
        "incs_reincidentes": [
            {
                "inc_id": i.inc_id,
                "prioridade": i.prioridade_atual,
                "abertura": i.abertura.isoformat(),
                "descricao_curta": i.descricao_curta,
            }
            for i in v.incs_reincidentes
        ],
        "grupo_designado": v.grupo_designado,
        "data_abertura_prb": (
            v.data_abertura_prb.isoformat() if v.data_abertura_prb else None
        ),
        "qtd_incs_pre_resolucao": v.qtd_incs_pre_resolucao,
        "clientes_unicos_pre": v.clientes_unicos_pre,
        "categorias_pre": v.categorias_pre,
        "chamados_pre": v.chamados_pre,
        "chamados_pos": v.chamados_pos,
        "delta_chamados_pct": v.delta_chamados_pct,
        "qtd_prbs_novos_pos_resolucao": v.qtd_prbs_novos_pos_resolucao,
        "prbs_novos": v.prbs_novos,
        "equipes_impactadas_pre": v.equipes_impactadas_pre,
        "equipes_impactadas_pos": v.equipes_impactadas_pos,
        "equipes_delta_pct": v.equipes_delta_pct,
    }


def montar_payload_dashboard(execucao: ExecucaoMotor) -> Dict[str, Any]:
    """Estrutura JSON consumida pelo front-end. Pensada para ser facilmente
    transformada em tabelas/cards (cada lista vira uma seção do dashboard)."""
    incidentes_unicos: Dict[str, Incidente] = {}
    for cluster in execucao.clusters:
        for inc in cluster.incidentes:
            incidentes_unicos.setdefault(inc.inc_id, inc)

    return {
        "meta": {
            "timestamp": execucao.timestamp.isoformat(),
            "total_incs_lidas": execucao.total_incs_lidas,
            "total_chamados": execucao.total_chamados,
            "total_clusters": len(execucao.clusters),
            "total_prescricoes": len(execucao.prescricoes),
            "total_saude_clientes": len(execucao.saude_clientes),
            "total_validacoes_entrega": len(execucao.validacoes_entrega),
            "erros": execucao.erros,
        },
        "clusters": [_cluster_para_dict(c) for c in execucao.clusters],
        "prescricoes": [_prescricao_para_dict(p) for p in execucao.prescricoes],
        "saude_clientes": [_saude_cliente_para_dict(c) for c in execucao.saude_clientes],
        "validacoes_entrega": [
            _validacao_entrega_para_dict(v) for v in execucao.validacoes_entrega
        ],
        "incidentes": [_incidente_para_dict(i) for i in incidentes_unicos.values()],
    }


def gravar_payload_dashboard(
    execucao: ExecucaoMotor, caminho: str | None = None
) -> str:
    """Grava o JSON em disco. Retorna o path final."""
    caminho_final = caminho or config.DASHBOARD_OUTPUT_PATH
    os.makedirs(os.path.dirname(caminho_final) or ".", exist_ok=True)
    payload = montar_payload_dashboard(execucao)
    with open(caminho_final, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=_serialize_datetime)
    log.info("Payload do dashboard gravado em %s.", caminho_final)
    return caminho_final


# -----------------------------------------------------------------------------
# DataFrame helper (opcional — pandas é dependência leve para o dashboard)
# -----------------------------------------------------------------------------
def montar_dataframes_dashboard(execucao: ExecucaoMotor):
    """Retorna dict de DataFrames prontos para Streamlit / Plotly Dash.

    Lazy-import do pandas: o pipeline principal não precisa de pandas; só
    consumidores que querem tabular.
    """
    try:
        import pandas as pd
    except ImportError:
        log.warning("pandas não instalado — `montar_dataframes_dashboard` indisponível.")
        return None

    payload = montar_payload_dashboard(execucao)
    return {
        "clusters": pd.DataFrame(payload["clusters"]),
        "prescricoes": pd.DataFrame(payload["prescricoes"]),
        "saude_clientes": pd.DataFrame(payload["saude_clientes"]),
        "validacoes_entrega": pd.DataFrame(payload["validacoes_entrega"]),
        "incidentes": pd.DataFrame(payload["incidentes"]),
    }