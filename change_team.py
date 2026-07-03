# =============================================================================
# Motor PRB-INC — change_team.py
# =============================================================================
# Orquestrador do "Painel Change Team" (Phase 1, PNCT-01).
#
# Faz o snapshot dos PRBs da força-tarefa Change Team a cada execução do
# ValidadorEntrega (cadência 6h, D-02). Lê a lista master de
# `lwsa.motor_change_team`, busca os PRBs no SNow sem janela temporal (D-03),
# separa abertos (D-05) vs resolvidos (D-06), reaproveita
# `validador_entrega._avaliar_prb` (Pattern 3 do RESEARCH, CON-012 LOCKED
# protegido) para os sinais pós-resolução, e produz uma lista de
# `PainelChangeTeamRow` para `notifier_db.persistir_painel_change_team`
# gravar atomicamente (TRUNCATE+INSERT, D-04).
#
# Chamado por `validar_entregas.executar_validacao()` (Plan 01-05) em bloco
# try/except dedicado (Defense in Depth, DEC-010) — qualquer falha aqui NÃO
# regride o veredito principal V3.1.
#
# Decisões de design referenciadas:
#   D-01: lista master em lwsa.motor_change_team (soft delete via ativo)
#   D-03: query separada SEM janela temporal
#   D-04: TRUNCATE+INSERT atômico (em notifier_db.py, não aqui)
#   D-05: colunas para PRBs abertos
#   D-06: colunas para PRBs resolvidos (reusa _avaliar_prb)
# =============================================================================
from __future__ import annotations

import logging
from typing import List, Optional, Sequence

import config
import time_utils
from extractor import FonteChamados, FonteIncidentes
from models import PainelChangeTeamRow, PRBExistente
from validador_entrega import _avaliar_prb

log = logging.getLogger(__name__)


def _ler_lista_change_team_ativa() -> List[str]:
    """Lê a lista master da tabela lwsa.motor_change_team filtrando ativos.

    Retorna List[str] com os prb_id ativos (ordem por numero ASC para
    determinismo). Defensivo: qualquer falha (banco off, tabela ausente,
    permissão negada) é logada e a função devolve [] — o caller trata lista
    vazia como "pular snapshot Change Team" sem afetar fluxo principal.

    Lazy import de `db.conectar` para não acoplar este módulo ao banco em
    tempo de import (padrão notifier_db.py:318).
    """
    try:
        from db import conectar
        # NOTA: a coluna na tabela master se chama `numero` (PRB number no
        # SNow), NÃO `prb_id`. Confira a DDL em sql/motor_tables.sql §7.
        sql = (
            f"SELECT numero FROM {config.SCHEMA_BANCO}."
            f"{config.TABELA_CHANGE_TEAM} WHERE ativo = true ORDER BY numero"
        )
        with conectar() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                return [row[0] for row in cur.fetchall()]
    except Exception as exc:
        log.warning("Falha ao ler lista Change Team master: %s", exc)
        return []


def _eh_resolvido(prb: PRBExistente) -> bool:
    """PRB é considerado resolvido se status em STATUS_PRB_ENCERRADOS E
    tem produto + servidor (Pitfall 3 do RESEARCH — PRB sem CI vira aberto
    para evitar match espúrio em _avaliar_prb).
    """
    return (
        prb.status in config.STATUS_PRB_ENCERRADOS
        and bool(prb.produto)
        and bool(prb.servidor)
    )


def _row_para_painel_aberto(
    prb: PRBExistente, snapshot_em
) -> PainelChangeTeamRow:
    """Mapeia PRBExistente → PainelChangeTeamRow (D-05). Sem sinais D-06."""
    # Pitfall 6: aberto_em pode ser None — dias_em_aberto fica None nesse caso.
    dias_em_aberto: Optional[int] = (
        (snapshot_em - prb.aberto_em).days if prb.aberto_em else None
    )
    return PainelChangeTeamRow(
        prb_id=prb.prb_id,
        descricao_curta=prb.descricao_curta,
        produto=prb.produto,
        servidor=prb.servidor,
        status_snow=prb.status,
        prioridade_atual=prb.prioridade_atual,
        grupo_designado=prb.grupo_designado,
        dias_em_aberto=dias_em_aberto,
        ultima_atualizacao=None,  # SNow não expõe campo direto; deixa NULL
        # Campos D-06 ficam com defaults (None/0) para PRB aberto
        snapshot_em=snapshot_em,
    )


def _row_para_painel_resolvido(
    prb: PRBExistente,
    fonte_inc: FonteIncidentes,
    fonte_chamados: Optional[FonteChamados],
    snapshot_em,
) -> PainelChangeTeamRow:
    """Mapeia PRBExistente resolvido + sinais V3.1 → PainelChangeTeamRow (D-06).

    Reusa `validador_entrega._avaliar_prb` (Pattern 3 do RESEARCH) — sem
    duplicação da lógica de veredicto/sinais.
    """
    validacao = _avaliar_prb(prb, fonte_inc, fonte_chamados)
    # Pitfall 6: aberto_em pode ser None — dias_em_aberto até data_resolucao
    dias_em_aberto: Optional[int] = (
        (validacao.data_resolucao - prb.aberto_em).days
        if prb.aberto_em and validacao.data_resolucao
        else None
    )
    return PainelChangeTeamRow(
        prb_id=prb.prb_id,
        descricao_curta=prb.descricao_curta,
        produto=prb.produto,
        servidor=prb.servidor,
        status_snow=prb.status,
        prioridade_atual=prb.prioridade_atual,
        grupo_designado=prb.grupo_designado,
        dias_em_aberto=dias_em_aberto,
        ultima_atualizacao=None,
        # D-06 — derivados de _avaliar_prb
        veredicto=validacao.veredicto,
        data_resolucao=validacao.data_resolucao,
        dias_pos_resolucao=validacao.dias_pos_resolucao,
        qtd_incs_pos_resolucao=validacao.qtd_incs_pos_resolucao,
        qtd_incs_pre_resolucao=validacao.qtd_incs_pre_resolucao,
        delta_chamados_pct=validacao.delta_chamados_pct,
        qtd_prbs_novos_pos_resolucao=validacao.qtd_prbs_novos_pos_resolucao,
        # Listas para click-through no chart (req. coordenação 2026-06-15).
        # incs_reincidentes vem como List[Incidente] — extraímos só o inc_id.
        incs_reincidentes=[
            inc.inc_id for inc in validacao.incs_reincidentes if inc.inc_id
        ],
        prbs_novos=list(validacao.prbs_novos),
        snapshot_em=snapshot_em,
    )


def gerar_painel_change_team(
    fonte_inc: FonteIncidentes,
    fonte_chamados: Optional[FonteChamados] = None,
) -> List[PainelChangeTeamRow]:
    """Compõe o snapshot do Painel Change Team.

    Fluxo:
      1. Lê lista master (lwsa.motor_change_team WHERE ativo=true).
      2. Early return se lista vazia.
      3. Busca PRBs no SNow via `fonte_inc.listar_prbs_por_numero` (D-03).
      4. Detecta inconsistência master ↔ SNow (Pitfall 5 RESEARCH).
      5. Para cada PRB: monta row D-05 (aberto) ou D-06 (resolvido — reusa
         `_avaliar_prb` para CON-012 compliance).
      6. Retorna List[PainelChangeTeamRow].

    Nunca levanta exception — caller (entry-point) espera List sempre.
    `fonte_chamados=None` é aceito: `_avaliar_prb` ainda funciona, com
    delta_chamados_pct zerado.
    """
    numeros_ativos = _ler_lista_change_team_ativa()
    if not numeros_ativos:
        log.info("Lista Change Team vazia — pulando snapshot.")
        return []

    snapshot_em = time_utils.agora_utc()
    prbs = fonte_inc.listar_prbs_por_numero(numeros_ativos)

    # Pitfall 5: detectar PRBs na master mas ausentes do SNow.
    encontrados = {p.prb_id for p in prbs}
    faltantes = set(numeros_ativos) - encontrados
    if faltantes:
        log.warning(
            "PRBs Change Team na master mas nao no SNow: %s", sorted(faltantes)
        )

    rows: List[PainelChangeTeamRow] = []
    for prb in prbs:
        try:
            if _eh_resolvido(prb):
                rows.append(
                    _row_para_painel_resolvido(
                        prb, fonte_inc, fonte_chamados, snapshot_em
                    )
                )
            else:
                rows.append(_row_para_painel_aberto(prb, snapshot_em))
        except Exception as exc:
            # Pitfall — falha numa row não derruba o snapshot inteiro.
            log.exception(
                "Falha ao compor row Change Team para PRB %s: %s",
                prb.prb_id,
                exc,
            )

    log.info(
        "Painel Change Team composto: %d rows (master=%d, encontrados=%d).",
        len(rows),
        len(numeros_ativos),
        len(encontrados),
    )
    return rows
