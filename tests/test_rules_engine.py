# =============================================================================
# Testes — matriz P1-P5 do rules_engine
# =============================================================================
# Foco: garantir que a matriz oficial está implementada corretamente.
# Hotspot CRÍTICO — bug aqui leva a alertas operacionais errados (P1 falso
# positivo inunda Slack; P1 falso negativo deixa crise passar batido).
# =============================================================================
import pytest

from rules_engine import prescrever
from builders import make_cluster, make_prb


# -----------------------------------------------------------------------------
# P1 — Crise
# -----------------------------------------------------------------------------
class TestP1Crise:
    def test_contratacao_indisponivel_sem_contorno_vira_p1(self):
        # Critério P1: contratação + indisponibilidade + sem contorno (todas)
        cluster = make_cluster(
            qtd_incs=3,
            todos_sem_contorno=True,
            descricao_curta="Checkout indisponível",
            descricao="Contratação fora do ar, carrinho não fecha. Indisponível total.",
            produto="CAL",
        )
        presc = prescrever(cluster, [])
        assert presc.prioridade_sugerida == "P1"
        assert presc.urgencia == "CRITICA"
        assert any("Contratação" in j or "contratação" in j for j in presc.justificativa)

    def test_risco_seguranca_isolado_vira_p1(self):
        # Apenas termo de segurança no texto basta para P1.
        cluster = make_cluster(
            qtd_incs=2,
            descricao_curta="Vazamento detectado",
            descricao="Possível vazamento de credenciais.",
        )
        presc = prescrever(cluster, [])
        assert presc.prioridade_sugerida == "P1"

    def test_palavra_fora_NAO_casa_falsamente_em_ra(self):
        # BUG REGRESSION: o termo 'ra' não pode casar em 'fora' (Reclame Aqui falso).
        # Veja GLOSSARIO.md — word boundary regex aplicado em _qualquer_termo_no_cluster.
        cluster = make_cluster(
            qtd_incs=6,
            todos_p3=True,
            todos_sem_contorno=True,
            descricao_curta="Servidor VPS fora",
            descricao="VPS não responde, kernel panic.",
        )
        presc = prescrever(cluster, [])
        # Não pode ser P1 só porque 'fora' contém 'ra ' antes do fix.
        # Deve ser P2 (gatilho proativo das 5 P3 promove P3→P2).
        assert presc.prioridade_sugerida != "P1"
        # Sem nenhuma justificativa mencionando Reclame Aqui
        assert not any("Reclame Aqui" in j for j in presc.justificativa)


# -----------------------------------------------------------------------------
# P2 — Alta
# -----------------------------------------------------------------------------
class TestP2Alta:
    def test_volume_sem_contorno_acima_de_5(self):
        cluster = make_cluster(
            qtd_incs=6,
            todos_p3=False,  # evita gatilho proativo, isolando P2 por volume
            todos_sem_contorno=True,
            descricao_curta="Servidor fora",
            descricao="VPS não responde.",
        )
        # Força prioridade fora de P3 para não disparar gatilho
        for inc in cluster.incidentes:
            inc.prioridade_atual = "P4"
        presc = prescrever(cluster, [])
        assert presc.prioridade_sugerida == "P2"
        assert presc.urgencia == "ALTA"

    def test_instalacao_servidor_dedicado_vira_p2(self):
        cluster = make_cluster(
            qtd_incs=2,
            todos_sem_contorno=True,
            nome="falha instalacao novo",
            produto="Servidor Dedicado",
            descricao_curta="Falha na instalação de novo servidor",
            descricao="Provisionamento travado.",
        )
        presc = prescrever(cluster, [])
        assert presc.prioridade_sugerida == "P2"
        assert any("instalação" in j.lower() for j in presc.justificativa)


# -----------------------------------------------------------------------------
# Gatilho proativo (5+ P3 idênticas)
# -----------------------------------------------------------------------------
class TestGatilhoProativo:
    def test_5_p3_identicas_promove_para_p2_via_cascata_p3(self):
        # Para o gatilho promover P3 → P2, a cascata precisa classificar como P3.
        # Critério P3: 20-100 INCs com contorno. Usamos 25 INCs com contorno.
        cluster = make_cluster(
            qtd_incs=25,  # faixa P3 (20-100)
            todos_p3=True,
            todos_sem_contorno=False,  # com contorno
        )
        # Tempo de contorno na faixa P3 (10-60 min)
        for inc in cluster.incidentes:
            inc.tempo_solucao_contorno_min = 30
        cluster.tempo_contorno_min_medio = 30
        presc = prescrever(cluster, [])
        # Cascata classifica P3 → gatilho proativo promove para P2.
        assert presc.prioridade_sugerida == "P2"
        assert any("gatilho proativo" in j.lower() for j in presc.justificativa)

    def test_5_p3_identicas_apenas_adiciona_justificativa_se_cluster_p4(self):
        # Caso onde a cascata classifica como P4 (poucas INCs com contorno).
        # O gatilho detecta as 5 P3 idênticas mas NÃO promove (só promove de P3).
        cluster = make_cluster(
            qtd_incs=5,
            todos_p3=True,
            todos_sem_contorno=False,  # com contorno
        )
        for inc in cluster.incidentes:
            inc.tempo_solucao_contorno_min = 5  # < 10 min → P4
        cluster.tempo_contorno_min_medio = 5
        presc = prescrever(cluster, [])
        # Cascata classifica P4. Gatilho não promove (só promove de P3).
        # Mas justificativa do gatilho deve aparecer.
        assert any("gatilho proativo" in j.lower() for j in presc.justificativa)

    def test_4_p3_NAO_dispara_gatilho(self):
        cluster = make_cluster(
            qtd_incs=4,
            todos_p3=True,
            todos_sem_contorno=False,
            descricao_curta="Lentidão certificado",
            descricao="Certificado expirado.",
        )
        presc = prescrever(cluster, [])
        # Sem gatilho, prioridade pode ser P3 ou P4 (depende de outras regras).
        assert not any("gatilho proativo" in j.lower() for j in presc.justificativa)


# -----------------------------------------------------------------------------
# Sugestão de repriorização
# -----------------------------------------------------------------------------
class TestRepriorizacao:
    def test_prb_p3_existente_com_cluster_p2_sugere_upgrade(self):
        cluster = make_cluster(
            qtd_incs=6,
            todos_p3=False,
            todos_sem_contorno=True,
            produto="VPS",
            servidor="vps-prod-01",
        )
        for inc in cluster.incidentes:
            inc.prioridade_atual = "P4"  # evita gatilho proativo
        prb = make_prb(prb_id="PRB0000123", produto="VPS", servidor="vps-prod-01", prioridade="P3")
        presc = prescrever(cluster, [prb])
        # Cluster é P2 (volume sem contorno) > PRB P3 → sugere upgrade.
        assert presc.acao == "REPRIORIZAR_PRB"
        assert presc.prb_existente is not None
        assert presc.prb_existente.prb_id == "PRB0000123"
        assert "P3 para P2" in (presc.sugestao_repriorizacao or "")

    def test_prb_ja_em_prioridade_correta_apenas_monitorar(self):
        cluster = make_cluster(
            qtd_incs=2,
            todos_sem_contorno=False,  # com contorno → cluster vai pra faixa baixa
            produto="VPS",
            servidor="vps-prod-01",
        )
        prb = make_prb(prb_id="PRB0000123", produto="VPS", servidor="vps-prod-01", prioridade="P3")
        presc = prescrever(cluster, [prb])
        # PRB já está em prioridade adequada — apenas monitorar.
        assert presc.acao == "MONITORAR"


# -----------------------------------------------------------------------------
# Ação final
# -----------------------------------------------------------------------------
class TestAcaoFinal:
    def test_p1_sem_prb_vira_abrir_prb(self):
        cluster = make_cluster(
            qtd_incs=3,
            todos_sem_contorno=True,
            descricao_curta="Checkout indisponível contratação",
            descricao="Indisponível total no checkout.",
            produto="CAL",
        )
        presc = prescrever(cluster, [])
        assert presc.acao == "ABRIR_PRB"

    def test_baixa_severidade_sem_prb_vira_nenhuma(self):
        cluster = make_cluster(
            qtd_incs=1,
            todos_p3=False,
            todos_sem_contorno=False,  # 1 INC com contorno → P4
        )
        for inc in cluster.incidentes:
            inc.prioridade_atual = "P4"
            inc.tempo_solucao_contorno_min = 5
        presc = prescrever(cluster, [])
        # P4 sem PRB sem gatilho → NENHUMA
        assert presc.acao == "NENHUMA"