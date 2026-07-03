# =============================================================================
# Testes — parsers defensivos do extractor
# =============================================================================
# Foco: garantir que parsers (datas, prioridade, atualizações, contorno) lidam
# com dados malformados sem propagar exceção. Hotspot crítico — dados do banco
# vêm como text e podem ter qualquer formato.
# =============================================================================
from datetime import datetime, timezone

import pytest

from extractor import (
    _parse_datetime,
    _parse_prioridade,
    _contar_atualizacoes,
    _detectar_contorno,
    normalizar_login_cliente,
)


# -----------------------------------------------------------------------------
# _parse_datetime
# -----------------------------------------------------------------------------
class TestParseDatetime:
    def test_data_valida_ISO_retorna_utc_tz_aware(self):
        resultado = _parse_datetime("2026-05-27 14:30:00")
        assert resultado is not None
        assert resultado.tzinfo is not None
        assert resultado.tzinfo == timezone.utc

    def test_data_nula_retorna_none(self):
        assert _parse_datetime(None) is None

    def test_data_vazia_retorna_none(self):
        assert _parse_datetime("") is None

    def test_data_malformada_retorna_none(self):
        assert _parse_datetime("abc") is None
        assert _parse_datetime("25/05/2026") is None  # formato BR não aceito

    def test_data_com_whitespace_ignorado(self):
        resultado = _parse_datetime("  2026-05-27 14:30:00  ")
        assert resultado is not None

    def test_conversao_brt_para_utc(self):
        # 14:30 BRT = 17:30 UTC (BRT é UTC-3)
        resultado = _parse_datetime("2026-05-27 14:30:00")
        assert resultado.hour == 17
        assert resultado.minute == 30


# -----------------------------------------------------------------------------
# _parse_prioridade
# -----------------------------------------------------------------------------
class TestParsePrioridade:
    @pytest.mark.parametrize("entrada,esperado", [
        ("1", "P1"),
        ("2", "P2"),
        ("3", "P3"),
        ("4", "P4"),
        ("5", "P5"),
        ("1 - Crítica", "P1"),
        ("2 - Alta", "P2"),
        ("3 - Média", "P3"),
        ("4 - Baixa", "P4"),
    ])
    def test_numero_isolado(self, entrada, esperado):
        assert _parse_prioridade(entrada) == esperado

    @pytest.mark.parametrize("entrada", ["P1", "P2", "P3", "P4", "P5"])
    def test_ja_normalizada(self, entrada):
        assert _parse_prioridade(entrada) == entrada

    def test_nula_volta_p4(self):
        assert _parse_prioridade(None) == "P4"

    def test_vazia_volta_p4(self):
        assert _parse_prioridade("") == "P4"

    def test_invalida_volta_p4(self):
        assert _parse_prioridade("xyz") == "P4"
        assert _parse_prioridade("99") == "P99"  # numero invalido virou P99 (limitação consciente)


# -----------------------------------------------------------------------------
# _contar_atualizacoes
# -----------------------------------------------------------------------------
class TestContarAtualizacoes:
    def test_nulo_retorna_zero(self):
        assert _contar_atualizacoes(None) == 0

    def test_vazio_retorna_zero(self):
        assert _contar_atualizacoes("") == 0

    def test_conta_timestamps(self):
        texto = """
        2026-05-27 14:30:00 - João - Investiguei
        2026-05-27 15:00:00 - Maria - Resolvido
        """
        assert _contar_atualizacoes(texto) == 2

    def test_fallback_blocos_separados(self):
        texto = "Primeira anotação\n\nSegunda anotação\n\nTerceira anotação"
        assert _contar_atualizacoes(texto) == 3

    def test_um_unico_timestamp(self):
        assert _contar_atualizacoes("2026-05-27 14:30:00 - resolvido") == 1


# -----------------------------------------------------------------------------
# _detectar_contorno
# -----------------------------------------------------------------------------
class TestDetectarContorno:
    def test_termo_contorno_simples(self):
        assert _detectar_contorno("Há contorno aplicado") is True

    def test_workaround(self):
        assert _detectar_contorno("Workaround temporário") is True

    def test_sem_termo(self):
        assert _detectar_contorno("Servidor caiu, investigando") is False

    def test_multiplos_argumentos(self):
        # Função aceita *textos
        assert _detectar_contorno("normal", "tem contorno aqui") is True
        assert _detectar_contorno("normal", "também normal") is False

    def test_nulos_ignorados(self):
        assert _detectar_contorno(None, "tem workaround") is True
        assert _detectar_contorno(None, None) is False


# -----------------------------------------------------------------------------
# normalizar_login_cliente — espelho Python da expressão SQL do locapredict
# -----------------------------------------------------------------------------
class TestNormalizarLoginCliente:
    def test_vazio_retorna_vazio(self):
        assert normalizar_login_cliente("") == ""
        assert normalizar_login_cliente("   ") == ""

    def test_ficha_url_kinghost(self):
        # URL intranet KingHost com `ficha=NNN`
        url = "https://intranet.kinghost.com.br:56001/kinghost.cgi?ficha=424593"
        assert normalizar_login_cliente(url) == "424593"

    def test_cod_com_acento(self):
        assert normalizar_login_cliente("govonifelipe (Cód. 1100035861)") == "1100035861"

    def test_cod_sem_acento(self):
        assert normalizar_login_cliente("empotech (Cod. 1101046630)") == "1101046630"

    def test_apenas_digitos(self):
        assert normalizar_login_cliente("123456") == "123456"
        assert normalizar_login_cliente("  789  ") == "789"

    def test_url_generica_com_digitos_no_fim(self):
        assert normalizar_login_cliente("https://exemplo.com/path?id=42") == "42"

    def test_url_sem_match_retorna_vazio(self):
        # URL que não tem ficha= nem termina em =NNN
        assert normalizar_login_cliente("https://exemplo.com/sem-id") == ""

    def test_texto_simples_lowercase_alfanumerico(self):
        assert normalizar_login_cliente("AcmeCorp") == "acmecorp"
        assert normalizar_login_cliente("MZ-Viagens.Br") == "mzviagensbr"

    def test_dois_formatos_mesmo_cliente_normalizam_igual(self):
        # Cenário central: 'govonifelipe' aparece em 2 formatos no DW.
        # A normalização precisa unificar para evitar duplicata na Saúde do Cliente.
        a = normalizar_login_cliente("govonifelipe (Cód. 1100035861)")
        b = normalizar_login_cliente("1100035861")
        assert a == b == "1100035861"

    def test_login_texto_puro_vira_canonico(self):
        # `govonifelipe` sem Código — fica como `govonifelipe` (lowercase alfanum).
        # NÃO casa com `1100035861` — são identificadores diferentes do mesmo cliente,
        # mas o motor já reconhece a primeira forma como agrupador estável.
        assert normalizar_login_cliente("govonifelipe") == "govonifelipe"