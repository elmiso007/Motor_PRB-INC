# =============================================================================
# Testes — validador_entrega (prisma retrospectivo)
# =============================================================================
# Cobertura: matriz dos 3 veredictos + edge cases (PRB sem CI, ordenação,
# precedência REINCIDENCIA sobre janela mínima).
# =============================================================================
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import List

import config
from models import Incidente, PRBExistente
from validador_entrega import (
    VEREDICTO_REINCIDENCIA,
    VEREDICTO_VALIDADA,
    VEREDICTO_INCONCLUSIVO,
    _classificar,
    gerar_validacoes_entrega,
)

from builders import make_incidente, make_prb


# -----------------------------------------------------------------------------
# Fake fonte — só implementa o que o validador usa
# -----------------------------------------------------------------------------
class _FakeFonte:
    """Fonte de incidentes mínima: devolve PRBs e INCs sob comando.

    Implementa a parte da interface FonteIncidentes que o validador toca.
    Outros métodos lançam NotImplementedError — falham alto se algo mudar.
    """

    def __init__(
        self,
        prbs: List[PRBExistente],
        incs_por_chave: dict[tuple[str, str], List[Incidente]] | None = None,
        vol_pre_por_chave: dict[tuple[str, str], dict[str, int]] | None = None,
        prbs_novos_por_chave: dict[tuple[str, str], List[str]] | None = None,
    ) -> None:
        self.prbs = prbs
        self.incs_por_chave = incs_por_chave or {}
        self.vol_pre_por_chave = vol_pre_por_chave or {}
        self.prbs_novos_por_chave = prbs_novos_por_chave or {}

    def listar_prbs_para_validacao(self, dias: int) -> List[PRBExistente]:
        return list(self.prbs)

    def listar_incidentes_por_produto_servidor(
        self, produto: str, servidor: str, desde: datetime,
        ate: datetime | None = None,
    ) -> List[Incidente]:
        return list(self.incs_por_chave.get((produto, servidor), []))

    def contar_incidentes_no_ci_periodo(
        self, produto: str, servidor: str, desde: datetime, ate: datetime
    ) -> dict:
        return self.vol_pre_por_chave.get(
            (produto, servidor),
            {"qtd": 0, "clientes_unicos": 0, "categorias": 0},
        )

    def listar_prbs_novos_no_ci_periodo(
        self, produto: str, servidor: str, desde: datetime, ignorar_prb_id: str = ""
    ) -> List[str]:
        novos = self.prbs_novos_por_chave.get((produto, servidor), [])
        return [p for p in novos if p != ignorar_prb_id]

    def listar_incidentes_recentes(self, horas):
        raise NotImplementedError

    def listar_prbs_abertos(self):
        raise NotImplementedError

    def listar_incidentes_cliente(self, login_cliente, meses):
        raise NotImplementedError


# -----------------------------------------------------------------------------
# Classificador puro
# -----------------------------------------------------------------------------
class TestClassificar:
    def test_reincidencia_pelo_limiar(self):
        # >= LIMIAR_INCS_REINCIDENCIA INCs => REINCIDENCIA, independente da janela
        assert _classificar(
            config.LIMIAR_INCS_REINCIDENCIA, 1
        ) == VEREDICTO_REINCIDENCIA

    def test_validada_quando_zero_incs_e_janela_suficiente(self):
        assert _classificar(0, config.MIN_DIAS_PARA_VALIDAR) == VEREDICTO_VALIDADA

    def test_inconclusivo_quando_janela_curta_sem_incs(self):
        # 0 INCs mas janela < MIN_DIAS_PARA_VALIDAR => INCONCLUSIVO
        assert _classificar(0, config.MIN_DIAS_PARA_VALIDAR - 1) == VEREDICTO_INCONCLUSIVO

    def test_inconclusivo_quando_poucas_incs(self):
        # 1 ou 2 INCs (abaixo do limiar de 3) e tempo qualquer => INCONCLUSIVO
        assert _classificar(
            config.LIMIAR_INCS_REINCIDENCIA - 1, 30
        ) == VEREDICTO_INCONCLUSIVO

    def test_reincidencia_tem_precedencia_sobre_janela_curta(self):
        # Reincidência detectada no 2º dia ainda é reincidência (não vira inconclusivo)
        assert _classificar(
            config.LIMIAR_INCS_REINCIDENCIA, 2
        ) == VEREDICTO_REINCIDENCIA


# -----------------------------------------------------------------------------
# Avaliação completa (gerar_validacoes_entrega)
# -----------------------------------------------------------------------------
def _agora() -> datetime:
    return datetime.now(timezone.utc)


class TestGerarValidacoes:
    def test_veredicto_validada_para_prb_resolvido_sem_incs_novas(self):
        prb = make_prb(
            prb_id="PRB0001",
            produto="VPS",
            servidor="vps-01",
            status="Aguardando Validação da Resolução",
            data_resolucao=_agora() - timedelta(days=config.MIN_DIAS_PARA_VALIDAR + 1),
        )
        fonte = _FakeFonte(prbs=[prb])  # sem INCs novas no produto/servidor
        validacoes = gerar_validacoes_entrega(fonte)

        assert len(validacoes) == 1
        assert validacoes[0].veredicto == VEREDICTO_VALIDADA
        assert validacoes[0].qtd_incs_pos_resolucao == 0

    def test_veredicto_reincidencia_quando_incs_voltam(self):
        prb = make_prb(
            prb_id="PRB0002",
            produto="DNS",
            servidor="dns-01",
            status="Encerrado Automaticamente",
            data_resolucao=_agora() - timedelta(days=5),
        )
        incs_novas = [
            make_incidente(
                inc_id=f"INC{i:07d}", produto="DNS", servidor="dns-01"
            )
            for i in range(config.LIMIAR_INCS_REINCIDENCIA + 1)
        ]
        fonte = _FakeFonte(prbs=[prb], incs_por_chave={("DNS", "dns-01"): incs_novas})

        validacoes = gerar_validacoes_entrega(fonte)

        assert len(validacoes) == 1
        v = validacoes[0]
        assert v.veredicto == VEREDICTO_REINCIDENCIA
        assert v.qtd_incs_pos_resolucao == len(incs_novas)
        assert len(v.incs_reincidentes) == len(incs_novas)

    def test_veredicto_inconclusivo_quando_janela_curta(self):
        # 0 INCs novas mas só 2 dias desde resolução — não dá pra validar ainda
        prb = make_prb(
            prb_id="PRB0003",
            produto="Hosting",
            servidor="hm-01",
            status="Aguardando Validação da Resolução",
            data_resolucao=_agora() - timedelta(days=2),
        )
        fonte = _FakeFonte(prbs=[prb])
        validacoes = gerar_validacoes_entrega(fonte)

        assert validacoes[0].veredicto == VEREDICTO_INCONCLUSIVO

    def test_prb_sem_produto_ou_servidor_vira_inconclusivo(self):
        # Sem CI não dá pra matchar INCs — vira INCONCLUSIVO defensivo
        prb = make_prb(
            prb_id="PRB0004",
            produto="",
            servidor="",
            data_resolucao=_agora() - timedelta(days=20),
        )
        fonte = _FakeFonte(prbs=[prb])
        validacoes = gerar_validacoes_entrega(fonte)

        assert validacoes[0].veredicto == VEREDICTO_INCONCLUSIVO
        assert validacoes[0].qtd_incs_pos_resolucao == 0

    def test_ordenacao_reincidencia_primeiro(self):
        # Mistura: 1 validada, 1 reincidência, 1 inconclusivo — reincidência deve
        # aparecer no topo (ordem útil pro plantão).
        prb_validada = make_prb(
            prb_id="PRB_OK", produto="VPS", servidor="vps-ok",
            data_resolucao=_agora() - timedelta(days=10),
        )
        prb_reinc = make_prb(
            prb_id="PRB_REINC", produto="DNS", servidor="dns-bad",
            data_resolucao=_agora() - timedelta(days=5),
        )
        prb_incon = make_prb(
            prb_id="PRB_INCON", produto="MAIL", servidor="mail-x",
            data_resolucao=_agora() - timedelta(days=2),
        )
        incs = [
            make_incidente(inc_id=f"INC{i}", produto="DNS", servidor="dns-bad")
            for i in range(config.LIMIAR_INCS_REINCIDENCIA + 1)
        ]
        fonte = _FakeFonte(
            prbs=[prb_validada, prb_reinc, prb_incon],
            incs_por_chave={("DNS", "dns-bad"): incs},
        )

        validacoes = gerar_validacoes_entrega(fonte)

        assert [v.prb_id for v in validacoes][0] == "PRB_REINC"
        assert validacoes[0].veredicto == VEREDICTO_REINCIDENCIA

    def test_erro_em_um_prb_nao_derruba_outros(self):
        # PRB problemático: produto/servidor que cause exceção na fonte (simula bug)
        class _FontePicada(_FakeFonte):
            def listar_incidentes_por_produto_servidor(self, produto, servidor, desde, ate=None):
                if produto == "QUEBRA":
                    raise RuntimeError("simulação de bug")
                return super().listar_incidentes_por_produto_servidor(produto, servidor, desde, ate)

        prb_ok = make_prb(
            prb_id="PRB_OK", produto="VPS", servidor="vps-ok",
            data_resolucao=_agora() - timedelta(days=10),
        )
        prb_quebra = make_prb(
            prb_id="PRB_QUEBRA", produto="QUEBRA", servidor="x",
            data_resolucao=_agora() - timedelta(days=10),
        )
        fonte = _FontePicada(prbs=[prb_quebra, prb_ok])
        validacoes = gerar_validacoes_entrega(fonte)

        # Apenas o PRB_OK deve sobreviver — o outro foi catched no _avaliar_prb
        prb_ids = [v.prb_id for v in validacoes]
        assert "PRB_OK" in prb_ids
        assert "PRB_QUEBRA" not in prb_ids

# -----------------------------------------------------------------------------
# Fake fonte de chamados — V3 usa match por prb_id/inc_ids
# -----------------------------------------------------------------------------
class _FakeFonteChamados:
    """Devolve contagens fixas pré/pós por prb_id + agrupamentos por equipe.

    Estruturas:
      contagens_por_prb    = {prb_id: {"pre": N, "pos": M}}
      agrupamentos_por_prb = {prb_id: {"pre": {equipe: qtd, ...},
                                       "pos": {equipe: qtd, ...}}}
    O validador chama contar_chamados_vinculados 2x e
    agrupar_chamados_vinculados_por_equipe 2x por PRB; alternamos pré/pós
    com base no histórico (chamadas separadas por método).
    """

    def __init__(
        self,
        contagens_por_prb: dict[str, dict[str, int]] | None = None,
        agrupamentos_por_prb: dict[str, dict[str, dict[str, int]]] | None = None,
    ) -> None:
        self.contagens_por_prb = contagens_por_prb or {}
        self.agrupamentos_por_prb = agrupamentos_por_prb or {}
        # Históricos separados por método (cada um alterna pré/pós).
        self.chamadas: List[tuple] = []
        self.chamadas_agrupar: List[tuple] = []

    def contar_chamados_vinculados(self, prb_id, incs_ids, desde, ate):
        self.chamadas.append((prb_id, tuple(incs_ids), desde, ate))
        cfg = self.contagens_por_prb.get(prb_id)
        if not cfg:
            return 0
        nth = sum(1 for c in self.chamadas if c[0] == prb_id)
        return cfg.get("pre" if nth == 1 else "pos", 0)

    def agrupar_chamados_vinculados_por_equipe(self, prb_id, incs_ids, desde, ate):
        self.chamadas_agrupar.append((prb_id, tuple(incs_ids), desde, ate))
        cfg = self.agrupamentos_por_prb.get(prb_id)
        if not cfg:
            return {}
        nth = sum(1 for c in self.chamadas_agrupar if c[0] == prb_id)
        fase = "pre" if nth == 1 else "pos"
        return dict(cfg.get(fase, {}))

    def contar_chamados_por_produto(self, produto, desde, ate):
        # Mantido só pra compat com a abstract — não é mais usado pelo validador.
        return 0

    def listar_chamados_periodo(self, horas, produtos=None):
        return []

    def listar_chamados_cliente(self, login_cliente, meses):
        return []


# -----------------------------------------------------------------------------
# Volumetria pré-resolução + Delta de chamados (V2)
# -----------------------------------------------------------------------------
class TestVolumetriaPre:
    def test_volumetria_pre_propagada_para_validacao(self):
        prb = make_prb(
            prb_id="PRB_X", produto="VPS", servidor="vps-01",
            data_resolucao=_agora() - timedelta(days=10),
        )
        fonte = _FakeFonte(
            prbs=[prb],
            vol_pre_por_chave={
                ("VPS", "vps-01"): {"qtd": 25, "clientes_unicos": 12, "categorias": 4},
            },
        )
        validacoes = gerar_validacoes_entrega(fonte)
        v = validacoes[0]
        assert v.qtd_incs_pre_resolucao == 25
        assert v.clientes_unicos_pre == 12
        assert v.categorias_pre == 4

    def test_volumetria_pre_zero_quando_fonte_nao_tem(self):
        prb = make_prb(
            prb_id="PRB_X", produto="VPS", servidor="vps-01",
            data_resolucao=_agora() - timedelta(days=10),
        )
        fonte = _FakeFonte(prbs=[prb])
        validacoes = gerar_validacoes_entrega(fonte)
        v = validacoes[0]
        assert v.qtd_incs_pre_resolucao == 0
        assert v.clientes_unicos_pre == 0
        assert v.categorias_pre == 0


class TestDeltaChamados:
    def test_delta_negativo_quando_chamados_caem(self):
        # Pre=20, Pos=5 → delta = (5-20)/20 = -0.75 (queda de 75%)
        prb = make_prb(
            prb_id="PRB_X", produto="VPS", servidor="vps-01",
            data_resolucao=_agora() - timedelta(days=10),
        )
        fonte_inc = _FakeFonte(prbs=[prb])
        fonte_ch = _FakeFonteChamados(
            contagens_por_prb={"PRB_X": {"pre": 20, "pos": 5}},
        )
        validacoes = gerar_validacoes_entrega(fonte_inc, fonte_ch)
        v = validacoes[0]
        assert v.chamados_pre == 20
        assert v.chamados_pos == 5
        assert v.delta_chamados_pct == -0.75

    def test_delta_zero_quando_pre_zero(self):
        # Sem base, delta = 0.0 (não pode dividir por zero)
        prb = make_prb(
            prb_id="PRB_X", produto="VPS", servidor="vps-01",
            data_resolucao=_agora() - timedelta(days=10),
        )
        fonte_inc = _FakeFonte(prbs=[prb])
        fonte_ch = _FakeFonteChamados(
            contagens_por_prb={"PRB_X": {"pre": 0, "pos": 0}},
        )
        validacoes = gerar_validacoes_entrega(fonte_inc, fonte_ch)
        v = validacoes[0]
        assert v.chamados_pre == 0
        assert v.chamados_pos == 0
        assert v.delta_chamados_pct == 0.0

    def test_sem_fonte_chamados_delta_continua_zero(self):
        # Quando gerar_validacoes_entrega é chamado sem fonte_chamados,
        # delta fica 0 mas demais campos funcionam normalmente.
        prb = make_prb(
            prb_id="PRB_X", produto="VPS", servidor="vps-01",
            data_resolucao=_agora() - timedelta(days=10),
        )
        fonte_inc = _FakeFonte(prbs=[prb])
        validacoes = gerar_validacoes_entrega(fonte_inc)  # sem fonte_chamados
        v = validacoes[0]
        assert v.chamados_pre == 0
        assert v.chamados_pos == 0
        assert v.delta_chamados_pct == 0.0

    def test_delta_positivo_quando_chamados_sobem(self):
        # Pre=4, Pos=10 → delta = (10-4)/4 = 1.5 (subida de 150%)
        prb = make_prb(
            prb_id="PRB_X", produto="VPS", servidor="vps-01",
            data_resolucao=_agora() - timedelta(days=10),
        )
        fonte_inc = _FakeFonte(prbs=[prb])
        fonte_ch = _FakeFonteChamados(
            contagens_por_prb={"PRB_X": {"pre": 4, "pos": 10}},
        )
        validacoes = gerar_validacoes_entrega(fonte_inc, fonte_ch)
        v = validacoes[0]
        assert v.delta_chamados_pct == 1.5


# -----------------------------------------------------------------------------
# PRBs novos abertos no mesmo CI pós-resolução (requisito de coordenação)
# -----------------------------------------------------------------------------
class TestPrbsNovosPosResolucao:
    def test_propaga_prbs_novos_para_validacao(self):
        prb = make_prb(
            prb_id="PRB_OK", produto="VPS", servidor="vps-01",
            data_resolucao=_agora() - timedelta(days=10),
        )
        fonte = _FakeFonte(
            prbs=[prb],
            prbs_novos_por_chave={
                ("VPS", "vps-01"): ["PRB_NEW_A", "PRB_NEW_B"],
            },
        )
        validacoes = gerar_validacoes_entrega(fonte)
        v = validacoes[0]
        assert v.qtd_prbs_novos_pos_resolucao == 2
        assert v.prbs_novos == ["PRB_NEW_A", "PRB_NEW_B"]

    def test_zero_quando_nao_ha_prb_novo(self):
        prb = make_prb(
            prb_id="PRB_OK", produto="VPS", servidor="vps-01",
            data_resolucao=_agora() - timedelta(days=10),
        )
        fonte = _FakeFonte(prbs=[prb])
        validacoes = gerar_validacoes_entrega(fonte)
        v = validacoes[0]
        assert v.qtd_prbs_novos_pos_resolucao == 0
        assert v.prbs_novos == []

    def test_proprio_prb_nao_se_auto_referencia(self):
        # Se a fonte (defensivamente) listar o proprio prb_id, o validador
        # passa ignorar_prb_id que ja exclui ele.
        prb = make_prb(
            prb_id="PRB_X", produto="VPS", servidor="vps-01",
            data_resolucao=_agora() - timedelta(days=10),
        )
        fonte = _FakeFonte(
            prbs=[prb],
            prbs_novos_por_chave={
                ("VPS", "vps-01"): ["PRB_X", "PRB_OUTRO"],  # PRB_X = o proprio
            },
        )
        validacoes = gerar_validacoes_entrega(fonte)
        v = validacoes[0]
        # Fake aplica o filtro ignorar_prb_id — devolve so PRB_OUTRO.
        assert v.qtd_prbs_novos_pos_resolucao == 1
        assert v.prbs_novos == ["PRB_OUTRO"]


# -----------------------------------------------------------------------------
# Times impactados (top N equipes via dynamics.chamados.equipeproprietaria)
# Requisito de coordenação 2026-06-03.
# -----------------------------------------------------------------------------
class TestEquipesImpactadas:
    def test_top_n_equipes_limita_ao_threshold(self, monkeypatch):
        # 7 equipes no pré → só TOP_EQUIPES_IMPACTADAS entram. Teste fixa em 5
        # pra exercitar o corte explicitamente (default atual é 7).
        monkeypatch.setattr(config, "TOP_EQUIPES_IMPACTADAS", 5)
        prb = make_prb(
            prb_id="PRB_X", produto="VPS", servidor="vps-01",
            data_resolucao=_agora() - timedelta(days=10),
        )
        fonte_inc = _FakeFonte(prbs=[prb])
        fonte_ch = _FakeFonteChamados(
            agrupamentos_por_prb={
                "PRB_X": {
                    "pre": {
                        "Cobrança": 15, "Suporte": 12, "DBA": 10,
                        "Redes": 7, "Plataforma": 5,
                        "Vendas": 3, "Financeiro": 1,  # devem ser cortadas
                    },
                    "pos": {},
                }
            },
        )
        validacoes = gerar_validacoes_entrega(fonte_inc, fonte_ch)
        v = validacoes[0]
        assert len(v.equipes_impactadas_pre) == 5
        # Top 5 deve estar em ordem decrescente.
        assert list(v.equipes_impactadas_pre.keys()) == [
            "Cobrança", "Suporte", "DBA", "Redes", "Plataforma"
        ]
        assert "Vendas" not in v.equipes_impactadas_pre
        assert "Financeiro" not in v.equipes_impactadas_pre

    def test_equipe_que_zerou_aparece_com_pos_zero_e_pct_minus_100(self):
        # Cobrança tinha 10 chamados pré, 0 pós → delta = -1.0 (-100%).
        prb = make_prb(
            prb_id="PRB_X", produto="VPS", servidor="vps-01",
            data_resolucao=_agora() - timedelta(days=10),
        )
        fonte_inc = _FakeFonte(prbs=[prb])
        fonte_ch = _FakeFonteChamados(
            agrupamentos_por_prb={
                "PRB_X": {
                    "pre": {"Cobrança": 10},
                    "pos": {},  # zerou
                }
            },
        )
        validacoes = gerar_validacoes_entrega(fonte_inc, fonte_ch)
        v = validacoes[0]
        assert v.equipes_impactadas_pre == {"Cobrança": 10}
        assert v.equipes_impactadas_pos == {"Cobrança": 0}
        assert v.equipes_delta_pct == {"Cobrança": -1.0}

    def test_equipe_que_aumentou_pos(self):
        # Suporte foi de 4 para 10 → +1.5 (+150%).
        prb = make_prb(
            prb_id="PRB_X", produto="VPS", servidor="vps-01",
            data_resolucao=_agora() - timedelta(days=10),
        )
        fonte_inc = _FakeFonte(prbs=[prb])
        fonte_ch = _FakeFonteChamados(
            agrupamentos_por_prb={
                "PRB_X": {
                    "pre": {"Suporte": 4},
                    "pos": {"Suporte": 10},
                }
            },
        )
        validacoes = gerar_validacoes_entrega(fonte_inc, fonte_ch)
        v = validacoes[0]
        assert v.equipes_impactadas_pos["Suporte"] == 10
        assert v.equipes_delta_pct["Suporte"] == 1.5

    def test_apenas_equipes_do_top_pre_recebem_pct(self):
        # Time que aparece SO no pos (não estava no pré) é ignorado —
        # só rastreamos quem ESTAVA chamando antes do fix.
        prb = make_prb(
            prb_id="PRB_X", produto="VPS", servidor="vps-01",
            data_resolucao=_agora() - timedelta(days=10),
        )
        fonte_inc = _FakeFonte(prbs=[prb])
        fonte_ch = _FakeFonteChamados(
            agrupamentos_por_prb={
                "PRB_X": {
                    "pre": {"Cobrança": 5},
                    "pos": {"Cobrança": 2, "TimeNovo": 8},  # TimeNovo não é top do pre
                }
            },
        )
        validacoes = gerar_validacoes_entrega(fonte_inc, fonte_ch)
        v = validacoes[0]
        assert set(v.equipes_impactadas_pre.keys()) == {"Cobrança"}
        assert set(v.equipes_impactadas_pos.keys()) == {"Cobrança"}
        assert "TimeNovo" not in v.equipes_impactadas_pos

    def test_sem_agrupamento_retorna_dicts_vazios(self):
        prb = make_prb(
            prb_id="PRB_X", produto="VPS", servidor="vps-01",
            data_resolucao=_agora() - timedelta(days=10),
        )
        fonte_inc = _FakeFonte(prbs=[prb])
        fonte_ch = _FakeFonteChamados()  # nenhum agrupamento
        validacoes = gerar_validacoes_entrega(fonte_inc, fonte_ch)
        v = validacoes[0]
        assert v.equipes_impactadas_pre == {}
        assert v.equipes_impactadas_pos == {}
        assert v.equipes_delta_pct == {}

    def test_sem_fonte_chamados_retorna_dicts_vazios(self):
        # Sem fonte_chamados, validador devolve campos default (dicts vazios).
        prb = make_prb(
            prb_id="PRB_X", produto="VPS", servidor="vps-01",
            data_resolucao=_agora() - timedelta(days=10),
        )
        fonte_inc = _FakeFonte(prbs=[prb])
        validacoes = gerar_validacoes_entrega(fonte_inc)  # sem fonte_chamados
        v = validacoes[0]
        assert v.equipes_impactadas_pre == {}
        assert v.equipes_impactadas_pos == {}
        assert v.equipes_delta_pct == {}
