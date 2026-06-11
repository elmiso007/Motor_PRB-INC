# =============================================================================
# Tests — change_team (Painel Change Team, Phase 1 PNCT-01)
# =============================================================================
# Cobre 6 cenários derivados do RESEARCH § Phase Requirements → Test Map:
#   1. Lista master vazia não quebra o pipeline
#   2. Separação correta abertos vs resolvidos (D-05 vs D-06)
#   3. fonte_chamados=None ainda produz rows válidas
#   4. PRBs na master ausentes do SNow geram log.warning (Pitfall 5)
#   5. Toggle CHANGE_TEAM_HABILITADO=False salta o bloco no entry-point
#   6. Falha do bloco Change Team NÃO derruba V3.1 (CON-012 LOCKED)
#
# Padrão de Fake fonte (sem rede, sem banco) seguindo
# tests/test_validador_entrega.py.
# =============================================================================
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Sequence

import pytest

import config
import change_team
import validar_entregas
from builders import make_prb
from models import Incidente, PRBExistente


# -----------------------------------------------------------------------------
# Fake fonte — implementa apenas os métodos da ABC FonteIncidentes que o
# change_team / _avaliar_prb exercitam. Demais métodos levantam
# NotImplementedError pra detectar uso inesperado.
# -----------------------------------------------------------------------------
class _FakeFonteCT:
    def __init__(self, prbs_por_numero: Dict[str, PRBExistente]):
        self._prbs = prbs_por_numero

    def listar_prbs_por_numero(
        self, numeros: Sequence[str]
    ) -> List[PRBExistente]:
        return [self._prbs[n] for n in numeros if n in self._prbs]

    def listar_incidentes_por_produto_servidor(
        self,
        produto: str,
        servidor: str,
        desde: datetime,
        ate: Optional[datetime] = None,
    ) -> List[Incidente]:
        # Vazio — não há incidentes pós-resolução no fake → veredicto ENTREGA_VALIDADA
        return []

    def listar_prbs_novos_no_ci_periodo(
        self,
        produto: str,
        servidor: str,
        desde: datetime,
        ignorar_prb_id: str = "",
    ) -> List[str]:
        return []

    def contar_incidentes_no_ci_periodo(
        self,
        produto: str,
        servidor: str,
        desde: datetime,
        ate: datetime,
    ) -> Dict[str, int]:
        # _avaliar_prb usa este método pra volumetria pré-resolução
        return {"qtd": 0, "clientes_unicos": 0, "categorias": 0}


# -----------------------------------------------------------------------------
# Test 1 — Lista master vazia
# -----------------------------------------------------------------------------
def test_painel_lista_vazia_nao_quebra(monkeypatch):
    """Master vazia → função retorna [] sem chamar listar_prbs_por_numero."""
    monkeypatch.setattr(
        "change_team._ler_lista_change_team_ativa", lambda: []
    )
    fonte = _FakeFonteCT({})
    rows = change_team.gerar_painel_change_team(fonte, fonte_chamados=None)
    assert rows == []


# -----------------------------------------------------------------------------
# Test 2 — Separação abertos vs resolvidos
# -----------------------------------------------------------------------------
def test_painel_separa_abertos_de_resolvidos(monkeypatch):
    """1 PRB aberto + 1 resolvido → 2 rows, com veredictos coerentes."""
    aberto = make_prb(
        prb_id="PRB0000A",
        status="Em Análise",
        data_resolucao=None,
    )
    aberto.aberto_em = datetime.now(timezone.utc) - timedelta(days=30)

    resolvido = make_prb(
        prb_id="PRB0000B",
        status=config.STATUS_PRB_ENCERRADOS[0],
        data_resolucao=datetime.now(timezone.utc) - timedelta(days=10),
    )
    resolvido.aberto_em = datetime.now(timezone.utc) - timedelta(days=40)

    monkeypatch.setattr(
        "change_team._ler_lista_change_team_ativa",
        lambda: ["PRB0000A", "PRB0000B"],
    )
    fonte = _FakeFonteCT({"PRB0000A": aberto, "PRB0000B": resolvido})

    rows = change_team.gerar_painel_change_team(fonte, fonte_chamados=None)

    assert len(rows) == 2
    by_id = {r.prb_id: r for r in rows}

    # Aberto: sem veredicto, sem data_resolucao
    assert by_id["PRB0000A"].veredicto is None
    assert by_id["PRB0000A"].data_resolucao is None

    # Resolvido: tem veredicto e data_resolucao
    assert by_id["PRB0000B"].veredicto in (
        "REINCIDENCIA",
        "ENTREGA_VALIDADA",
        "INCONCLUSIVO",
    )
    assert by_id["PRB0000B"].data_resolucao is not None


# -----------------------------------------------------------------------------
# Test 3 — fonte_chamados=None
# -----------------------------------------------------------------------------
def test_painel_sem_fonte_chamados(monkeypatch):
    """fonte_chamados=None ainda produz row válida (delta zerado)."""
    resolvido = make_prb(
        prb_id="PRB0000C",
        status=config.STATUS_PRB_ENCERRADOS[0],
        data_resolucao=datetime.now(timezone.utc) - timedelta(days=15),
    )
    resolvido.aberto_em = datetime.now(timezone.utc) - timedelta(days=45)

    monkeypatch.setattr(
        "change_team._ler_lista_change_team_ativa", lambda: ["PRB0000C"]
    )
    fonte = _FakeFonteCT({"PRB0000C": resolvido})

    rows = change_team.gerar_painel_change_team(fonte, fonte_chamados=None)

    assert len(rows) == 1
    # delta numérico válido (zero quando sem fonte_chamados)
    assert isinstance(rows[0].delta_chamados_pct, float)


# -----------------------------------------------------------------------------
# Test 4 — Detecção de PRBs faltantes (Pitfall 5)
# -----------------------------------------------------------------------------
def test_painel_detecta_prbs_faltantes(monkeypatch, caplog):
    """Master tem PRBs ausentes do SNow → log.warning + skip silencioso."""
    presente = make_prb(prb_id="PRB1", status="Em Análise")
    presente.aberto_em = datetime.now(timezone.utc) - timedelta(days=5)

    monkeypatch.setattr(
        "change_team._ler_lista_change_team_ativa",
        lambda: ["PRB1", "PRB2", "PRB3"],
    )
    fonte = _FakeFonteCT({"PRB1": presente})

    with caplog.at_level("WARNING", logger="change_team"):
        rows = change_team.gerar_painel_change_team(fonte, fonte_chamados=None)

    assert len(rows) == 1  # só PRB1 foi encontrado
    # Warning loga os faltantes (PRB2 e PRB3)
    warnings_text = " ".join(caplog.messages)
    assert "PRB2" in warnings_text
    assert "PRB3" in warnings_text


# -----------------------------------------------------------------------------
# Test 5 — Toggle CHANGE_TEAM_HABILITADO=False
# -----------------------------------------------------------------------------
def test_painel_toggle_off(monkeypatch):
    """Toggle off → executar_validacao não chama gerar_painel_change_team."""
    monkeypatch.setattr(config, "CHANGE_TEAM_HABILITADO", False)
    monkeypatch.setattr(config, "USAR_MOCKS", True)
    monkeypatch.setattr(config, "PERSISTIR_NO_BANCO", False)

    # Contador de chamadas
    chamadas = {"count": 0}

    def fake_gerar(*args, **kwargs):
        chamadas["count"] += 1
        return []

    monkeypatch.setattr("change_team.gerar_painel_change_team", fake_gerar)

    execucao = validar_entregas.executar_validacao()

    assert chamadas["count"] == 0, "Bloco Change Team deveria estar pulado"
    # V3.1 continua funcionando — não há erro propagado
    assert all("change_team" not in e for e in execucao.erros), (
        f"Esperava sem erros change_team, obtido: {execucao.erros}"
    )


# -----------------------------------------------------------------------------
# Test 6 — Falha do Change Team NÃO derruba V3.1 (CON-012 LOCKED)
# -----------------------------------------------------------------------------
def test_falha_change_team_nao_derruba_validador(monkeypatch):
    """gerar_painel_change_team lança exception → validacoes_entrega intacto + erros.append."""
    monkeypatch.setattr(config, "CHANGE_TEAM_HABILITADO", True)
    monkeypatch.setattr(config, "USAR_MOCKS", True)
    monkeypatch.setattr(config, "PERSISTIR_NO_BANCO", False)

    def fake_gerar_explode(*args, **kwargs):
        raise RuntimeError("simulado — falha proposital no Change Team")

    # patch no validar_entregas (onde é importado lazy) ou no módulo
    monkeypatch.setattr(
        "change_team.gerar_painel_change_team", fake_gerar_explode
    )

    execucao = validar_entregas.executar_validacao()

    # V3.1 rodou e populou validacoes_entrega (não foi derrubado pela falha CT)
    assert execucao.validacoes_entrega is not None
    # Erro do Change Team foi registrado em execucao.erros (prefixo "change_team:")
    erros_str = " ".join(execucao.erros)
    assert "change_team:" in erros_str, (
        f"Esperava prefixo 'change_team:' em erros, obtido: {execucao.erros}"
    )
