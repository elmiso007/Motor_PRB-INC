# =============================================================================
# Testes — scores do analyzer
# =============================================================================
# Foco: garantir que _score_criticidade e _score_ineficiencia produzem valores
# determinísticos e no range esperado [0.0, 1.0]. Hotspot — score errado
# impacta priorização downstream.
# =============================================================================
from datetime import datetime, timezone, timedelta

import pytest

from analyzer import (
    _fundir_singletons_por_ci,
    _score_criticidade,
    _score_ineficiencia,
    _termos_dominantes,
)
from builders import make_incidente


# -----------------------------------------------------------------------------
# _score_criticidade
# -----------------------------------------------------------------------------
class TestScoreCriticidade:
    def test_range_sempre_entre_0_e_1(self):
        incs = [make_incidente()]
        score = _score_criticidade(incs, total_incs=1, cis_recorrentes=[])
        assert 0.0 <= score <= 1.0

    def test_total_incs_zero_retorna_zero(self):
        # Edge case: dataset vazio.
        score = _score_criticidade([], total_incs=0, cis_recorrentes=[])
        assert score == 0.0

    def test_tudo_critico_da_score_alto(self):
        # Volume 100%, indisponibilidade, sem contorno, CI recorrente → score próximo de 1.
        incs = [
            make_incidente(
                tem_contorno=False,
                descricao_curta="Servidor fora do ar",
                descricao="Não pinga, indisponível",
                servidor="srv-001",
            )
            for _ in range(10)
        ]
        score = _score_criticidade(incs, total_incs=10, cis_recorrentes=["srv-001"])
        assert score > 0.9  # quase máximo

    def test_baixa_criticidade(self):
        # 1 INC com contorno, sem termos críticos, sem CI recorrente.
        incs = [make_incidente(
            tem_contorno=True,
            descricao_curta="Lentidão pontual",
            descricao="Cliente reportou lentidão.",
        )]
        score = _score_criticidade(incs, total_incs=100, cis_recorrentes=[])
        assert score < 0.2  # baixo

    def test_recorrencia_apenas_contribui_010(self):
        # Apenas componente recorrência alto, outros baixos.
        incs = [make_incidente(tem_contorno=True, servidor="srv-recorrente")]
        score = _score_criticidade(incs, total_incs=100, cis_recorrentes=["srv-recorrente"])
        # PESO_RECORRENCIA_CI = 0.10, volume mínimo (1/100), outros zero.
        assert 0.10 < score < 0.15


# -----------------------------------------------------------------------------
# _score_ineficiencia
# -----------------------------------------------------------------------------
class TestScoreIneficiencia:
    def test_lista_vazia_retorna_zero(self):
        assert _score_ineficiencia([]) == 0.0

    def test_range_sempre_entre_0_e_1(self):
        incs = [make_incidente(qtd_updates=5)]
        score = _score_ineficiencia(incs)
        assert 0.0 <= score <= 1.0

    def test_muitas_atualizacoes_eleva_componente_volume(self):
        # Volume satura quando média >= LIMIAR_UPDATES_INEFICIENTE (8).
        incs = [make_incidente(qtd_updates=15) for _ in range(5)]
        score = _score_ineficiencia(incs)
        assert score > 0.5  # pelo menos componente volume alto

    def test_poucas_atualizacoes_score_baixo(self):
        # Poucas atualizações E espaçadas no tempo (24h) → baixo em ambos
        # componentes (volume baixo + velocidade baixa).
        now = datetime.now(timezone.utc)
        incs = [
            make_incidente(
                qtd_updates=1,
                abertura=now - timedelta(hours=24),
                atualizacao=now - timedelta(hours=1),
            )
            for _ in range(5)
        ]
        score = _score_ineficiencia(incs)
        assert score < 0.3

    def test_velocidade_alta_com_volume_alto(self):
        # INCs com muitos updates e janela curta (1h) → updates/hora alto.
        now = datetime.now(timezone.utc)
        incs = [
            make_incidente(
                qtd_updates=10,
                abertura=now - timedelta(hours=1),
                atualizacao=now,
            )
            for _ in range(5)
        ]
        score = _score_ineficiencia(incs)
        # Volume (10/8=1.25→satura em 1.0) + Velocidade (10/h / 2 = 5→satura em 1.0)
        assert score >= 0.99


# -----------------------------------------------------------------------------
# _termos_dominantes
# -----------------------------------------------------------------------------
class TestTermosDominantes:
    def test_retorna_top_n(self):
        incs = [
            make_incidente(descricao_curta="kernel panic", descricao="vps fora")
            for _ in range(3)
        ]
        termos = _termos_dominantes(incs, top_n=3)
        assert len(termos) <= 3

    def test_descarta_palavras_curtas(self):
        incs = [make_incidente(descricao_curta="a b c", descricao="kernel x y")]
        termos = _termos_dominantes(incs)
        # Tokens com len < 3 não entram.
        assert "kernel" in termos
        assert "a" not in termos
        assert "b" not in termos

    def test_descarta_digitos_puros(self):
        incs = [make_incidente(descricao_curta="2026", descricao="kernel panic")]
        termos = _termos_dominantes(incs)
        assert "2026" not in termos
        assert "kernel" in termos


# -----------------------------------------------------------------------------
# _fundir_singletons_por_ci — fusão de singletons por (produto, servidor)
# -----------------------------------------------------------------------------
class TestFusaoSingletonsPorCI:
    def test_funde_dois_singletons_mesmo_ci(self):
        # Dois singletons no mesmo (produto, servidor) → devem virar 1 cluster.
        incs = [
            make_incidente(inc_id="INC1", produto="Email", servidor="srv-01"),
            make_incidente(inc_id="INC2", produto="Email", servidor="srv-01"),
        ]
        labels_in = [-1, -1]
        labels_out = _fundir_singletons_por_ci(incs, labels_in)
        assert labels_out[0] == labels_out[1] != -1

    def test_nao_funde_quando_produto_difere(self):
        incs = [
            make_incidente(inc_id="INC1", produto="Email", servidor="srv-01"),
            make_incidente(inc_id="INC2", produto="VPS", servidor="srv-01"),
        ]
        labels_out = _fundir_singletons_por_ci(incs, [-1, -1])
        assert labels_out == [-1, -1]

    def test_nao_funde_quando_servidor_difere(self):
        incs = [
            make_incidente(inc_id="INC1", produto="Email", servidor="srv-01"),
            make_incidente(inc_id="INC2", produto="Email", servidor="srv-02"),
        ]
        labels_out = _fundir_singletons_por_ci(incs, [-1, -1])
        assert labels_out == [-1, -1]

    def test_nao_funde_singleton_sem_servidor(self):
        # Singleton sem CI completo permanece singleton (evita match espúrio).
        incs = [
            make_incidente(inc_id="INC1", produto="Email", servidor=""),
            make_incidente(inc_id="INC2", produto="Email", servidor=""),
        ]
        labels_out = _fundir_singletons_por_ci(incs, [-1, -1])
        assert labels_out == [-1, -1]

    def test_nao_toca_em_clusters_existentes(self):
        # INCs já agrupadas pelo DBSCAN não devem ter label trocado.
        incs = [
            make_incidente(inc_id="INC1", produto="Email", servidor="srv-01"),
            make_incidente(inc_id="INC2", produto="Email", servidor="srv-01"),
            make_incidente(inc_id="INC3", produto="VPS", servidor="srv-99"),
            make_incidente(inc_id="INC4", produto="VPS", servidor="srv-99"),
        ]
        # INC1+INC2 já estão no cluster 0; INC3+INC4 são singletons no mesmo CI.
        labels_in = [0, 0, -1, -1]
        labels_out = _fundir_singletons_por_ci(incs, labels_in)
        assert labels_out[0] == 0 and labels_out[1] == 0
        assert labels_out[2] == labels_out[3] != -1
        assert labels_out[2] != 0  # novo label, não reaproveita o 0

    def test_label_novo_nao_colide_com_dbscan(self):
        # Quando DBSCAN gera label 5 como máximo, fusão começa do 6.
        incs = [
            make_incidente(inc_id=f"INC{i}", produto="P", servidor="S")
            for i in range(2)
        ]
        labels_out = _fundir_singletons_por_ci(incs, [-1, -1])
        # Sem clusters DBSCAN: próximo label começa em 0.
        assert labels_out[0] == 0

        # Com DBSCAN tendo gerado até label 5, fusão deve começar em 6.
        incs2 = [
            make_incidente(inc_id="A", produto="P1", servidor="S1"),
            make_incidente(inc_id="B", produto="P1", servidor="S1"),
            make_incidente(inc_id="C", produto="P2", servidor="S2"),
            make_incidente(inc_id="D", produto="P2", servidor="S2"),
        ]
        labels_out2 = _fundir_singletons_por_ci(incs2, [5, 5, -1, -1])
        assert labels_out2[2] == labels_out2[3] == 6

    def test_grupo_de_tres_singletons_funde_todos(self):
        incs = [
            make_incidente(inc_id=f"INC{i}", produto="Email", servidor="srv-01")
            for i in range(3)
        ]
        labels_out = _fundir_singletons_por_ci(incs, [-1, -1, -1])
        assert len(set(labels_out)) == 1 and labels_out[0] != -1

    def test_grupos_distintos_recebem_labels_distintos(self):
        incs = [
            make_incidente(inc_id="A", produto="Email", servidor="srv-01"),
            make_incidente(inc_id="B", produto="Email", servidor="srv-01"),
            make_incidente(inc_id="C", produto="VPS", servidor="srv-99"),
            make_incidente(inc_id="D", produto="VPS", servidor="srv-99"),
        ]
        labels_out = _fundir_singletons_por_ci(incs, [-1, -1, -1, -1])
        assert labels_out[0] == labels_out[1]
        assert labels_out[2] == labels_out[3]
        assert labels_out[0] != labels_out[2]  # grupos distintos, labels distintos

    def test_lista_vazia(self):
        assert _fundir_singletons_por_ci([], []) == []