"""Cliente da API SGS do Banco Central (séries temporais).

Limitações conhecidas (modelo.md, seção 2.1):
- a API recusa janelas maiores que 10 anos em séries diárias (HTTP 406);
- séries diárias exigem `dataInicial` e `dataFinal` juntos;
- as datas vão em `dd/mm/aaaa`.
Por isso `buscar_serie` divide o período em janelas de até 9 anos.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

URL_BASE = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
URL_ULTIMOS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados/ultimos/{quantidade}"

FORMATO_DATA = "%d/%m/%Y"
ANOS_MAXIMOS_POR_JANELA = 9
TIMEOUT_SEGUNDOS = 60
CABECALHOS = {"Accept": "application/json"}


def converter_data(valor: str | date | datetime) -> date:
    """Aceita `dd/mm/aaaa`, `aaaa-mm-dd` ou objetos de data."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor

    texto = str(valor).strip()[:10]
    for formato in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    raise ValueError("data em formato não reconhecido: " + str(valor))


def formatar_data(valor: str | date | datetime) -> str:
    """Devolve a data no formato exigido pela API SGS (`dd/mm/aaaa`)."""
    return converter_data(valor).strftime(FORMATO_DATA)


def dividir_em_janelas(
    de: date, ate: date, anos_max: int = ANOS_MAXIMOS_POR_JANELA
) -> list[tuple[date, date]]:
    """Divide o período em janelas de até `anos_max` anos, sem sobreposição."""
    if de > ate:
        raise ValueError("data inicial posterior à final")

    janelas: list[tuple[date, date]] = []
    inicio = de
    while inicio <= ate:
        try:
            limite = inicio.replace(year=inicio.year + anos_max)
        except ValueError:  # 29 de fevereiro
            limite = inicio.replace(year=inicio.year + anos_max, day=28)
        fim = min(limite - timedelta(days=1), ate)
        janelas.append((inicio, fim))
        inicio = fim + timedelta(days=1)
    return janelas


def _requisitar(url: str, parametros: dict | None = None) -> list[dict]:
    resposta = requests.get(url, params=parametros, timeout=TIMEOUT_SEGUNDOS, headers=CABECALHOS)
    resposta.encoding = "utf-8"  # a API não informa o charset corretamente
    resposta.raise_for_status()

    corpo = (resposta.text or "").strip()
    if not corpo:
        # O SGS às vezes devolve 200 com corpo vazio (falha transitória). Erro explícito
        # para o retry agir — devolver [] aqui esconderia dado que existe na janela.
        raise ValueError(
            "resposta vazia da API SGS (HTTP %s) para %s" % (resposta.status_code, url)
        )

    try:
        dados = resposta.json()
    except ValueError as erro:
        raise ValueError(
            "resposta da API SGS nao e JSON (HTTP %s): %s"
            % (resposta.status_code, corpo[:200])
        ) from erro

    if not isinstance(dados, list):
        raise ValueError("resposta inesperada da API SGS: " + str(type(dados)))
    return dados

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    reraise=True,
)
def fetch_sgs(
    codigo: int,
    data_inicial: str | date | datetime,
    data_final: str | date | datetime,
) -> list[dict]:
    """Busca uma janela de uma série do SGS. Repete até 3 vezes se a rede falhar."""
    parametros = {
        "formato": "json",
        "dataInicial": formatar_data(data_inicial),
        "dataFinal": formatar_data(data_final),
    }
    return _requisitar(URL_BASE.format(codigo=int(codigo)), parametros)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    reraise=True,
)
def fetch_ultimos(codigo: int, quantidade: int = 12) -> list[dict]:
    """Busca os últimos N valores de uma série do SGS."""
    url = URL_ULTIMOS.format(codigo=int(codigo), quantidade=int(quantidade))
    return _requisitar(url, {"formato": "json"})


def buscar_serie(
    codigo: int,
    data_inicial: str | date | datetime,
    data_final: str | date | datetime,
) -> list[dict]:
    """Busca o período completo, em janelas de 9 anos, sem repetir datas."""
    de = converter_data(data_inicial)
    ate = converter_data(data_final)

    registros: dict[str, dict] = {}
    for inicio, fim in dividir_em_janelas(de, ate):
        for item in fetch_sgs(codigo, inicio, fim):
            registros[str(item.get("data"))] = item

    return [
        registros[chave]
        for chave in sorted(registros, key=lambda texto: converter_data(texto))
    ]
