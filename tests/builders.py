# =============================================================================
# Builders — fábricas de objetos para testes unitários
# =============================================================================
# Funções make_X criam Incidente, Cluster e PRBExistente com defaults sensatos.
# Configuração de sys.path está em conftest.py (descoberto automaticamente
# pelo pytest).
# =============================================================================
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import List, Optional

from models import Incidente, Cluster, PRBExistente


def make_incidente(
    inc_id: str = "INC0000001",
    prioridade: str = "P3",
    tem_contorno: bool = False,
    descricao_curta: str = "Servidor VPS fora",
    descricao: str = "VPS não responde.",
    qtd_updates: int = 3,
    servidor: str = "vps-prod-01",
    produto: str = "VPS",
    login_cliente: str = "cliente001",
    abertura: Optional[datetime] = None,
    atualizacao: Optional[datetime] = None,
    tempo_contorno_min: int = 0,
    tipo_usuario: str = "Nominal",
) -> Incidente:
    """Cria um Incidente com defaults sensatos. Overrides via kwargs."""
    if abertura is None:
        abertura = datetime.now(timezone.utc) - timedelta(hours=1)
    if atualizacao is None:
        atualizacao = abertura + timedelta(minutes=30)
    return Incidente(
        inc_id=inc_id,
        descricao_curta=descricao_curta,
        descricao=descricao,
        servidor=servidor,
        produto=produto,
        login_cliente=login_cliente,
        prioridade_atual=prioridade,
        abertura=abertura,
        atualizacao=atualizacao,
        qtd_atualizacoes=qtd_updates,
        tem_solucao_contorno=tem_contorno,
        tempo_solucao_contorno_min=tempo_contorno_min,
        tipo_usuario=tipo_usuario,
    )


def make_cluster(
    cluster_id: str = "cluster-0",
    nome: str = "vps servidor fora",
    qtd_incs: int = 6,
    todos_p3: bool = True,
    todos_sem_contorno: bool = True,
    produto: str = "VPS",
    servidor: str = "vps-prod-01",
    score_criticidade: float = 0.5,
    score_ineficiencia: float = 0.5,
    chamados_relacionados: int = 0,
    cis_recorrentes_15d: Optional[List[str]] = None,
    descricao_curta: str = "Servidor VPS fora",
    descricao: str = "VPS não responde.",
) -> Cluster:
    """Cria um Cluster com N incidentes uniformes. Defaults sensatos."""
    incidentes = [
        make_incidente(
            inc_id=f"INC{i:07d}",
            prioridade="P3" if todos_p3 else "P4",
            tem_contorno=not todos_sem_contorno,
            descricao_curta=descricao_curta,
            descricao=descricao,
            servidor=servidor,
            produto=produto,
        )
        for i in range(qtd_incs)
    ]
    return Cluster(
        cluster_id=cluster_id,
        nome=nome,
        incidentes=incidentes,
        servidor_principal=servidor,
        produto=produto,
        qtd_incs=qtd_incs,
        score_criticidade=score_criticidade,
        score_ineficiencia=score_ineficiencia,
        tem_solucao_contorno=not todos_sem_contorno,
        tempo_contorno_min_medio=0,
        chamados_relacionados=chamados_relacionados,
        cis_recorrentes_15d=cis_recorrentes_15d or [],
        termos_dominantes=["vps", "servidor", "fora"],
    )


def make_prb(
    prb_id: str = "PRB0000001",
    produto: str = "VPS",
    servidor: str = "vps-prod-01",
    prioridade: str = "P3",
    status: str = "Em Análise",
    data_resolucao: Optional[datetime] = None,
) -> PRBExistente:
    """Cria um PRBExistente com defaults sensatos."""
    return PRBExistente(
        prb_id=prb_id,
        descricao_curta="Kernel panic recorrente",
        descricao="Recorrência em VPS",
        produto=produto,
        servidor=servidor,
        prioridade_atual=prioridade,
        status=status,
        data_resolucao=data_resolucao,
    )