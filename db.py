# =============================================================================
# Motor Prescritivo PRB — Helpers de acesso ao PostgreSQL
# =============================================================================
# Reproduz a interface usada pelo projeto irmão (locapredict) para reusar o
# mesmo config.ini compartilhado em projetos/config.ini. Mantemos o módulo
# auto-suficiente em vez de importar do locapredict — independência > DRY
# quando o overhead é trivial (60 linhas).
# =============================================================================
from __future__ import annotations

import configparser
import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, Iterator

log = logging.getLogger(__name__)


def resolve_config_path() -> str:
    """Descobre o caminho do config.ini.

    Ordem:
      1. Env var CAMINHO_ARQUIVO_CONFIGURACAO ou CONFIG_PATH (override explícito).
      2. ./config.ini, ../config.ini, ../../config.ini (caminhos relativos a este arquivo).
    """
    caminho = (
        os.environ.get("CAMINHO_ARQUIVO_CONFIGURACAO")
        or os.environ.get("CONFIG_PATH")
        or ""
    ).strip()
    if caminho and os.path.isfile(caminho):
        return caminho

    pasta_script = os.path.dirname(os.path.abspath(__file__))
    for rel in ("./config.ini", "../config.ini", "../../config.ini"):
        candidato = os.path.abspath(os.path.join(pasta_script, rel))
        if os.path.isfile(candidato):
            return candidato

    raise FileNotFoundError(
        "config.ini não encontrado. Defina CONFIG_PATH ou coloque o arquivo "
        "em ./, ../ ou ../../"
    )


def load_db_config(path: str | None = None) -> Dict[str, Any]:
    """Lê a seção [database] do config.ini e devolve kwargs prontos para psycopg2.

    Aceita chaves alternativas (server/host, database/dbname, uid/user, pwd/password)
    para compatibilidade com configs legados.
    """
    caminho = path or resolve_config_path()
    cfg = configparser.ConfigParser()
    cfg.read(caminho, encoding="utf-8")

    if "database" not in cfg:
        raise ValueError(f"O arquivo '{caminho}' não contém a seção [database]")

    parametros = {
        "host": (
            cfg.get("database", "server", fallback=None)
            or cfg.get("database", "host", fallback=None)
        ),
        "port": cfg.getint("database", "port", fallback=5432),
        "dbname": (
            cfg.get("database", "database", fallback=None)
            or cfg.get("database", "dbname", fallback=None)
        ),
        "user": (
            cfg.get("database", "uid", fallback=None)
            or cfg.get("database", "user", fallback=None)
        ),
        "password": (
            cfg.get("database", "pwd", fallback=None)
            or cfg.get("database", "password", fallback=None)
        ),
    }

    faltando = [k for k, v in parametros.items() if v is None]
    if faltando:
        raise ValueError(
            f"Faltam chaves em [database] do {caminho}: {', '.join(faltando)}"
        )

    return parametros


@contextmanager
def conectar() -> Iterator[Any]:
    """Context manager para conexão Postgres. Fecha sempre, mesmo com erro.

    Uso:
        with conectar() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    """
    try:
        import psycopg2
    except ImportError as exc:
        raise ImportError(
            "psycopg2 não instalado. Adicione `psycopg2-binary` ao requirements.txt"
        ) from exc

    params = load_db_config()
    conn = psycopg2.connect(**params)
    try:
        yield conn
    finally:
        conn.close()