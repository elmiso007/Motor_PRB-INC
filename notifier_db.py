# =============================================================================
# Motor Prescritivo PRB — Persistência Postgres (lwsa.motor_*)
# =============================================================================
# Segunda saída do motor (paralela ao JSON do dashboard).
#
# Persiste cada ciclo em 5 tabelas histórico-com-TTL (30 dias por default):
#   - lwsa.motor_execucao (cabeça)
#   - lwsa.motor_cluster (1 por cluster)
#   - lwsa.motor_prescricao (1 por prescrição)
#   - lwsa.motor_saude_cliente (1 por saúde de cliente avaliada)
#   - lwsa.motor_validacao_entrega (1 por PRB validado retrospectivamente)
#
# Transação única por ciclo: ou tudo grava, ou nada grava. Garante consistência
# referencial (FKs ON DELETE CASCADE não veem estado intermediário).
#
# Antes da gravação, executa cleanup TTL — DELETE de execuções antigas. Por que
# antes (e não depois): se cleanup falhar, ainda persistimos o ciclo atual.
#
# DDL deve ter sido executada no banco (sql/motor_tables.sql).
# =============================================================================
from __future__ import annotations

import json
import logging
from typing import Any, Iterable, List, Tuple

import config
import time_utils
from models import (
    Cluster,
    ExecucaoMotor,
    PainelChangeTeamRow,
    PrescricaoPRB,
    SaudeCliente,
    ValidacaoEntrega,
)

log = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Helpers de serialização
# -----------------------------------------------------------------------------
def _jsonb(valor: Any) -> str:
    """Serializa Python value para string JSON compatível com `json` do Postgres.

    psycopg2 aceita string JSON em colunas json/jsonb desde que a string seja
    JSON válido. `default=str` lida com datetime/Decimal de forma defensiva.

    Nota: nome do helper mantido como `_jsonb` para preservar compatibilidade
    semântica caso migremos para jsonb no futuro (Postgres 9.4+).
    """
    return json.dumps(valor, ensure_ascii=False, default=str)


# -----------------------------------------------------------------------------
# Cleanup TTL
# -----------------------------------------------------------------------------
def purgar_execucoes_antigas(dias: int | None = None) -> int:
    """Remove execuções com timestamp > N dias atrás. ON DELETE CASCADE remove
    clusters/prescrições/saúdes vinculados automaticamente.

    Retorna a quantidade de execuções removidas (info — pode ficar em log).
    Falha graciosamente: erro vira warning, motor segue.
    """
    janela_dias = dias if dias is not None else config.JANELA_TTL_BANCO_DIAS
    sql = """
        DELETE FROM lwsa.motor_execucao
        WHERE timestamp_utc < NOW() - %s::interval
        RETURNING id
    """
    try:
        from db import conectar
        with conectar() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (f"{janela_dias} days",))
                qtd = cur.rowcount
                conn.commit()
        if qtd > 0:
            log.info("TTL: %d execuções antigas removidas (> %d dias).", qtd, janela_dias)
        return qtd
    except Exception as exc:
        log.warning("Falha no cleanup TTL — seguindo sem purgar: %s", exc)
        return 0


# -----------------------------------------------------------------------------
# Inserts individuais (uma função por tabela, para legibilidade)
# -----------------------------------------------------------------------------
def _insert_execucao(cur, execucao: ExecucaoMotor, total_clusters: int) -> int:
    """Insere a cabeça e retorna o id gerado (FK para outras tabelas).

    `total_clusters` é passado explicitamente porque pode divergir de
    `len(execucao.clusters)` quando singletons são omitidos da persistência
    (mantém consistência com o que efetivamente entra em motor_cluster).
    """
    sql = """
        INSERT INTO lwsa.motor_execucao (
            timestamp_utc, total_incs_lidas, total_chamados,
            total_clusters, total_prescricoes, total_saude_clientes,
            total_validacoes_entrega,
            erros, duracao_ciclo_ms
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::json, %s)
        RETURNING id
    """
    cur.execute(sql, (
        execucao.timestamp,
        execucao.total_incs_lidas,
        execucao.total_chamados,
        total_clusters,
        len(execucao.prescricoes),
        len(execucao.saude_clientes),
        len(execucao.validacoes_entrega),
        _jsonb(execucao.erros),
        execucao.duracao_ciclo_ms,
    ))
    return cur.fetchone()[0]


def _insert_clusters(cur, execucao_id: int, clusters: Iterable[Cluster]) -> None:
    """Insere N clusters em batch (executemany)."""
    sql = """
        INSERT INTO lwsa.motor_cluster (
            execucao_id, cluster_id, nome, produto, servidor, qtd_incs,
            score_criticidade, score_ineficiencia, tem_solucao_contorno,
            tempo_contorno_min_medio, chamados_relacionados,
            cis_recorrentes_15d, termos_dominantes, inc_ids
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::json, %s::json, %s::json)
    """
    rows = [
        (
            execucao_id,
            c.cluster_id,
            c.nome,
            c.produto or None,
            c.servidor_principal or None,
            c.qtd_incs,
            c.score_criticidade,
            c.score_ineficiencia,
            c.tem_solucao_contorno,
            c.tempo_contorno_min_medio,
            c.chamados_relacionados,
            _jsonb(c.cis_recorrentes_15d),
            _jsonb(c.termos_dominantes),
            _jsonb([i.inc_id for i in c.incidentes]),
        )
        for c in clusters
    ]
    if rows:
        cur.executemany(sql, rows)


def _insert_prescricoes(cur, execucao_id: int, prescricoes: Iterable[PrescricaoPRB]) -> None:
    sql = """
        INSERT INTO lwsa.motor_prescricao (
            execucao_id, cluster_id, acao, urgencia, prioridade_sugerida,
            prb_existente, prioridade_atual_prb, sugestao_repriorizacao, justificativa
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::json)
    """
    rows = [
        (
            execucao_id,
            p.cluster_id,
            p.acao,
            p.urgencia,
            p.prioridade_sugerida,
            p.prb_existente.prb_id if p.prb_existente else None,
            p.prioridade_atual_prb,
            p.sugestao_repriorizacao,
            _jsonb(p.justificativa),
        )
        for p in prescricoes
    ]
    if rows:
        cur.executemany(sql, rows)


def _insert_saude_clientes(cur, execucao_id: int, saudes: Iterable[SaudeCliente]) -> None:
    sql = """
        INSERT INTO lwsa.motor_saude_cliente (
            execucao_id, cliente_login, qtd_incs_periodo, qtd_chamados_periodo,
            severidade_media, alerta_recorrencia_alta, linha_do_tempo
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s::json)
    """
    rows = [
        (
            execucao_id,
            s.cliente_login,
            s.qtd_incs_periodo,
            s.qtd_chamados_periodo,
            s.severidade_media,
            s.alerta_recorrencia_alta,
            _jsonb(s.linha_do_tempo),
        )
        for s in saudes
    ]
    if rows:
        cur.executemany(sql, rows)


def _insert_validacoes_entrega(
    cur, execucao_id: int, validacoes: Iterable[ValidacaoEntrega]
) -> None:
    """Insere N validações de entrega + suas equipes impactadas (V3.1).

    Persistência em 2 tabelas:
      - lwsa.motor_validacao_entrega: 1 linha por PRB (com os 3 dicts em json
        preservados para retrocompatibilidade).
      - lwsa.motor_validacao_entrega_equipe: 1 linha por (PRB, equipe) —
        espelho relacional das colunas json, pensado para dashboards.

    Loop por validação (não executemany) porque precisamos do `id` retornado
    pelo RETURNING para popular a tabela filha. Volume tipico: 10 PRBs/ciclo,
    overhead irrelevante.
    """
    sql_pai = """
        INSERT INTO lwsa.motor_validacao_entrega (
            execucao_id, prb_id, descricao_curta, produto, servidor, status_prb,
            data_resolucao, dias_pos_resolucao, qtd_incs_pos_resolucao,
            veredicto, incs_reincidentes,
            grupo_designado, data_abertura_prb,
            qtd_incs_pre_resolucao, clientes_unicos_pre, categorias_pre,
            chamados_pre, chamados_pos, delta_chamados_pct,
            qtd_prbs_novos_pos_resolucao, prbs_novos,
            equipes_impactadas_pre, equipes_impactadas_pos, equipes_delta_pct
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::json,
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s::json,
                %s::json, %s::json, %s::json)
        RETURNING id
    """
    sql_filha = """
        INSERT INTO lwsa.motor_validacao_entrega_equipe (
            validacao_id, equipe, qtd_pre, qtd_pos, delta_pct
        )
        VALUES (%s, %s, %s, %s, %s)
    """
    for v in validacoes:
        cur.execute(sql_pai, (
            execucao_id,
            v.prb_id,
            v.descricao_curta,
            v.produto or None,
            v.servidor or None,
            v.status_prb,
            v.data_resolucao,
            v.dias_pos_resolucao,
            v.qtd_incs_pos_resolucao,
            v.veredicto,
            _jsonb([
                {
                    "inc_id": i.inc_id,
                    "prioridade": i.prioridade_atual,
                    "abertura": i.abertura.isoformat() if i.abertura else None,
                }
                for i in v.incs_reincidentes
            ]),
            v.grupo_designado or None,
            v.data_abertura_prb,
            v.qtd_incs_pre_resolucao,
            v.clientes_unicos_pre,
            v.categorias_pre,
            v.chamados_pre,
            v.chamados_pos,
            v.delta_chamados_pct,
            v.qtd_prbs_novos_pos_resolucao,
            _jsonb(v.prbs_novos),
            _jsonb(v.equipes_impactadas_pre),
            _jsonb(v.equipes_impactadas_pos),
            _jsonb(v.equipes_delta_pct),
        ))
        validacao_id = cur.fetchone()[0]

        # Espelha as 3 colunas json em forma relacional. Itera as equipes
        # do top do pré (são as "impactadas"); pega qtd_pos e delta_pct das
        # outras 2 estruturas com fallback defensivo (não deveriam divergir).
        for equipe, qtd_pre in v.equipes_impactadas_pre.items():
            cur.execute(sql_filha, (
                validacao_id,
                equipe,
                int(qtd_pre),
                int(v.equipes_impactadas_pos.get(equipe, 0)),
                float(v.equipes_delta_pct.get(equipe, 0.0)),
            ))


# -----------------------------------------------------------------------------
# API pública
# -----------------------------------------------------------------------------
def persistir_execucao(execucao: ExecucaoMotor) -> int | None:
    """Persiste o ciclo em uma transação atômica. Retorna `execucao_id` se OK,
    None em falha (motor segue funcionando — JSON ainda foi gravado em paralelo).

    Antes da inserção, se CLEANUP_TTL_HABILITADO=true, faz cleanup TTL —
    execuções > N dias são removidas automaticamente (ON DELETE CASCADE remove
    filhas). Quando false (default), cleanup é responsabilidade externa (DBA).
    """
    if not config.PERSISTIR_NO_BANCO:
        log.info("Persistência Postgres desabilitada (PERSISTIR_NO_BANCO=false).")
        return None

    # Cleanup ANTES do insert (em transação separada — falha aqui não impede
    # gravação do ciclo atual). Só roda se habilitado (requer permissão DELETE).
    if config.CLEANUP_TTL_HABILITADO:
        purgar_execucoes_antigas()

    # Singletons (qtd_incs == 1) são omitidos do banco — só agrupamentos
    # significativos entram em motor_cluster. Singletons continuam vivos em
    # memória e no JSON do dashboard (consumidos por customer_monitor e UI).
    clusters_persistir = [c for c in execucao.clusters if c.qtd_incs >= 2]
    singletons_omitidos = len(execucao.clusters) - len(clusters_persistir)

    try:
        from db import conectar
        with conectar() as conn:
            with conn.cursor() as cur:
                # Transação única — tudo ou nada.
                execucao_id = _insert_execucao(cur, execucao, len(clusters_persistir))
                _insert_clusters(cur, execucao_id, clusters_persistir)
                _insert_prescricoes(cur, execucao_id, execucao.prescricoes)
                _insert_saude_clientes(cur, execucao_id, execucao.saude_clientes)
                _insert_validacoes_entrega(cur, execucao_id, execucao.validacoes_entrega)
                conn.commit()
        log.info(
            "Persistência Postgres OK: execucao_id=%d (%d clusters, %d singletons omitidos, "
            "%d prescrições, %d saúde, %d validações).",
            execucao_id,
            len(clusters_persistir),
            singletons_omitidos,
            len(execucao.prescricoes),
            len(execucao.saude_clientes),
            len(execucao.validacoes_entrega),
        )
        return execucao_id
    except Exception as exc:
        log.exception("Falha na persistência Postgres — JSON ainda foi gravado: %s", exc)
        return None


# -----------------------------------------------------------------------------
# Painel Change Team — TRUNCATE+INSERT atômico (D-04)
# -----------------------------------------------------------------------------
def persistir_painel_change_team(rows: List[PainelChangeTeamRow]) -> int:
    """TRUNCATE + INSERT atômico do painel Change Team.

    Padrão D-04 (snapshot completo a cada ciclo). Mesmo idioma de
    `persistir_execucao`: `with conectar() as conn` + cursor manual +
    `conn.commit()` ao final. Sem CASCADE — tabela é folha (sem FK para
    filhos).

    TRUNCATE pode aguardar leitores Superset; cadência 6h tolera espera.
    Try/except retorna 0 em falha — caller (validar_entregas) tem try/except
    próprio que propaga para `execucao.erros` sem regredir CON-012.
    """
    if not config.PERSISTIR_NO_BANCO:
        log.info("Persistência Postgres desabilitada — pulando painel Change Team.")
        return 0
    try:
        from db import conectar
        with conectar() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"TRUNCATE TABLE {config.SCHEMA_BANCO}."
                    f"{config.TABELA_CHANGE_TEAM_PAINEL} RESTART IDENTITY"
                )
                if rows:
                    _insert_painel_change_team(cur, rows)
                conn.commit()
        log.info("Painel Change Team gravado: %d rows.", len(rows))
        return len(rows)
    except Exception as exc:
        log.exception("Falha ao persistir painel Change Team: %s", exc)
        return 0


def _insert_painel_change_team(
    cur, rows: Iterable[PainelChangeTeamRow]
) -> None:
    """Batch INSERT — sem RETURNING porque tabela é folha (sem FK para filhos)."""
    sql = f"""
        INSERT INTO {config.SCHEMA_BANCO}.{config.TABELA_CHANGE_TEAM_PAINEL} (
            prb_id, descricao_curta, produto, servidor,
            status_snow, prioridade_atual, dias_em_aberto,
            grupo_designado, ultima_atualizacao,
            veredicto, data_resolucao, dias_pos_resolucao,
            qtd_incs_pos_resolucao, qtd_incs_pre_resolucao,
            delta_chamados_pct, qtd_prbs_novos_pos_resolucao,
            incs_reincidentes, prbs_novos,
            snapshot_em
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s,
                %s::json, %s::json,
                %s)
    """
    cur.executemany(
        sql,
        [
            (
                r.prb_id, r.descricao_curta, r.produto, r.servidor,
                r.status_snow, r.prioridade_atual, r.dias_em_aberto,
                r.grupo_designado, r.ultima_atualizacao,
                r.veredicto, r.data_resolucao, r.dias_pos_resolucao,
                r.qtd_incs_pos_resolucao, r.qtd_incs_pre_resolucao,
                r.delta_chamados_pct, r.qtd_prbs_novos_pos_resolucao,
                _jsonb(r.incs_reincidentes), _jsonb(r.prbs_novos),
                r.snapshot_em,
            )
            for r in rows
        ],
    )