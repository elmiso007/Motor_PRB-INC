# =============================================================================
# Motor Prescritivo PRB — Extractor (PostgreSQL + Dynamics)
# =============================================================================
# Camada de ingestão. Todas as fontes são Postgres no mesmo banco compartilhado
# com o projeto irmão locapredict:
#   - INCs:     lwsa.service_now_incidentes
#   - PRBs:     lwsa.service_now_problemas
#   - Chamados: dynamics.chamados (Locaweb) e kinghost.chamados (Kinghost),
#               roteados pela coluna `organizacao` da INC/PRB correspondente.
#
# Quando config.USAR_MOCKS=True, as classes Mock devolvem dados sintéticos
# coerentes com a matriz de regras — útil para validação local sem rede.
# =============================================================================
from __future__ import annotations

import logging
import random
import re
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

import config
import time_utils
from models import Incidente, InteracaoChamado, PRBExistente

log = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Interfaces (contratos)
# -----------------------------------------------------------------------------
class FonteIncidentes(ABC):
    @abstractmethod
    def listar_incidentes_recentes(self, horas: int) -> List[Incidente]: ...

    @abstractmethod
    def listar_prbs_abertos(self) -> List[PRBExistente]: ...

    @abstractmethod
    def listar_incidentes_cliente(
        self, login_cliente: str, meses: int
    ) -> List[Incidente]: ...

    @abstractmethod
    def listar_prbs_para_validacao(self, dias: int) -> List[PRBExistente]:
        """PRBs candidatos a validação retrospectiva: status `Aguardando Validação`
        ou encerrados (`Encerrado Automaticamente` / `Concluído`) com
        `data_encerrado >= NOW() - dias`. Devolvidos com `data_resolucao` populado.
        """
        ...

    @abstractmethod
    def listar_incidentes_por_produto_servidor(
        self, produto: str, servidor: str, desde: datetime,
        ate: Optional[datetime] = None,
    ) -> List[Incidente]:
        """INCs com data_abertura ∈ [desde, ate) no mesmo (produto, servidor).

        `ate` opcional — quando None, sem limite superior (default mantém
        compatibilidade com o uso original do ValidadorEntrega pra reincidência
        pós-resolução). Quando passado, restringe a janela bilateral — usado
        para levantar INCs PRÉ-resolução pra o cálculo de Δ chamados V3.
        """
        ...

    @abstractmethod
    def contar_clientes_com_inc_recente(
        self, horas: int, tipos_usuario: Sequence[str] = ()
    ) -> Dict[str, int]:
        """Conta INCs por login_cliente nas últimas N horas, opcionalmente
        filtrado por tipo_usuario. Retorna {login: qtd}.

        SQL agregado (GROUP BY) — muito mais leve que hidratar Incidente
        completo. Usado pelo customer_monitor para identificar candidatos a
        Saúde do Cliente em janelas longas (30+ dias) sem estourar memória.
        """
        ...

    @abstractmethod
    def listar_incidentes_para_saude(
        self, logins_canonicos: Sequence[str], meses: int
    ) -> Dict[str, List[Incidente]]:
        """Bulk + slim: 1 query única retornando INCs de TODOS os clientes
        candidatos, agrupadas por login canônico. Substitui N chamadas a
        listar_incidentes_cliente — paga 1 round-trip em vez de N.

        Slim: SELECT só com colunas usadas pela Saúde do Cliente (sem
        descrição longa, atualizações, fechamento). `tem_solucao_contorno`
        é pré-computado via regex no SQL.
        """
        ...

    @abstractmethod
    def contar_incidentes_no_ci_periodo(
        self, produto: str, servidor: str, desde: datetime, ate: datetime
    ) -> Dict[str, int]:
        """Volumetria pré-resolução do ValidadorEntrega.

        Conta INCs no mesmo (produto, servidor) dentro do período
        [desde, ate). Retorna agregado:
          - qtd            — total de INCs
          - clientes_unicos — COUNT DISTINCT login_cliente
          - categorias     — COUNT DISTINCT categoria

        Query agregada — não hidrata Incidentes (a Saúde do Cliente faz isso
        em outro lugar; aqui só precisamos das contagens).
        """
        ...

    @abstractmethod
    def listar_prbs_novos_no_ci_periodo(
        self, produto: str, servidor: str, desde: datetime, ignorar_prb_id: str = ""
    ) -> List[str]:
        """PRBs novos abertos no mesmo (produto, servidor) a partir de `desde`.

        Usado pelo ValidadorEntrega para detectar se um problema voltou em
        outra forma após o fix (PRB original resolvido, mas novo PRB criado).
        `ignorar_prb_id` exclui o PRB sendo validado (defensivo).

        Retorna lista de `numero` (ex.: ["PRB0012345", "PRB0012346"]).
        """
        ...

    @abstractmethod
    def listar_prbs_por_numero(self, numeros: Sequence[str]) -> List[PRBExistente]:
        """PRBs por número exato (sem janela temporal — D-03 Phase 1 Change Team).

        Aceita qualquer status. Devolve um PRBExistente por número encontrado
        no SNow. Números fornecidos que não baterem no SNow são silenciosamente
        omitidos — chamador deve comparar input vs output para detectar misses.
        """
        ...


class FonteChamados(ABC):
    @abstractmethod
    def listar_chamados_periodo(
        self, horas: int, produtos: Optional[List[str]] = None
    ) -> List[InteracaoChamado]: ...

    @abstractmethod
    def listar_chamados_cliente(
        self, login_cliente: str, meses: int
    ) -> List[InteracaoChamado]: ...

    @abstractmethod
    def listar_chamados_para_saude(
        self, logins_canonicos: Sequence[str], meses: int
    ) -> Dict[str, List[InteracaoChamado]]:
        """Bulk: 1 SELECT por organização (Locaweb + KingHost) retornando
        chamados de TODOS os candidatos, agrupados por login canônico.
        Substitui N×2 chamadas a listar_chamados_cliente.
        """
        ...

    @abstractmethod
    def contar_chamados_por_produto(
        self, produto: str, desde: datetime, ate: datetime
    ) -> int:
        """[DEPRECATED — substituído por contar_chamados_vinculados.]

        Delta de chamados pré/pós-resolução do ValidadorEntrega (V2).
        Match exato por `chamados.produto = prb.produto` — sinal fraco porque
        a taxonomia da `lw_octadesk.classificacoes.produto` raramente bate
        com `service_now_problems.produto`.
        """
        ...

    @abstractmethod
    def contar_chamados_vinculados(
        self, prb_id: str, incs_ids: Sequence[str],
        desde: datetime, ate: datetime,
    ) -> int:
        """Delta de chamados pré/pós com vínculo direto (V3).

        Conta chamados na janela `[desde, ate)` cujo `prb = prb_id` OU
        `inc IN incs_ids`. Resposta o pedido do coordenador (2026-06-02):
        usar as colunas que ligam o chamado ao PRB/INC em vez de match
        genérico por produto.

        Quando `incs_ids` é vazio, só filtra por `prb = prb_id`. Quando
        `prb_id` é vazio, só filtra por `inc IN (...)`. Ambos vazios = 0.
        """
        ...

    @abstractmethod
    def agrupar_chamados_vinculados_por_equipe(
        self, prb_id: str, incs_ids: Sequence[str],
        desde: datetime, ate: datetime,
    ) -> Dict[str, int]:
        """Agrupa chamados vinculados ao PRB/INCs por `equipeproprietaria`.

        Mesma cláusula de filtro de `contar_chamados_vinculados`
        (prb = prb_id OU inc IN incs_ids) na janela [desde, ate), com
        GROUP BY equipeproprietaria. Retorna {equipe: qtd}, ordenado por
        qtd desc. Equipes nulas/vazias caem em '<sem-equipe>'.

        Usado pelo ValidadorEntrega para identificar quais times internos
        da Locaweb foram impactados pelo problema do PRB (pré-resolução)
        e se eles deixaram de abrir chamados após o fix (pós-resolução).
        Resposta ao pedido do coordenador (2026-06-03).
        """
        ...


# -----------------------------------------------------------------------------
# Normalização de login_cliente
# -----------------------------------------------------------------------------
def sql_normalizar_login_cliente(coluna: str = "login_cliente") -> str:
    """Fragmento PostgreSQL que devolve um identificador canônico do cliente.

    Port literal do projeto irmão locapredict (guardiao_saude_cliente). Unifica
    formatos distintos que o ServiceNow/Dynamics/KingHost usam pra mesmo cliente:

      1. URL com `ficha=NNN` (KingHost intranet) → NNN
      2. `(Cód. NNN)` / `(Cod. NNN)` → NNN
      3. Valor só com dígitos → mantém
      4. Outra URL `http(s)://...=NNN` → NNN final
      5. Texto qualquer → lowercase + remove tudo que não é alfanumérico

    Usa substring(...FROM 'pat') (PG 7.x+) — compatível com PG 9.x do DW.
    """
    c = coluna
    return f"""NULLIF(
  TRIM(
    COALESCE(
      substring(TRIM({c}) FROM '(?i)ficha=(\\d+)'),
      substring(TRIM({c}) FROM '(?i)\\(\\s*C[oó]d\\.?\\s*(\\d+)\\s*\\)'),
      CASE WHEN TRIM({c}) ~ '^\\d+$' THEN TRIM({c}) END,
      CASE
        WHEN TRIM({c}) ~* '^https?://'
        THEN substring(TRIM({c}) FROM '.*=(\\d+)\\s*$')
      END,
      CASE
        WHEN TRIM({c}) !~* '^https?://'
        THEN NULLIF(lower(regexp_replace(TRIM({c}), '[^a-zA-Z0-9]', '', 'g')), '')
      END
    )
  ),
  ''
)"""


# Expressões pré-calculadas para uso direto em f-strings de SQL.
# _LOGIN_NORM_SNI: lwsa.service_now_incidentes (coluna `login_cliente` sem alias).
_LOGIN_NORM_SNI = sql_normalizar_login_cliente("login_cliente")


def _filtro_orgs_sni() -> tuple:
    """Cláusula AND + params para restringir INCs/PRBs do ServiceNow às orgs
    ativas (config.ORGANIZACOES_ATIVAS). Tupla vazia = sem filtro.

    Retorna (clausula_sql, params). A cláusula já inclui o "AND" inicial e
    placeholders %s — pronta pra ser concatenada num WHERE existente.
    """
    orgs = config.ORGANIZACOES_ATIVAS
    if not orgs:
        return "", ()
    placeholders = ",".join(["%s"] * len(orgs))
    return f"AND organizacao IN ({placeholders})", tuple(orgs)


def _registry_chamados_ativo() -> Dict[str, Any]:
    """Devolve `TABELAS_CHAMADOS_POR_ORGANIZACAO` filtrado por
    config.ORGANIZACOES_ATIVAS. Tupla vazia = retorna o registry inteiro.

    Usado por todos os métodos do ChamadosExtractor que iteram organizações.
    """
    orgs = config.ORGANIZACOES_ATIVAS
    if not orgs:
        return dict(config.TABELAS_CHAMADOS_POR_ORGANIZACAO)
    return {
        nome: spec
        for nome, spec in config.TABELAS_CHAMADOS_POR_ORGANIZACAO.items()
        if nome in orgs
    }


def _sql_cte_chamados_por_inc(janela_dias: int = 180) -> str:
    """CTE PostgreSQL que retorna {inc → logincliente} a partir de
    dynamics.chamados. Quando uma INC tem múltiplos chamados, escolhe o mais
    recente (DISTINCT ON com ORDER BY datacriacao DESC).

    Permite enriquecer INCs do SNow com login limpo do cliente real — vital
    quando service_now_incidentes.login_cliente vem vazio, com URL, ou com
    formato "(Cód. NNN)".

    `janela_dias` restringe a CTE a chamados criados nos últimos N dias.
    Sem o filtro a CTE varre a tabela inteira (~20k+ linhas) — com 180 dias
    cobre o histórico de 6 meses da Saúde do Cliente. Recomenda-se também
    criar índice `CREATE INDEX ON dynamics.chamados (inc) WHERE inc IS NOT NULL`
    via DBA pra eliminar de vez o gargalo.
    """
    return f"""chamados_por_inc AS (
        SELECT DISTINCT ON (inc) inc, logincliente
        FROM dynamics.chamados
        WHERE inc IS NOT NULL AND TRIM(inc) <> ''
          AND TRIM(COALESCE(logincliente, '')) <> ''
          AND datacriacao >= NOW() - INTERVAL '{int(janela_dias)} days'
        ORDER BY inc, datacriacao DESC
    )"""


def _filtro_padroes_login_excluidos(coluna: str = "login_cliente") -> tuple:
    """Cláusula AND + params para descartar rows cujo `login_cliente` contém
    padrões blacklist (case-insensitive). Tupla vazia = sem filtro.

    Complementa o filtro por organização: cobre o caso de INCs do DW
    classificadas como Locaweb mas com login que indica outra origem
    (ex.: URLs `intranet.kinghost.com.br/.../ficha=NNN`).
    """
    padroes = config.LOGIN_CLIENTE_PADROES_EXCLUIDOS
    if not padroes:
        return "", ()
    clausulas = " ".join([f"AND {coluna} NOT ILIKE %s" for _ in padroes])
    params = tuple(f"%{p}%" for p in padroes)
    return clausulas, params


# Regexes pré-compilados — equivalente Python da expressão SQL acima.
_RX_FICHA = re.compile(r"ficha=(\d+)", re.IGNORECASE)
_RX_COD = re.compile(r"\(\s*C[oó]d\.?\s*(\d+)\s*\)", re.IGNORECASE)
_RX_DIGITOS = re.compile(r"^\d+$")
_RX_URL_PREFIXO = re.compile(r"^https?://", re.IGNORECASE)
_RX_URL_DIGITOS_FIM = re.compile(r".*=(\d+)\s*$")
_RX_NAO_ALFANUM = re.compile(r"[^a-zA-Z0-9]")


def normalizar_login_cliente(valor: str) -> str:
    """Versão Python da `sql_normalizar_login_cliente` — mesma ordem de precedência.

    Usado no mock e em customer_monitor para que a contagem em Python case
    com o GROUP BY do banco. Retorna "" se entrada inválida/vazia.
    """
    if not valor:
        return ""
    s = valor.strip()
    if not s:
        return ""
    m = _RX_FICHA.search(s)
    if m:
        return m.group(1)
    m = _RX_COD.search(s)
    if m:
        return m.group(1)
    if _RX_DIGITOS.match(s):
        return s
    if _RX_URL_PREFIXO.match(s):
        m = _RX_URL_DIGITOS_FIM.match(s)
        return m.group(1) if m else ""
    return _RX_NAO_ALFANUM.sub("", s).lower()


# -----------------------------------------------------------------------------
# Helpers de parsing (colunas vêm como text no banco)
# -----------------------------------------------------------------------------
_REGEX_TIMESTAMP_WORKNOTE = re.compile(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}")

_TERMOS_INDICADORES_CONTORNO = [
    "contorno", "workaround", "solucao alternativa", "solução alternativa",
    "paliativo", "temporariamente", "temporário", "temporario",
]


def _parse_datetime(valor: Any) -> Optional[datetime]:
    """Aceita string ISO 8601 ou objeto datetime (psycopg2 devolve datetime
    direto em colunas timestamp). Devolve UTC tz-aware.

    Strings/datetimes sem timezone são assumidos no fuso config.TIMEZONE_BANCO
    (BRT por convenção Locaweb) e convertidos para UTC.
    Retorna None se inválido/vazio.
    """
    if valor is None or valor == "":
        return None
    # psycopg2 devolve datetime direto para colunas timestamp; trata antes da string.
    if isinstance(valor, datetime):
        if valor.tzinfo is None:
            return time_utils.naive_banco_para_utc(valor)
        return valor.astimezone(timezone.utc)
    try:
        dt = datetime.strptime(valor.strip(), "%Y-%m-%d %H:%M:%S")
        return time_utils.naive_banco_para_utc(dt)
    except (ValueError, AttributeError):
        log.debug("Data inválida ignorada: %r", valor)
        return None


def _parse_prioridade(valor: Optional[str]) -> str:
    """Aceita '1'..'5' e devolve 'P1'..'P5'. Default 'P4' (baixa) se inválido."""
    if not valor:
        return "P4"
    valor_strip = valor.strip()
    if not valor_strip:
        return "P4"
    if valor_strip.startswith("P"):
        return valor_strip
    primeiro_digito = ""
    for caractere in valor_strip:
        if caractere.isdigit():
            primeiro_digito = caractere
            break
        if primeiro_digito:
            break
    try:
        if primeiro_digito:
            return f"P{int(primeiro_digito)}"
        return f"P{int(valor_strip)}"
    except (ValueError, TypeError):
        log.debug("Prioridade inválida tratada como P4: %r", valor)
        return "P4"


def _contar_atualizacoes(valor: Any) -> int:
    """Conta work_notes. Aceita int (coluna numérica já agregada) ou string
    (texto livre com timestamps de worknotes — usado no mock e em legados).

    Fallback para string: se não achar timestamp, conta blocos separados por \\n\\n.
    """
    if valor is None:
        return 0
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float):
        return int(valor)
    texto = str(valor)
    if not texto.strip():
        return 0
    matches = _REGEX_TIMESTAMP_WORKNOTE.findall(texto)
    if matches:
        return len(matches)
    blocos = [b for b in texto.split("\n\n") if b.strip()]
    return len(blocos)


def _detectar_contorno(*textos: Optional[str]) -> bool:
    """Heurística textual: presença de termos de contorno em qualquer um dos textos."""
    concat = " ".join(t for t in textos if t).lower()
    return any(termo in concat for termo in _TERMOS_INDICADORES_CONTORNO)


# -----------------------------------------------------------------------------
# Implementação real — PostgreSQL (data warehouse lwsa)
# -----------------------------------------------------------------------------
class ServiceNowExtractor(FonteIncidentes):
    """Lê INCs e PRBs do data warehouse Postgres (schema lwsa).

    Conexão é resolvida em db.conectar() lendo config.ini compartilhado.
    """

    def _row_para_incidente(self, row: Dict[str, Any]) -> Incidente:
        """Converte uma linha de lwsa.rawdata_service_now_incidentes em Incidente."""
        abertura = _parse_datetime(row.get("data_abertura")) or time_utils.agora_utc()
        atualizacao = (
            _parse_datetime(row.get("data_resolvido"))
            or _parse_datetime(row.get("data_encerrado"))
            or abertura
        )
        return Incidente(
            inc_id=row.get("numero") or "",
            descricao_curta=row.get("descricao_curta") or "",
            descricao=row.get("descricao") or "",
            servidor=row.get("servidor") or "",
            produto=row.get("produto") or "",
            login_cliente=row.get("login_cliente") or "",
            prioridade_atual=_parse_prioridade(row.get("prioridade")),
            abertura=abertura,
            atualizacao=atualizacao,
            qtd_atualizacoes=_contar_atualizacoes(row.get("atualizacoes")),
            tem_solucao_contorno=_detectar_contorno(
                row.get("descricao"), row.get("fechamento")
            ),
            organizacao=row.get("organizacao") or "",
            categoria=row.get("categoria") or "",
            subcategoria=row.get("subcategoria") or "",
            grupo_designado=row.get("grupo_designado") or "",
            status=row.get("status") or "",
            fechamento=row.get("fechamento") or "",
            tipo_usuario=row.get("tipo_usuario") or "",
        )

    def _row_para_prb(self, row: Dict[str, Any]) -> PRBExistente:
        """Converte uma linha de lwsa.rawdata_service_now_problems em PRBExistente."""
        return PRBExistente(
            prb_id=row.get("numero") or "",
            descricao_curta=row.get("descricao_curta") or "",
            descricao=row.get("descricao") or "",
            produto=row.get("produto") or "",
            servidor=row.get("servidor") or "",
            prioridade_atual=_parse_prioridade(row.get("prioridade")),
            status=row.get("status") or "",
            solucao_alternativa=row.get("solucao_alternativa") or "",
            categoria=row.get("categoria") or "",
            subcategoria=row.get("subcategoria") or "",
            grupo_designado=row.get("grupo_designado") or "",
            qtd_atualizacoes=_contar_atualizacoes(row.get("atualizacoes")),
            aberto_em=_parse_datetime(row.get("data_abertura")),
            data_resolucao=_parse_datetime(row.get("data_encerrado")),
        )

    def _query(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Executa SELECT e devolve list[dict] (column_name → valor)."""
        from db import conectar
        with conectar() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                colunas = [desc[0] for desc in cur.description]
                return [dict(zip(colunas, row)) for row in cur.fetchall()]

    # --- INCs ---------------------------------------------------------------
    def listar_incidentes_recentes(self, horas: int) -> List[Incidente]:
        """INCs abertas nas últimas N horas (sem filtro de status — fluxo, não estado)."""
        corte = time_utils.agora_utc() - timedelta(hours=horas)
        filtro_org, params_org = _filtro_orgs_sni()
        sql = f"""
            SELECT numero, organizacao, descricao_curta, descricao, fechamento,
                   prioridade, produto, data_abertura, data_resolvido, data_encerrado,
                   grupo_designado, status,
                   {_LOGIN_NORM_SNI} AS login_cliente,
                   categoria, subcategoria,
                   atualizacoes, servidor, tipo_usuario
            FROM {config.SCHEMA_BANCO}.{config.TABELA_INCIDENTES}
            WHERE data_abertura >= %s
              {filtro_org}
        """
        params = (time_utils.utc_para_string_banco(corte),) + params_org
        rows = self._query(sql, params)
        return [self._row_para_incidente(r) for r in rows]

    def listar_incidentes_cliente(
        self, login_cliente: str, meses: int
    ) -> List[Incidente]:
        """Histórico de INCs de um cliente nos últimos N meses (Saúde do Cliente).

        O `login_cliente` recebido aqui é o canônico (normalizado upstream em
        contar_clientes_com_inc_recente). Compara contra a expressão normalizada
        da coluna para casar todos os formatos: 'username', 'username (Cód. N)',
        'ficha=N', '12345', etc.
        """
        corte = time_utils.agora_utc() - timedelta(days=30 * meses)
        filtro_org, params_org = _filtro_orgs_sni()
        sql = f"""
            SELECT numero, organizacao, descricao_curta, descricao, fechamento,
                   prioridade, produto, data_abertura, data_resolvido, data_encerrado,
                   grupo_designado, status,
                   {_LOGIN_NORM_SNI} AS login_cliente,
                   categoria, subcategoria,
                   atualizacoes, servidor, tipo_usuario
            FROM {config.SCHEMA_BANCO}.{config.TABELA_INCIDENTES}
            WHERE {_LOGIN_NORM_SNI} = %s
              AND data_abertura >= %s
              {filtro_org}
        """
        params = (login_cliente, time_utils.utc_para_string_banco(corte)) + params_org
        rows = self._query(sql, params)
        return [self._row_para_incidente(r) for r in rows]

    # --- PRBs ---------------------------------------------------------------
    def listar_prbs_abertos(self) -> List[PRBExistente]:
        """PRBs com status ativo (config.STATUS_PRB_ATIVOS)."""
        placeholders = ",".join(["%s"] * len(config.STATUS_PRB_ATIVOS))
        filtro_org, params_org = _filtro_orgs_sni()
        sql = f"""
            SELECT numero, descricao_curta, descricao, produto, servidor,
                   prioridade, status, solucao_alternativa, categoria, subcategoria,
                   grupo_designado, atualizacoes, data_abertura, data_encerrado
            FROM {config.SCHEMA_BANCO}.{config.TABELA_PROBLEMAS}
            WHERE status IN ({placeholders})
              {filtro_org}
        """
        rows = self._query(sql, tuple(config.STATUS_PRB_ATIVOS) + params_org)
        return [self._row_para_prb(r) for r in rows]

    def listar_prbs_para_validacao(self, dias: int) -> List[PRBExistente]:
        """PRBs candidatos a validação retrospectiva.

        Critério: status em STATUS_PRB_ENCERRADOS, data_encerrado NÃO nula e
        dentro da janela de N dias. Status como 'Aguardando Validação da
        Resolução' não entram aqui porque no DW eles sempre têm data_encerrado
        NULL — sem data confiável, não tem como avaliar dias_pos_resolucao.
        """
        corte = time_utils.agora_utc() - timedelta(days=dias)
        placeholders = ",".join(["%s"] * len(config.STATUS_PRB_ENCERRADOS))
        filtro_org, params_org = _filtro_orgs_sni()
        sql = f"""
            SELECT numero, descricao_curta, descricao, produto, servidor,
                   prioridade, status, solucao_alternativa, categoria, subcategoria,
                   grupo_designado, atualizacoes, data_abertura, data_encerrado
            FROM {config.SCHEMA_BANCO}.{config.TABELA_PROBLEMAS}
            WHERE status IN ({placeholders})
              AND data_encerrado IS NOT NULL
              AND data_encerrado >= %s
              {filtro_org}
        """
        params = tuple(config.STATUS_PRB_ENCERRADOS) + (
            time_utils.utc_para_string_banco(corte),
        ) + params_org
        rows = self._query(sql, params)
        return [self._row_para_prb(r) for r in rows]

    def listar_prbs_por_numero(self, numeros: Sequence[str]) -> List[PRBExistente]:
        """Implementação real — sem janela, sem filtro de status (D-03).

        Aplica filtro de organização (_filtro_orgs_sni) para coerência com o
        resto do extractor. Edge case: lista vazia → retorna [].
        Não levanta exception em PRBs ausentes no SNow — silenciosamente omite.
        """
        if not numeros:
            return []
        placeholders = ",".join(["%s"] * len(numeros))
        filtro_org, params_org = _filtro_orgs_sni()
        sql = f"""
            SELECT numero, descricao_curta, descricao, produto, servidor,
                   prioridade, status, solucao_alternativa, categoria, subcategoria,
                   grupo_designado, atualizacoes, data_abertura, data_encerrado
            FROM {config.SCHEMA_BANCO}.{config.TABELA_PROBLEMAS}
            WHERE numero IN ({placeholders})
              {filtro_org}
        """
        rows = self._query(sql, tuple(numeros) + params_org)
        return [self._row_para_prb(r) for r in rows]

    def listar_prbs_novos_no_ci_periodo(
        self, produto: str, servidor: str, desde: datetime, ignorar_prb_id: str = ""
    ) -> List[str]:
        """PRBs com data_abertura >= `desde` no mesmo (produto, servidor)."""
        filtro_org, params_org = _filtro_orgs_sni()
        sql = f"""
            SELECT numero
            FROM {config.SCHEMA_BANCO}.{config.TABELA_PROBLEMAS}
            WHERE produto = %s
              AND servidor = %s
              AND data_abertura >= %s
              AND numero <> %s
              {filtro_org}
            ORDER BY data_abertura DESC
        """
        params = (
            produto, servidor,
            time_utils.utc_para_string_banco(desde),
            ignorar_prb_id or "",
        ) + params_org
        rows = self._query(sql, params)
        return [r["numero"] for r in rows if r.get("numero")]

    def listar_incidentes_por_produto_servidor(
        self, produto: str, servidor: str, desde: datetime,
        ate: Optional[datetime] = None,
    ) -> List[Incidente]:
        """INCs com data_abertura ∈ [desde, ate) no mesmo (produto, servidor).

        Match exato (não fuzzy) — mesma estratégia que rules_engine usa pra
        casar cluster com PRB existente. `ate=None` mantém compat (sem limite
        superior). `ate` é exclusivo (`<`) para evitar overlap pré/pós no
        instante exato de `data_encerrado`.
        """
        filtro_org, params_org = _filtro_orgs_sni()
        clausula_ate = ""
        params_ate: tuple = ()
        if ate is not None:
            clausula_ate = "AND data_abertura < %s"
            params_ate = (time_utils.utc_para_string_banco(ate),)
        sql = f"""
            SELECT numero, organizacao, descricao_curta, descricao, fechamento,
                   prioridade, produto, data_abertura, data_resolvido, data_encerrado,
                   grupo_designado, status,
                   {_LOGIN_NORM_SNI} AS login_cliente,
                   categoria, subcategoria,
                   atualizacoes, servidor, tipo_usuario
            FROM {config.SCHEMA_BANCO}.{config.TABELA_INCIDENTES}
            WHERE produto = %s
              AND servidor = %s
              AND data_abertura >= %s
              {clausula_ate}
              {filtro_org}
        """
        params = (
            (produto, servidor, time_utils.utc_para_string_banco(desde))
            + params_ate
            + params_org
        )
        rows = self._query(sql, params)
        return [self._row_para_incidente(r) for r in rows]

    def contar_clientes_com_inc_recente(
        self, horas: int, tipos_usuario: Sequence[str] = ()
    ) -> Dict[str, int]:
        """SQL agregado normalizado: SELECT login_canonico, COUNT(*) GROUP BY login_canonico.

        Login efetivo = COALESCE(dynamics.chamados.logincliente, sni.login_cliente).
        Quando a INC tem chamado correspondente em dynamics.chamados.inc, usa o
        logincliente de lá (limpo, sem URL/Cód./vazio). Cai pro SNow quando não
        houver cruzamento. Depois aplica `sql_normalizar_login_cliente` pra
        canonizar.
        """
        corte = time_utils.agora_utc() - timedelta(hours=horas)
        params: List[Any] = [time_utils.utc_para_string_banco(corte)]
        where_tipo = ""
        if tipos_usuario:
            placeholders = ",".join(["%s"] * len(tipos_usuario))
            where_tipo = f"AND sni.tipo_usuario IN ({placeholders})"
            params.extend(tipos_usuario)
        # Filtros org/login operam sobre as colunas do SNow (raw) — antes do COALESCE.
        # KingHost na URL do login_cliente continua sendo excluído.
        filtro_org_raw, params_org = _filtro_orgs_sni()
        params.extend(params_org)
        filtro_org = filtro_org_raw.replace("organizacao", "sni.organizacao")
        filtro_login_raw, params_login = _filtro_padroes_login_excluidos("sni.login_cliente")
        params.extend(params_login)
        # E também o login efetivo (caso dynamics traga um login KingHost — paranóia).
        filtro_login_efetivo, params_login_efetivo = _filtro_padroes_login_excluidos("login_efetivo")
        params.extend(params_login_efetivo)
        login_norm_efetivo = sql_normalizar_login_cliente("login_efetivo")
        # CTE cobre a mesma janela que estamos buscando (com folga de 7 dias
        # pra capturar chamados criados um pouco antes da abertura da INC).
        janela_cte_dias = max(int(horas / 24) + 7, 14)
        sql = f"""
            WITH {_sql_cte_chamados_por_inc(janela_cte_dias)},
            enriquecido AS (
                SELECT
                    COALESCE(
                        NULLIF(TRIM(c.logincliente), ''),
                        sni.login_cliente
                    ) AS login_efetivo
                FROM {config.SCHEMA_BANCO}.{config.TABELA_INCIDENTES} sni
                LEFT JOIN chamados_por_inc c ON c.inc = sni.numero
                WHERE sni.data_abertura >= %s
                  AND sni.login_cliente IS NOT NULL
                  AND TRIM(sni.login_cliente) <> ''
                  {where_tipo}
                  {filtro_org}
                  {filtro_login_raw}
            )
            SELECT {login_norm_efetivo} AS login_canonico, COUNT(*) AS qtd
            FROM enriquecido
            WHERE login_efetivo IS NOT NULL
              AND TRIM(login_efetivo) <> ''
              {filtro_login_efetivo}
            GROUP BY {login_norm_efetivo}
            HAVING {login_norm_efetivo} IS NOT NULL AND {login_norm_efetivo} <> ''
        """
        rows = self._query(sql, tuple(params))
        return {r["login_canonico"]: int(r["qtd"]) for r in rows}

    def contar_incidentes_no_ci_periodo(
        self, produto: str, servidor: str, desde: datetime, ate: datetime
    ) -> Dict[str, int]:
        """SQL agregado: 3 contagens distintas numa única query."""
        filtro_org, params_org = _filtro_orgs_sni()
        sql = f"""
            SELECT
                COUNT(*) AS qtd,
                COUNT(DISTINCT NULLIF(TRIM(COALESCE(login_cliente, '')), '')) AS clientes_unicos,
                COUNT(DISTINCT NULLIF(TRIM(COALESCE(categoria, '')), '')) AS categorias
            FROM {config.SCHEMA_BANCO}.{config.TABELA_INCIDENTES}
            WHERE produto = %s
              AND servidor = %s
              AND data_abertura >= %s
              AND data_abertura < %s
              {filtro_org}
        """
        params = (
            produto, servidor,
            time_utils.utc_para_string_banco(desde),
            time_utils.utc_para_string_banco(ate),
        ) + params_org
        rows = self._query(sql, params)
        if not rows:
            return {"qtd": 0, "clientes_unicos": 0, "categorias": 0}
        r = rows[0]
        return {
            "qtd": int(r.get("qtd") or 0),
            "clientes_unicos": int(r.get("clientes_unicos") or 0),
            "categorias": int(r.get("categorias") or 0),
        }

    def listar_incidentes_para_saude(
        self, logins_canonicos: Sequence[str], meses: int
    ) -> Dict[str, List[Incidente]]:
        """Bulk + slim para Saúde do Cliente.

        Uma única query traz histórico de TODOS os logins canônicos. Colunas
        reduzidas — só o que customer_monitor usa pra montar a linha do tempo
        e calcular severidade. `tem_solucao_contorno` é pré-computado no SQL
        com a mesma lista de termos da função Python _detectar_contorno().
        """
        if not logins_canonicos:
            return {}

        corte = time_utils.agora_utc() - timedelta(days=30 * meses)
        placeholders = ",".join(["%s"] * len(logins_canonicos))
        # Regex equivalente a `_TERMOS_INDICADORES_CONTORNO` em Python. ~* é
        # POSIX case-insensitive — cobre acento e variações comuns.
        regex_contorno = r"contorno|workaround|solu[cç][aã]o alternativa|paliativo|tempor[aá]ri[oa]|tempor[aá]riamente"
        filtro_org_raw, params_org = _filtro_orgs_sni()
        filtro_org = filtro_org_raw.replace("organizacao", "sni.organizacao")
        # Mesmo login efetivo da contagem de candidatos — sem isso o WHERE
        # comparando login_canonico contra IN (...) não casaria as INCs cujo
        # login canônico veio de dynamics.chamados.logincliente.
        login_norm_efetivo = sql_normalizar_login_cliente(
            "COALESCE(NULLIF(TRIM(c.logincliente), ''), sni.login_cliente)"
        )
        # CTE cobre a janela de histórico + folga de 7d.
        janela_cte_dias = 30 * meses + 7
        sql = f"""
            WITH {_sql_cte_chamados_por_inc(janela_cte_dias)}
            SELECT
                sni.numero,
                sni.descricao_curta,
                sni.prioridade,
                sni.produto,
                sni.data_abertura,
                sni.servidor,
                {login_norm_efetivo} AS login_cliente,
                (COALESCE(sni.descricao, '') || ' ' || COALESCE(sni.fechamento, ''))
                    ~* '{regex_contorno}' AS tem_contorno
            FROM {config.SCHEMA_BANCO}.{config.TABELA_INCIDENTES} sni
            LEFT JOIN chamados_por_inc c ON c.inc = sni.numero
            WHERE {login_norm_efetivo} IN ({placeholders})
              AND sni.data_abertura >= %s
              {filtro_org}
        """
        params = tuple(logins_canonicos) + (time_utils.utc_para_string_banco(corte),) + params_org
        rows = self._query(sql, params)

        agrupado: Dict[str, List[Incidente]] = {login: [] for login in logins_canonicos}
        for r in rows:
            login = r.get("login_cliente") or ""
            if login not in agrupado:
                continue
            abertura = _parse_datetime(r.get("data_abertura")) or time_utils.agora_utc()
            agrupado[login].append(Incidente(
                inc_id=r.get("numero") or "",
                descricao_curta=r.get("descricao_curta") or "",
                descricao="",
                servidor=r.get("servidor") or "",
                produto=r.get("produto") or "",
                login_cliente=login,
                prioridade_atual=_parse_prioridade(r.get("prioridade")),
                abertura=abertura,
                atualizacao=abertura,  # slim: não puxa data_resolvido/encerrado
                qtd_atualizacoes=0,
                tem_solucao_contorno=bool(r.get("tem_contorno")),
            ))
        return agrupado


def _montar_sql_chamados(spec: Dict[str, Any], where_clause: str) -> str:
    """Constrói SQL declarativamente a partir do spec do registry.

    spec: entrada de config.TABELAS_CHAMADOS_POR_ORGANIZACAO[organizacao].
    where_clause: cláusula SQL completa (sem a palavra WHERE) com placeholders %s.

    SEGURANÇA: schema/tabela/alias/colunas vêm SÓ do config (whitelist). O
    `where_clause` PODE conter texto livre — chamadores DEVEM usar placeholders
    %s para qualquer valor variável, NUNCA concatenar string.
    """
    cols = spec["colunas"]
    select_lines = [f"{expr} AS {chave}" for chave, expr in cols.items()]
    select_sql = ",\n    ".join(select_lines)

    schema = spec["schema"]
    tabela = spec["tabela"]
    alias = spec.get("alias")
    from_sql = f"{schema}.{tabela}"
    if alias:
        from_sql = f"{from_sql} {alias}"

    join_sql = ""
    join = spec.get("join")
    if join:
        join_schema = join["schema"]
        join_tabela = join["tabela"]
        join_alias = join["alias"]
        chaves = join["chaves"]
        conds = " AND ".join(
            f"{alias}.{k} = {join_alias}.{k}" for k in chaves
        )
        join_sql = (
            f"\nLEFT JOIN {join_schema}.{join_tabela} {join_alias}\n"
            f"    ON {conds}"
        )

    return (
        f"SELECT\n    {select_sql}\n"
        f"FROM {from_sql}"
        f"{join_sql}\n"
        f"WHERE {where_clause}"
    )


def _row_para_interacao_chamado(
    row: Dict[str, Any], organizacao: str
) -> InteracaoChamado:
    """Converte row do banco em InteracaoChamado (independente da organização —
    os nomes de campo já vêm normalizados pelo `_montar_sql_chamados` via AS).
    """
    data = _parse_datetime(row.get("data")) or time_utils.agora_utc()
    qtd = row.get("qtd_interacoes_cliente")
    try:
        qtd_int = int(qtd) if qtd is not None else 0
    except (ValueError, TypeError):
        qtd_int = 0

    return InteracaoChamado(
        chamado_id=str(row.get("chamado_id") or ""),
        produto=row.get("produto") or "",
        cliente_login=row.get("login_cliente") or "",
        organizacao=organizacao,
        data=data,
        assunto=row.get("assunto") or "",
        origem=row.get("origem") or "cliente",
        quantidade_interacoes_cliente=qtd_int,
    )


def _validar_registry_chamados() -> None:
    """Valida no startup que cada organização tem todas as chaves obrigatórias
    em `colunas`. Falha rápida em vez de gerar SQL inválido depois.
    """
    for organizacao, spec in config.TABELAS_CHAMADOS_POR_ORGANIZACAO.items():
        if "schema" not in spec or "tabela" not in spec:
            raise ValueError(
                f"Organização '{organizacao}' sem schema/tabela no registry."
            )
        cols = spec.get("colunas") or {}
        faltando = [c for c in config.COLUNAS_OBRIGATORIAS_CHAMADOS if c not in cols]
        if faltando:
            raise ValueError(
                f"Organização '{organizacao}' faltam colunas no registry: {faltando}"
            )


class ChamadosExtractor(FonteChamados):
    """Lê chamados das tabelas Postgres específicas por organização.

    Implementação declarativa: a estrutura do SQL para cada organização vive
    em config.TABELAS_CHAMADOS_POR_ORGANIZACAO. Este extractor é genérico —
    itera o registry e usa _montar_sql_chamados() para cada org.

    Para adicionar uma nova organização, edite o config.py. Zero código novo.
    """

    def __init__(self) -> None:
        # Falha rápida: se o registry estiver inconsistente, erro no startup,
        # não na primeira chamada de produção.
        _validar_registry_chamados()

    def _consultar_organizacao(
        self,
        organizacao: str,
        where_clause: str,
        params: tuple,
    ) -> List[InteracaoChamado]:
        """Helper: constrói SQL para a organização e executa."""
        spec = config.TABELAS_CHAMADOS_POR_ORGANIZACAO[organizacao]
        sql = _montar_sql_chamados(spec, where_clause)
        from db import conectar
        with conectar() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                colunas = [desc[0] for desc in cur.description]
                rows = [dict(zip(colunas, row)) for row in cur.fetchall()]
        return [_row_para_interacao_chamado(r, organizacao) for r in rows]

    def listar_chamados_periodo(
        self, horas: int, produtos: Optional[List[str]] = None
    ) -> List[InteracaoChamado]:
        """Itera o registry e consulta TODAS as organizações. Falha em uma
        organização não derruba as outras (defensiva por org)."""
        corte = time_utils.agora_utc() - timedelta(hours=horas)
        # Coluna `data` é o alias canônico vindo do _montar_sql. O WHERE precisa
        # casar com a tabela real — usamos o nome lógico via spec.
        resultados: List[InteracaoChamado] = []
        for organizacao, spec in _registry_chamados_ativo().items():
            alias = spec.get("alias")
            col_data = spec["colunas"]["data"]  # já vem com alias correto
            where = f"{col_data} >= %s"
            try:
                resultados.extend(self._consultar_organizacao(
                    organizacao, where, (time_utils.utc_para_string_banco(corte),)
                ))
            except Exception as exc:
                log.warning(
                    "Falha ao consultar chamados de %s: %s",
                    organizacao, exc,
                )
        if produtos:
            resultados = [r for r in resultados if r.produto in produtos]
        return resultados

    def listar_chamados_cliente(
        self, login_cliente: str, meses: int
    ) -> List[InteracaoChamado]:
        """Descobre a organização do cliente via última INC e consulta APENAS
        a tabela correspondente (eficiente).

        Fallback: se não descobrir organização, consulta TODAS as tabelas. Isso
        cobre clientes que nunca abriram INC (raro — Saúde do Cliente exige >=3 INCs).
        """
        corte = time_utils.agora_utc() - timedelta(days=30 * meses)
        corte_str = time_utils.utc_para_string_banco(corte)

        # Tenta descobrir organização do cliente (otimização).
        organizacao = self._descobrir_organizacao_via_inc(login_cliente)
        registry_ativo = _registry_chamados_ativo()

        orgs_para_consultar = (
            [organizacao] if organizacao and organizacao in registry_ativo
            else list(registry_ativo.keys())
        )

        resultados: List[InteracaoChamado] = []
        for org in orgs_para_consultar:
            spec = registry_ativo.get(org)
            if not spec:
                log.warning("Organização '%s' não está no registry. Pulando.", org)
                continue
            col_data = spec["colunas"]["data"]
            col_login = spec["colunas"]["login_cliente"]
            # Compara contra a forma normalizada — o `login_cliente` que chega
            # aqui é o canônico (vindo de contar_clientes_com_inc_recente).
            login_norm = sql_normalizar_login_cliente(col_login)
            where = f"{login_norm} = %s AND {col_data} >= %s"
            try:
                resultados.extend(self._consultar_organizacao(
                    org, where, (login_cliente, corte_str)
                ))
            except Exception as exc:
                log.warning("Falha ao consultar %s para %s: %s", org, login_cliente, exc)
        return resultados

    def listar_chamados_para_saude(
        self, logins_canonicos: Sequence[str], meses: int
    ) -> Dict[str, List[InteracaoChamado]]:
        """Bulk: 1 SELECT por organização para TODOS os logins canônicos.

        Substitui N×2 chamadas individuais (uma por cliente, por org) por
        2 queries totais (Locaweb + KingHost). Cada org devolve só os clientes
        que realmente têm chamado lá — não precisa descobrir organização antes.
        """
        if not logins_canonicos:
            return {}

        corte = time_utils.agora_utc() - timedelta(days=30 * meses)
        corte_str = time_utils.utc_para_string_banco(corte)
        placeholders = ",".join(["%s"] * len(logins_canonicos))

        agrupado: Dict[str, List[InteracaoChamado]] = {
            login: [] for login in logins_canonicos
        }
        for organizacao, spec in _registry_chamados_ativo().items():
            col_data = spec["colunas"]["data"]
            col_login = spec["colunas"]["login_cliente"]
            login_norm = sql_normalizar_login_cliente(col_login)
            where = f"{login_norm} IN ({placeholders}) AND {col_data} >= %s"
            try:
                chamados = self._consultar_organizacao(
                    organizacao, where, tuple(logins_canonicos) + (corte_str,)
                )
            except Exception as exc:
                log.warning(
                    "Falha ao consultar bulk %s: %s — clientes dessa org sem chamados.",
                    organizacao, exc,
                )
                continue
            for chamado in chamados:
                login = normalizar_login_cliente(chamado.cliente_login)
                if login in agrupado:
                    agrupado[login].append(chamado)
        return agrupado

    def contar_chamados_vinculados(
        self, prb_id: str, incs_ids: Sequence[str],
        desde: datetime, ate: datetime,
    ) -> int:
        """Conta chamados em dynamics.chamados onde `prb = prb_id` OR
        `inc IN incs_ids`, na janela [desde, ate).

        Query consulta APENAS `dynamics.chamados` (Locaweb) — `kinghost.chamados`
        não tem mapeamento `inc`/`prb` no registry hoje. Se KingHost ativar
        no futuro, esta função precisará ser estendida.

        Edge cases:
          - `prb_id` vazio e `incs_ids` vazio → retorna 0 sem hit no banco.
          - `incs_ids` vazio → só filtra por prb.
          - `prb_id` vazio → só filtra por inc IN (...).
        """
        prb_id = (prb_id or "").strip()
        incs = [i for i in incs_ids if i and i.strip()]
        if not prb_id and not incs:
            return 0

        clausulas = []
        params: List[Any] = [
            time_utils.utc_para_string_banco(desde),
            time_utils.utc_para_string_banco(ate),
        ]
        if prb_id:
            clausulas.append("prb = %s")
            params.append(prb_id)
        if incs:
            placeholders = ",".join(["%s"] * len(incs))
            clausulas.append(
                f"(inc IS NOT NULL AND TRIM(inc) <> '' AND inc IN ({placeholders}))"
            )
            params.extend(incs)
        clausula_or = " OR ".join(clausulas)

        sql = f"""
            SELECT COUNT(*) FROM dynamics.chamados
            WHERE datacriacao >= %s
              AND datacriacao <  %s
              AND ({clausula_or})
        """
        try:
            from db import conectar
            with conectar() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, tuple(params))
                    row = cur.fetchone()
                    return int(row[0]) if row and row[0] else 0
        except Exception as exc:
            log.warning(
                "Falha em contar_chamados_vinculados(prb=%s, %d incs): %s",
                prb_id, len(incs), exc,
            )
            return 0

    def agrupar_chamados_vinculados_por_equipe(
        self, prb_id: str, incs_ids: Sequence[str],
        desde: datetime, ate: datetime,
    ) -> Dict[str, int]:
        """Agrupa chamados vinculados ao PRB/INCs por equipeproprietaria.

        Mesma cláusula OR de `contar_chamados_vinculados` (prb=X OR inc IN ...),
        com GROUP BY em COALESCE(NULLIF(TRIM(equipeproprietaria), ''),
        '<sem-equipe>'). Ordena por qtd desc — caller (ValidadorEntrega)
        limita ao Top N (config.TOP_EQUIPES_IMPACTADAS).

        Edge cases (idênticos a contar_chamados_vinculados):
          - prb_id vazio e incs_ids vazio → retorna {} sem hit no banco.
          - incs_ids vazio → só filtra por prb.
          - prb_id vazio → só filtra por inc IN (...).
        """
        prb_id = (prb_id or "").strip()
        incs = [i for i in incs_ids if i and i.strip()]
        if not prb_id and not incs:
            return {}

        clausulas = []
        params: List[Any] = [
            time_utils.utc_para_string_banco(desde),
            time_utils.utc_para_string_banco(ate),
        ]
        if prb_id:
            clausulas.append("prb = %s")
            params.append(prb_id)
        if incs:
            placeholders = ",".join(["%s"] * len(incs))
            clausulas.append(
                f"(inc IS NOT NULL AND TRIM(inc) <> '' AND inc IN ({placeholders}))"
            )
            params.extend(incs)
        clausula_or = " OR ".join(clausulas)

        sql = f"""
            SELECT COALESCE(NULLIF(TRIM(equipeproprietaria), ''), '<sem-equipe>') AS equipe,
                   COUNT(*) AS qtd
            FROM dynamics.chamados
            WHERE datacriacao >= %s
              AND datacriacao <  %s
              AND ({clausula_or})
            GROUP BY 1
            ORDER BY qtd DESC
        """
        try:
            from db import conectar
            with conectar() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, tuple(params))
                    return {row[0]: int(row[1]) for row in cur.fetchall()}
        except Exception as exc:
            log.warning(
                "Falha em agrupar_chamados_vinculados_por_equipe(prb=%s, %d incs): %s",
                prb_id, len(incs), exc,
            )
            return {}

    def contar_chamados_por_produto(
        self, produto: str, desde: datetime, ate: datetime
    ) -> int:
        """[DEPRECATED — ver contar_chamados_vinculados.] Conta chamados
        (Locaweb + KingHost) com match EXATO por produto.

        Itera as organizações do registry, executa COUNT(*) por org com
        `WHERE {col_produto} = %s AND {col_data} >= %s AND {col_data} < %s`,
        e soma os totais. Falha numa org não derruba as outras.
        """
        from db import conectar
        desde_str = time_utils.utc_para_string_banco(desde)
        ate_str = time_utils.utc_para_string_banco(ate)
        total = 0
        for organizacao, spec in _registry_chamados_ativo().items():
            col_data = spec["colunas"]["data"]
            col_produto = spec["colunas"]["produto"]
            alias = spec.get("alias")
            schema = spec["schema"]
            tabela = spec["tabela"]
            from_sql = f"{schema}.{tabela}" + (f" {alias}" if alias else "")
            join_sql = ""
            join = spec.get("join")
            if join:
                conds = " AND ".join(
                    f"{alias}.{k} = {join['alias']}.{k}" for k in join["chaves"]
                )
                join_sql = (
                    f"\nLEFT JOIN {join['schema']}.{join['tabela']} {join['alias']}\n"
                    f"    ON {conds}"
                )
            sql = (
                f"SELECT COUNT(*) FROM {from_sql}{join_sql}\n"
                f"WHERE {col_produto} = %s AND {col_data} >= %s AND {col_data} < %s"
            )
            try:
                with conectar() as conn:
                    with conn.cursor() as cur:
                        cur.execute(sql, (produto, desde_str, ate_str))
                        row = cur.fetchone()
                        total += int(row[0]) if row and row[0] else 0
            except Exception as exc:
                log.warning(
                    "Falha ao contar chamados em %s para produto=%r: %s",
                    organizacao, produto, exc,
                )
        return total

    def _descobrir_organizacao_via_inc(
        self, login_cliente: str
    ) -> Optional[str]:
        """Lê a coluna `organizacao` da última INC do cliente. None se não há INC.

        Usado para rotear consultas de Saúde do Cliente para a tabela de chamados certa
        (evita consultar dynamics+kinghost desnecessariamente).
        """
        filtro_org, params_org = _filtro_orgs_sni()
        sql = f"""
            SELECT organizacao
            FROM {config.SCHEMA_BANCO}.{config.TABELA_INCIDENTES}
            WHERE {_LOGIN_NORM_SNI} = %s
              {filtro_org}
            ORDER BY data_abertura DESC
            LIMIT 1
        """
        try:
            from db import conectar
            with conectar() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (login_cliente,))
                    row = cur.fetchone()
            return row[0] if row and row[0] else None
        except Exception as exc:
            log.warning(
                "Falha ao descobrir organização de %s: %s — caindo para fallback.",
                login_cliente, exc,
            )
            return None


# -----------------------------------------------------------------------------
# Mocks — dados sintéticos coerentes com a matriz de regras
# -----------------------------------------------------------------------------
class _GeradorMock:
    """Fornece datasets reproduzíveis que exercitam todas as regras (P1..P5)."""

    PRODUTOS = ["VPS", "Servidor Dedicado", "CAL", "Painel do Produto", "Central do Cliente"]
    SERVIDORES = [
        "vps-prod-01.locaweb.local",
        "vps-prod-02.locaweb.local",
        "dedicado-mg-15.locaweb.local",
        "cal-frontend-03.locaweb.local",
        "painel-api-07.locaweb.local",
    ]
    CLIENTES = [f"cliente{i:03d}" for i in range(1, 20)]
    GRUPOS = ["NOC", "DBA", "Service Operation", "Infra Cloud", "Suporte N2"]

    # Cenários por cluster temático (cada item vira N INCs similares)
    CENARIOS = [
        {
            "tema": "kernel panic vps fora",
            "descricao_curta": "Servidor VPS fora — kernel panic",
            "descricao": "VPS não pinga, não responde SSH. Erro ao montar system rescue.",
            "produto": "VPS",
            "servidor": "vps-prod-01.locaweb.local",
            "categoria": "Servidor",
            "subcategoria": "Indisponibilidade",
            "grupo": "NOC",
            "prioridade": "P3",
            "tem_contorno": False,
            "tempo_contorno_min": 0,
            "qtd_incs": 6,
        },
        {
            "tema": "checkout indisponivel pagamento",
            "descricao_curta": "Checkout indisponível — contratação travada",
            "descricao": "Cliente reclame aqui sem solucao de contorno. Carrinho não conclui.",
            "produto": "CAL",
            "servidor": "cal-frontend-03.locaweb.local",
            "categoria": "Aplicação",
            "subcategoria": "Indisponibilidade",
            "grupo": "Service Operation",
            "prioridade": "P2",
            "tem_contorno": False,
            "tempo_contorno_min": 0,
            "qtd_incs": 3,
        },
        {
            "tema": "lentidao painel api",
            "descricao_curta": "Lentidão no painel do produto",
            "descricao": "Funcionalidade parcial. Há contorno: reiniciar sessão (5 min).",
            "produto": "Painel do Produto",
            "servidor": "painel-api-07.locaweb.local",
            "categoria": "Aplicação",
            "subcategoria": "Performance",
            "grupo": "Infra Cloud",
            "prioridade": "P4",
            "tem_contorno": True,
            "tempo_contorno_min": 5,
            "qtd_incs": 25,
        },
        {
            "tema": "erro https certificado",
            "descricao_curta": "Erro de certificado HTTPS",
            "descricao": "Cliente reporta certificado expirado. Contorno: forçar renovação (30 min).",
            "produto": "Servidor Dedicado",
            "servidor": "dedicado-mg-15.locaweb.local",
            "categoria": "Segurança",
            "subcategoria": "Certificado",
            "grupo": "Suporte N2",
            "prioridade": "P3",
            "tem_contorno": True,
            "tempo_contorno_min": 30,
            "qtd_incs": 55,
        },
        {
            "tema": "instalacao servidor dedicado",
            "descricao_curta": "Falha na instalação de novo servidor dedicado",
            "descricao": "Provisionamento travado. Impacto direto na entrega ao cliente.",
            "produto": "Servidor Dedicado",
            "servidor": "dedicado-mg-15.locaweb.local",
            "categoria": "Provisionamento",
            "subcategoria": "Falha",
            "grupo": "Infra Cloud",
            "prioridade": "P3",
            "tem_contorno": False,
            "tempo_contorno_min": 0,
            "qtd_incs": 2,
        },
    ]

    def __init__(self, semente: int = 42) -> None:
        self.rng = random.Random(semente)

    def gerar_incidentes(self) -> List[Incidente]:
        agora = time_utils.agora_utc()
        incidentes: List[Incidente] = []
        seq = 0
        for cenario in self.CENARIOS:
            for _ in range(cenario["qtd_incs"]):
                seq += 1
                abertura = agora - timedelta(hours=self.rng.uniform(0.5, 23.5))
                atualizacao = abertura + timedelta(minutes=self.rng.uniform(5, 720))
                updates = (
                    self.rng.randint(8, 15) if "kernel" in cenario["tema"]
                    else self.rng.randint(1, 5)
                )
                cliente = self.rng.choice(self.CLIENTES[:5] if seq % 3 == 0 else self.CLIENTES)
                incidentes.append(Incidente(
                    inc_id=f"INC{1000000 + seq:07d}",
                    descricao_curta=cenario["descricao_curta"],
                    descricao=cenario["descricao"],
                    servidor=cenario["servidor"],
                    produto=cenario["produto"],
                    login_cliente=cliente,
                    prioridade_atual=cenario["prioridade"],
                    abertura=abertura,
                    atualizacao=atualizacao,
                    qtd_atualizacoes=updates,
                    tem_solucao_contorno=cenario["tem_contorno"],
                    tempo_solucao_contorno_min=cenario["tempo_contorno_min"],
                    organizacao=f"org-{cliente}",
                    categoria=cenario["categoria"],
                    subcategoria=cenario["subcategoria"],
                    grupo_designado=cenario["grupo"],
                    status=self.rng.choice(["Novo", "Em Análise", "Resolvido"]),
                    tipo_usuario="Nominal",
                ))
        self.rng.shuffle(incidentes)
        return incidentes

    def gerar_prbs(self) -> List[PRBExistente]:
        """PRBs já abertos — um deles ficará 'desatualizado' (P3 mas o cluster cresceu)."""
        return [
            PRBExistente(
                prb_id="PRB0000123",
                descricao_curta="Kernel panic intermitente em VPS de produção",
                descricao="Recorrência de kernel panic em servidores VPS hospedados no host físico HP-01.",
                produto="VPS",
                servidor="vps-prod-01.locaweb.local",
                prioridade_atual="P3",
                status="Em Análise",
                solucao_alternativa="Migrar VM para host HP-02 manualmente.",
                categoria="Servidor",
                subcategoria="Indisponibilidade",
                grupo_designado="NOC",
                qtd_atualizacoes=3,
                aberto_em=time_utils.agora_utc() - timedelta(days=4),
            ),
            PRBExistente(
                prb_id="PRB0000456",
                descricao_curta="Lentidão recorrente no painel API",
                descricao="Painel apresenta lentidão em horários de pico.",
                produto="Painel do Produto",
                servidor="painel-api-07.locaweb.local",
                prioridade_atual="P4",
                status="Solução Pendente",
                solucao_alternativa="Reiniciar pool de aplicação.",
                categoria="Aplicação",
                subcategoria="Performance",
                grupo_designado="Infra Cloud",
                qtd_atualizacoes=2,
                aberto_em=time_utils.agora_utc() - timedelta(days=10),
            ),
        ]

    def gerar_prbs_para_validacao(self) -> List[PRBExistente]:
        """Mock para o ValidadorEntrega: 3 PRBs cobrindo os 3 veredictos esperados.

        - PRB0000789: resolvido há 10 dias (>= MIN_DIAS_PARA_VALIDAR) sem INCs novas
          no produto/servidor → ENTREGA_VALIDADA.
        - PRB0000790: resolvido há 5 dias, mock injeta 4 INCs no mesmo
          (produto, servidor) → REINCIDENCIA.
        - PRB0000791: resolvido há 2 dias (< MIN_DIAS_PARA_VALIDAR), sem INCs → INCONCLUSIVO.
        """
        agora = time_utils.agora_utc()
        return [
            PRBExistente(
                prb_id="PRB0000789",
                descricao_curta="Falha intermitente no agendador de backups",
                descricao="Backups deixavam de rodar em janelas de manutenção.",
                produto="Backup",
                servidor="bkp-cluster-02.locaweb.local",
                prioridade_atual="P3",
                status="Concluído",
                solucao_alternativa="Reagendamento manual via cron.",
                grupo_designado="Infra Cloud",
                qtd_atualizacoes=4,
                aberto_em=agora - timedelta(days=20),
                data_resolucao=agora - timedelta(days=10),
            ),
            PRBExistente(
                prb_id="PRB0000790",
                descricao_curta="DNS lento em consultas externas",
                descricao="Latência aumentada em consultas DNS reverso.",
                produto="DNS",
                servidor="dnsfirewallb0005",  # casa com CI real do banco para teste integrado
                prioridade_atual="P2",
                status="Encerrado Automaticamente",
                solucao_alternativa="Forçar uso de resolver secundário.",
                grupo_designado="NOC",
                qtd_atualizacoes=6,
                aberto_em=agora - timedelta(days=12),
                data_resolucao=agora - timedelta(days=5),
            ),
            PRBExistente(
                prb_id="PRB0000791",
                descricao_curta="Erro 500 em upload de arquivos grandes",
                descricao="Upload acima de 100MB retornava 500.",
                produto="Hospedagem Compartilhada",
                servidor="hm-shared-09.locaweb.local",
                prioridade_atual="P3",
                status="Concluído",
                solucao_alternativa="Limitar upload a 80MB no front-end.",
                grupo_designado="Web Hosting",
                qtd_atualizacoes=2,
                aberto_em=agora - timedelta(days=6),
                data_resolucao=agora - timedelta(days=2),
            ),
        ]

    def gerar_chamados(
        self, qtd: int = 80, dias: int = 1
    ) -> List[InteracaoChamado]:
        agora = time_utils.agora_utc()
        produtos = self.PRODUTOS
        organizacoes = list(config.TABELAS_CHAMADOS_POR_ORGANIZACAO.keys())
        out: List[InteracaoChamado] = []
        for i in range(qtd):
            cliente = self.rng.choice(self.CLIENTES[:5] if i % 3 == 0 else self.CLIENTES)
            organizacao = self.rng.choice(organizacoes)
            qtd_interacoes_cliente = self.rng.randint(1, 8)
            out.append(InteracaoChamado(
                chamado_id=f"CAS-{500000 + i}",
                produto=self.rng.choice(produtos),
                cliente_login=cliente,
                organizacao=organizacao,
                data=agora - timedelta(hours=self.rng.uniform(0, dias * 24)),
                assunto=self.rng.choice([
                    "Servidor lento", "Não consigo acessar", "Erro no checkout",
                    "Dúvida de configuração", "Solicitação de upgrade",
                ]),
                origem="cliente",  # mock: cada row = 1 chamado de cliente
                quantidade_interacoes_cliente=qtd_interacoes_cliente,
            ))
        return out


class ServiceNowExtractorMock(FonteIncidentes):
    """Drop-in replacement do ServiceNowExtractor para validação local."""

    def __init__(self) -> None:
        self._gerador = _GeradorMock(semente=42)
        self._incidentes_cache: Optional[List[Incidente]] = None

    def _todos_incidentes(self) -> List[Incidente]:
        if self._incidentes_cache is None:
            self._incidentes_cache = self._gerador.gerar_incidentes()
        return self._incidentes_cache

    def listar_incidentes_recentes(self, horas: int) -> List[Incidente]:
        corte = time_utils.agora_utc() - timedelta(hours=horas)
        return [i for i in self._todos_incidentes() if i.abertura >= corte]

    def listar_prbs_abertos(self) -> List[PRBExistente]:
        return self._gerador.gerar_prbs()

    def listar_prbs_para_validacao(self, dias: int) -> List[PRBExistente]:
        """Mock: devolve PRBs sintéticos com data_resolucao dentro da janela.
        O parâmetro `dias` é respeitado — filtra os mocks pela janela real.
        """
        corte = time_utils.agora_utc() - timedelta(days=dias)
        prbs = self._gerador.gerar_prbs_para_validacao()
        return [
            p for p in prbs
            if p.data_resolucao is not None and p.data_resolucao >= corte
        ]

    def listar_prbs_por_numero(self, numeros: Sequence[str]) -> List[PRBExistente]:
        """Mock: pega PRBs sintéticos cujo numero está na lista solicitada.

        Não filtra por status; espelha o comportamento da implementação real
        (D-03 — sem janela). Edge case: lista vazia → retorna [].
        """
        if not numeros:
            return []
        alvos = set(numeros)
        todos = self._gerador.gerar_prbs() + self._gerador.gerar_prbs_para_validacao()
        return [p for p in todos if p.prb_id in alvos]

    def listar_incidentes_por_produto_servidor(
        self, produto: str, servidor: str, desde: datetime,
        ate: Optional[datetime] = None,
    ) -> List[Incidente]:
        """Mock: injeta INCs sintéticas só quando produto+servidor batem com
        o PRB de reincidência (PRB0000790 / DNS / dnsfirewallb0005). Para os
        outros casos devolve lista vazia — preserva os veredictos esperados.
        """
        if produto == "DNS" and servidor == "dnsfirewallb0005":
            qtd = 4
            return [
                Incidente(
                    inc_id=f"INC_REINC_{i:03d}",
                    descricao_curta="Latência DNS reincidiu após resolução",
                    descricao="Resolução DNS lenta novamente em consultas reverso.",
                    servidor=servidor,
                    produto=produto,
                    login_cliente="",
                    prioridade_atual="P3",
                    abertura=desde + timedelta(days=1, hours=i),
                    atualizacao=desde + timedelta(days=1, hours=i),
                    qtd_atualizacoes=1,
                    tem_solucao_contorno=False,
                    organizacao="Locaweb",
                    tipo_usuario="Integração",
                )
                for i in range(qtd)
            ]
        return []

    def contar_clientes_com_inc_recente(
        self, horas: int, tipos_usuario: Sequence[str] = ()
    ) -> Dict[str, int]:
        from collections import Counter
        corte = time_utils.agora_utc() - timedelta(hours=horas)
        tipos_set = set(tipos_usuario)
        counter: Counter[str] = Counter()
        for inc in self._todos_incidentes():
            if inc.abertura < corte:
                continue
            login_norm = normalizar_login_cliente(inc.login_cliente)
            if not login_norm:
                continue
            if tipos_set and inc.tipo_usuario not in tipos_set:
                continue
            counter[login_norm] += 1
        return dict(counter)

    def listar_incidentes_para_saude(
        self, logins_canonicos: Sequence[str], meses: int
    ) -> Dict[str, List[Incidente]]:
        agrupado: Dict[str, List[Incidente]] = {l: [] for l in logins_canonicos}
        for login in logins_canonicos:
            agrupado[login] = self.listar_incidentes_cliente(login, meses)
        return agrupado

    def contar_incidentes_no_ci_periodo(
        self, produto: str, servidor: str, desde: datetime, ate: datetime
    ) -> Dict[str, int]:
        casados = [
            i for i in self._todos_incidentes()
            if i.produto == produto and i.servidor == servidor
            and desde <= i.abertura < ate
        ]
        return {
            "qtd": len(casados),
            "clientes_unicos": len({i.login_cliente for i in casados if i.login_cliente}),
            "categorias": len({i.categoria for i in casados if i.categoria}),
        }

    def listar_prbs_novos_no_ci_periodo(
        self, produto: str, servidor: str, desde: datetime, ignorar_prb_id: str = ""
    ) -> List[str]:
        # Mock: derivar dos PRBs abertos sintéticos quando match (produto+servidor).
        novos = []
        for prb in self._gerador.gerar_prbs():
            if (
                prb.produto == produto and prb.servidor == servidor
                and prb.prb_id != ignorar_prb_id
                and prb.aberto_em and prb.aberto_em >= desde
            ):
                novos.append(prb.prb_id)
        return novos

    def listar_incidentes_cliente(
        self, login_cliente: str, meses: int
    ) -> List[Incidente]:
        corte = time_utils.agora_utc() - timedelta(days=30 * meses)
        recentes = [
            i for i in self._todos_incidentes()
            if normalizar_login_cliente(i.login_cliente) == login_cliente
        ]
        historicos: List[Incidente] = []
        for idx, inc in enumerate(recentes):
            inc_copia = Incidente(
                inc_id=f"{inc.inc_id}-H{idx}",
                descricao_curta=inc.descricao_curta,
                descricao=inc.descricao,
                servidor=inc.servidor,
                produto=inc.produto,
                login_cliente=login_cliente,
                prioridade_atual=inc.prioridade_atual,
                abertura=time_utils.agora_utc() - timedelta(days=15 * (idx + 1)),
                atualizacao=time_utils.agora_utc() - timedelta(days=15 * (idx + 1)),
                qtd_atualizacoes=inc.qtd_atualizacoes,
                tem_solucao_contorno=inc.tem_solucao_contorno,
                tempo_solucao_contorno_min=inc.tempo_solucao_contorno_min,
                organizacao=inc.organizacao,
                categoria=inc.categoria,
                subcategoria=inc.subcategoria,
                grupo_designado=inc.grupo_designado,
                status=inc.status,
                tipo_usuario=inc.tipo_usuario,
            )
            if inc_copia.abertura >= corte:
                historicos.append(inc_copia)
        return recentes + historicos


class ChamadosExtractorMock(FonteChamados):
    """Drop-in replacement do ChamadosExtractor para validação local."""

    def __init__(self) -> None:
        self._gerador = _GeradorMock(semente=99)
        self._cache: Optional[List[InteracaoChamado]] = None

    def _todos(self) -> List[InteracaoChamado]:
        if self._cache is None:
            self._cache = self._gerador.gerar_chamados(qtd=80, dias=1)
        return self._cache

    def listar_chamados_periodo(
        self, horas: int, produtos: Optional[List[str]] = None
    ) -> List[InteracaoChamado]:
        corte = time_utils.agora_utc() - timedelta(hours=horas)
        resultado = [i for i in self._todos() if i.data >= corte]
        if produtos:
            resultado = [i for i in resultado if i.produto in produtos]
        return resultado

    def listar_chamados_para_saude(
        self, logins_canonicos: Sequence[str], meses: int
    ) -> Dict[str, List[InteracaoChamado]]:
        agrupado: Dict[str, List[InteracaoChamado]] = {l: [] for l in logins_canonicos}
        for login in logins_canonicos:
            agrupado[login] = self.listar_chamados_cliente(login, meses)
        return agrupado

    def contar_chamados_por_produto(
        self, produto: str, desde: datetime, ate: datetime
    ) -> int:
        return sum(
            1 for c in self._todos()
            if c.produto == produto and desde <= c.data < ate
        )

    def contar_chamados_vinculados(
        self, prb_id: str, incs_ids: Sequence[str],
        desde: datetime, ate: datetime,
    ) -> int:
        # Mock: o dataset sintético não tem colunas inc/prb nos chamados —
        # retorna 0. Testes injetam comportamento via _FakeFonteChamados.
        return 0

    def agrupar_chamados_vinculados_por_equipe(
        self, prb_id: str, incs_ids: Sequence[str],
        desde: datetime, ate: datetime,
    ) -> Dict[str, int]:
        # Mock: dataset sintético não tem equipeproprietaria — retorna {}.
        return {}

    def listar_chamados_cliente(
        self, login_cliente: str, meses: int
    ) -> List[InteracaoChamado]:
        corte = time_utils.agora_utc() - timedelta(days=30 * meses)
        base = [
            i for i in self._todos()
            if normalizar_login_cliente(i.cliente_login) == login_cliente
        ]
        historicos: List[InteracaoChamado] = []
        for idx, inter in enumerate(base):
            historicos.append(InteracaoChamado(
                chamado_id=f"{inter.chamado_id}-H{idx}",
                produto=inter.produto,
                cliente_login=login_cliente,
                organizacao=inter.organizacao,
                data=time_utils.agora_utc() - timedelta(days=20 * (idx + 1)),
                assunto=inter.assunto,
                origem=inter.origem,
                descricao=inter.descricao,
                quantidade_interacoes_cliente=inter.quantidade_interacoes_cliente,
            ))
        todos = base + historicos
        return [i for i in todos if i.data >= corte]


# -----------------------------------------------------------------------------
# Factory — escolhe mock vs. real conforme config
# -----------------------------------------------------------------------------
def criar_fonte_incidentes() -> FonteIncidentes:
    if config.USAR_MOCKS:
        log.info("Usando ServiceNowExtractorMock (USAR_MOCKS=true).")
        return ServiceNowExtractorMock()
    log.info("Usando ServiceNowExtractor real (PostgreSQL lwsa.*).")
    return ServiceNowExtractor()


def criar_fonte_chamados() -> FonteChamados:
    if config.USAR_MOCKS:
        log.info("Usando ChamadosExtractorMock (USAR_MOCKS=true).")
        return ChamadosExtractorMock()
    log.info("Usando ChamadosExtractor real (PostgreSQL dynamics/kinghost).")
    return ChamadosExtractor()