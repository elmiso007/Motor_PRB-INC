# =============================================================================
# Motor Prescritivo PRB — Helpers de Timezone (UTC interno + fronteira BRT)
# =============================================================================
# Convenção do motor:
#   - INTERNAMENTE no Python: tudo em UTC tz-aware (datetime com tzinfo=UTC).
#   - NA FRONTEIRA com SQL: converter UTC para o fuso do banco (BRT) ao montar
#     queries, e fazer o caminho inverso ao parsear retornos.
#
# Por que UTC internamente: comparações e ordenações ficam sempre corretas,
# independente do fuso do servidor onde o motor roda.
# Por que BRT nas queries: as colunas `text` no banco vêm sem tzinfo e o ETL
# upstream usa fuso local (assunção registrada em config.TIMEZONE_BANCO).
# =============================================================================
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

import config


def agora_utc() -> datetime:
    """Substituto de `datetime.now()` — sempre devolve UTC tz-aware.

    Use em qualquer ponto do motor que antes usaria `datetime.now()`. A única
    exceção legítima é exibição puramente local (ex.: nome de arquivo de log).
    """
    return datetime.now(timezone.utc)


@lru_cache(maxsize=1)
def _zona_banco() -> ZoneInfo:
    """Retorna o ZoneInfo do banco. Cache: ZoneInfo é instanciado uma vez."""
    return ZoneInfo(config.TIMEZONE_BANCO)


def naive_banco_para_utc(dt_naive: datetime) -> datetime:
    """Trata um datetime naive como sendo no fuso do banco e converte para UTC.

    Uso típico: parsing de coluna `text` do banco que veio sem tzinfo.

    Se receber um datetime já tz-aware, devolve convertido para UTC sem
    quebrar (defensiva).
    """
    if dt_naive.tzinfo is not None:
        return dt_naive.astimezone(timezone.utc)
    return dt_naive.replace(tzinfo=_zona_banco()).astimezone(timezone.utc)


def utc_para_string_banco(dt_utc: datetime) -> str:
    """Converte UTC tz-aware para string no formato/fuso esperado pelo SQL.

    Uso típico: montar parâmetro `corte` para WHERE clause comparar com
    coluna `text` do banco.

    Se receber um datetime naive (sem tzinfo), assume que já está no fuso
    do banco (defensiva — não faz conversão dupla).
    """
    if dt_utc.tzinfo is None:
        return dt_utc.strftime("%Y-%m-%d %H:%M:%S")
    local = dt_utc.astimezone(_zona_banco())
    return local.strftime("%Y-%m-%d %H:%M:%S")