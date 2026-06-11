# =============================================================================
# Testes — customer_monitor (Saúde do Cliente)
# =============================================================================
# Foco: filtro de candidatos por volume + tipo_usuario. INCs de monitoração
# (tipo_usuario = "Integração") nunca devem contar pra Saúde do Cliente porque
# não têm cliente associado por design do ServiceNow.
# =============================================================================
from collections import Counter
from datetime import datetime
from typing import Dict, List, Sequence

import config
from customer_monitor import _clientes_com_volume, gerar_saude_clientes
from builders import make_incidente
from extractor import FonteIncidentes, FonteChamados
from models import Incidente, PRBExistente, InteracaoChamado


class TestClientesComVolume:
    def test_cliente_com_3_incs_nominais_vira_candidato(self):
        incs = [
            make_incidente(inc_id=f"INC{i}", login_cliente="acme", tipo_usuario="Nominal")
            for i in range(3)
        ]
        assert _clientes_com_volume(incs, limiar=3) == ["acme"]

    def test_cliente_com_2_incs_nao_atinge_limiar(self):
        incs = [
            make_incidente(inc_id=f"INC{i}", login_cliente="acme", tipo_usuario="Nominal")
            for i in range(2)
        ]
        assert _clientes_com_volume(incs, limiar=3) == []

    def test_inc_de_integracao_nao_conta(self):
        # 3 INCs Integração + 1 Nominal — cliente NÃO deve virar candidato
        # com limiar=3, porque só 1 INC Nominal conta.
        incs_integracao = [
            make_incidente(inc_id=f"INT{i}", login_cliente="acme", tipo_usuario="Integração")
            for i in range(3)
        ]
        incs_nominais = [
            make_incidente(inc_id="NOM1", login_cliente="acme", tipo_usuario="Nominal")
        ]
        assert _clientes_com_volume(incs_integracao + incs_nominais, limiar=3) == []

    def test_login_vazio_descartado_mesmo_sendo_nominal(self):
        # Regra antiga: login vazio nunca conta. Garantia de não regredir.
        incs = [
            make_incidente(inc_id=f"INC{i}", login_cliente="", tipo_usuario="Nominal")
            for i in range(5)
        ]
        assert _clientes_com_volume(incs, limiar=3) == []

    def test_dois_clientes_distintos(self):
        incs = (
            [make_incidente(inc_id=f"A{i}", login_cliente="cli1") for i in range(3)]
            + [make_incidente(inc_id=f"B{i}", login_cliente="cli2") for i in range(4)]
            + [make_incidente(inc_id="C0",   login_cliente="cli3")]  # só 1, não conta
        )
        result = sorted(_clientes_com_volume(incs, limiar=3))
        assert result == ["cli1", "cli2"]

    def test_tipos_usuario_aceitos_configuravel(self, monkeypatch):
        # Se config aceitar "Integração" também, INCs de monitoração contam.
        monkeypatch.setattr(config, "TIPOS_USUARIO_SAUDE_CLIENTE", ("Nominal", "Integração"))
        incs = [
            make_incidente(inc_id=f"I{i}", login_cliente="acme", tipo_usuario="Integração")
            for i in range(3)
        ]
        assert _clientes_com_volume(incs, limiar=3) == ["acme"]

    def test_lista_vazia_de_tipos_desativa_filtro(self, monkeypatch):
        # Tupla vazia = filtro desligado, todas as INCs contam.
        monkeypatch.setattr(config, "TIPOS_USUARIO_SAUDE_CLIENTE", ())
        incs = [
            make_incidente(inc_id=f"X{i}", login_cliente="acme", tipo_usuario="Qualquer")
            for i in range(3)
        ]
        assert _clientes_com_volume(incs, limiar=3) == ["acme"]

    def test_tipo_usuario_vazio_eh_descartado_quando_filtro_ativo(self):
        # tipo_usuario vazio (legado) não bate com "Nominal" → cliente descartado.
        incs = [
            make_incidente(inc_id=f"INC{i}", login_cliente="acme", tipo_usuario="")
            for i in range(3)
        ]
        assert _clientes_com_volume(incs, limiar=3) == []


# -----------------------------------------------------------------------------
# Fake mínimo de FonteIncidentes para testar gerar_saude_clientes
# -----------------------------------------------------------------------------
class _FakeFonteInc(FonteIncidentes):
    """Captura o argumento de contar_clientes_com_inc_recente pra inspeção."""
    def __init__(self, incs_recentes: List[Incidente], incs_historico: List[Incidente]) -> None:
        self.incs_recentes = incs_recentes
        self.incs_historico = incs_historico
        self.horas_recebidas: List[int] = []
        self.tipos_recebidos: List[Sequence[str]] = []

    def listar_incidentes_recentes(self, horas: int) -> List[Incidente]:
        return list(self.incs_recentes)

    def listar_prbs_abertos(self) -> List[PRBExistente]:
        return []

    def listar_incidentes_cliente(self, login_cliente: str, meses: int) -> List[Incidente]:
        return [i for i in self.incs_historico if i.login_cliente == login_cliente]

    def listar_prbs_para_validacao(self, dias: int) -> List[PRBExistente]:
        return []

    def listar_incidentes_por_produto_servidor(
        self, produto: str, servidor: str, desde: datetime,
        ate=None,
    ) -> List[Incidente]:
        return []

    def contar_clientes_com_inc_recente(
        self, horas: int, tipos_usuario: Sequence[str] = ()
    ) -> Dict[str, int]:
        self.horas_recebidas.append(horas)
        self.tipos_recebidos.append(tuple(tipos_usuario))
        tipos_set = set(tipos_usuario)
        counter: Counter = Counter()
        for inc in self.incs_recentes:
            if not inc.login_cliente:
                continue
            if tipos_set and inc.tipo_usuario not in tipos_set:
                continue
            counter[inc.login_cliente] += 1
        return dict(counter)

    def listar_incidentes_para_saude(
        self, logins_canonicos: Sequence[str], meses: int
    ) -> Dict[str, List[Incidente]]:
        # Reusa o histórico configurado e filtra por login canônico.
        return {
            login: [i for i in self.incs_historico if i.login_cliente == login]
            for login in logins_canonicos
        }

    def contar_incidentes_no_ci_periodo(
        self, produto, servidor, desde, ate
    ) -> Dict[str, int]:
        return {"qtd": 0, "clientes_unicos": 0, "categorias": 0}

    def listar_prbs_novos_no_ci_periodo(
        self, produto, servidor, desde, ignorar_prb_id=""
    ) -> List[str]:
        return []

    def listar_prbs_por_numero(
        self, numeros: Sequence[str]
    ) -> List[PRBExistente]:
        # Stub para satisfazer ABC FonteIncidentes (Plan 01-03 Phase 1).
        # Customer monitor não usa este método — retornar vazio é seguro.
        return []


class _FakeFonteChamados(FonteChamados):
    def listar_chamados_periodo(self, horas, produtos=None) -> List[InteracaoChamado]:
        return []

    def listar_chamados_cliente(self, login_cliente, meses) -> List[InteracaoChamado]:
        return []

    def listar_chamados_para_saude(
        self, logins_canonicos: Sequence[str], meses: int
    ) -> Dict[str, List[InteracaoChamado]]:
        return {login: [] for login in logins_canonicos}

    def contar_chamados_por_produto(self, produto, desde, ate) -> int:
        return 0

    def contar_chamados_vinculados(
        self, prb_id, incs_ids, desde, ate
    ) -> int:
        return 0

    def agrupar_chamados_vinculados_por_equipe(
        self, prb_id, incs_ids, desde, ate
    ) -> Dict[str, int]:
        return {}


class TestAmpliacaoDeJanela:
    def test_amplia_janela_quando_config_pede_mais_dias(self, monkeypatch):
        # Config pede 7 dias (168h) e a janela base é 24h → deve refazer query.
        monkeypatch.setattr(config, "JANELA_INC_HORAS", 24)
        monkeypatch.setattr(config, "JANELA_CANDIDATOS_SAUDE_DIAS", 7)

        # 3 INCs Nominais do mesmo cliente na janela ampliada — limiar atingido.
        amplas = [
            make_incidente(inc_id=f"AMP{i}", login_cliente="acme", tipo_usuario="Nominal")
            for i in range(3)
        ]
        fake_inc = _FakeFonteInc(incs_recentes=amplas, incs_historico=amplas)
        fake_ch = _FakeFonteChamados()

        # incidentes_janela (24h) vazia, mas a query ampliada vai trazer as 3.
        resultado = gerar_saude_clientes([], fake_inc, fake_ch)

        # Confirma chamada com janela ampla (7 * 24 = 168h)
        assert fake_inc.horas_recebidas == [168]
        # Confirma que cliente foi identificado
        assert len(resultado) == 1 and resultado[0].cliente_login == "acme"

    def test_nao_amplia_quando_config_menor_ou_igual(self, monkeypatch):
        # Se JANELA_CANDIDATOS_SAUDE_DIAS * 24 <= JANELA_INC_HORAS, usa a lista
        # recebida — não faz query extra.
        monkeypatch.setattr(config, "JANELA_INC_HORAS", 168)
        monkeypatch.setattr(config, "JANELA_CANDIDATOS_SAUDE_DIAS", 1)

        ja_carregadas = [
            make_incidente(inc_id=f"JC{i}", login_cliente="acme", tipo_usuario="Nominal")
            for i in range(3)
        ]
        fake_inc = _FakeFonteInc(incs_recentes=[], incs_historico=ja_carregadas)
        fake_ch = _FakeFonteChamados()

        resultado = gerar_saude_clientes(ja_carregadas, fake_inc, fake_ch)

        # Não deve ter chamado listar_incidentes_recentes
        assert fake_inc.horas_recebidas == []
        assert len(resultado) == 1 and resultado[0].cliente_login == "acme"

    def test_fallback_se_query_ampla_falha(self, monkeypatch):
        # Se a query ampliada lançar exceção, cai pra incidentes_janela.
        monkeypatch.setattr(config, "JANELA_INC_HORAS", 24)
        monkeypatch.setattr(config, "JANELA_CANDIDATOS_SAUDE_DIAS", 7)

        class _FonteQueExplode(_FakeFonteInc):
            def contar_clientes_com_inc_recente(self, horas, tipos_usuario=()):
                self.horas_recebidas.append(horas)
                raise RuntimeError("DW indisponível")

        ja_carregadas = [
            make_incidente(inc_id=f"FB{i}", login_cliente="acme", tipo_usuario="Nominal")
            for i in range(3)
        ]
        fake_inc = _FonteQueExplode(incs_recentes=[], incs_historico=ja_carregadas)
        fake_ch = _FakeFonteChamados()

        resultado = gerar_saude_clientes(ja_carregadas, fake_inc, fake_ch)

        # Tentou ampliar, mas usou o fallback — cliente ainda foi identificado.
        assert fake_inc.horas_recebidas == [168]
        assert len(resultado) == 1 and resultado[0].cliente_login == "acme"
