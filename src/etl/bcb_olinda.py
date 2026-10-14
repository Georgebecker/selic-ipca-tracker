"""Cliente da API Olinda do Banco Central — boletim Focus (expectativas de mercado).

Com o Focus dá para responder a pergunta que o SGS sozinho não responde: **o que o
mercado espera** e quanto isso está longe do realizado. O SGS publica o passado; o Focus
publica a expectativa.

Recursos usados (OData, `$format=json`):
- `ExpectativasMercadoInflacao12Meses` — mediana do IPCA/IGP-M para os próximos 12 meses
  (publicação semanal, `Data` = data do boletim, `Suavizada` = S/N);
- `ExpectativasMercadoAnuais` — mediana para um ano fechado (`DataReferencia` = ano);
- `ExpectativasMercadoSelic` — mediana da Selic por reunião do Copom (`Reuniao`).

Cuidados (mesmas lições do cliente do SGS):
- corpo vazio é erro explícito, para o retry agir — nunca `[]` silencioso;
- `requests` monta a query (encoding de `$filter` na mão é armadilha);
- quem chama nunca é surpreendido por exceção: `expectativas_do_focus()` devolve
  `disponivel=False` e o motivo, para a interface seguir funcionando sem o Olinda.
"""

from __future__ import annotations

from datetime import date, datetime
from urllib.parse import quote

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

URL_FOCUS = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata"
FORMATO = "json"
TIMEOUT_SEGUNDOS = 60
CABECALHOS = {"Accept": "application/json"}

INDICADOR_IPCA = "IPCA"
INDICADOR_IGPM = "IGP-M"
INDICADOR_SELIC = "Selic"


def _converter_data(valor) -> date | None:
    if not valor:
        return None
    texto = str(valor).strip()[:10]
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date()
    except ValueError:
        return None


def _converter_numero(valor) -> float | None:
    if valor is None or valor == "":
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    reraise=True,
)
def buscar_focus(recurso: str, **filtros) -> list[dict]:
    """Busca um recurso do Focus. `filtros` vira OData (ex.: top=3, orderby='Data desc').

    A query é montada à mão de propósito: o OData do Olinda exige o `$` **literal** no nome
    do parâmetro, e o `requests` (via `urlencode`) transforma `$format` em `%24format`, o
    que faz a API responder 400.
    """
    partes = ["$format=" + quote(FORMATO, safe="")]
    for chave, valor in filtros.items():
        if valor is None:
            continue
        partes.append("$" + chave + "=" + quote(str(valor), safe=""))

    url = URL_FOCUS + "/" + recurso + "?" + "&".join(partes)
    resposta = requests.get(url, timeout=TIMEOUT_SEGUNDOS, headers=CABECALHOS)
    resposta.encoding = "utf-8"
    resposta.raise_for_status()

    corpo = (resposta.text or "").strip()
    if not corpo:
        raise ValueError("resposta vazia da API Olinda (HTTP %s) para %s" % (resposta.status_code, recurso))

    try:
        dados = resposta.json()
    except ValueError as erro:
        raise ValueError(
            "resposta da API Olinda nao e JSON (HTTP %s): %s" % (resposta.status_code, corpo[:200])
        ) from erro

    registros = dados.get("value") if isinstance(dados, dict) else dados
    if registros is None:
        raise ValueError("resposta da API Olinda sem o campo 'value'")
    return list(registros)


def _normalizar(registro: dict, referencia: str | None = None) -> dict:
    return {
        "indicador": str(registro.get("Indicador") or "").strip(),
        "data": _converter_data(registro.get("Data")),
        "mediana": _converter_numero(registro.get("Mediana")),
        "media": _converter_numero(registro.get("Media")),
        "minimo": _converter_numero(registro.get("Minimo")),
        "maximo": _converter_numero(registro.get("Maximo")),
        "respondentes": registro.get("numeroRespondentes"),
        "referencia": referencia
        if referencia is not None
        else (str(registro.get("DataReferencia")).strip() if registro.get("DataReferencia") else None),
    }


def expectativas_12_meses(indicador: str = INDICADOR_IPCA, quantidade: int = 1) -> list[dict]:
    """Últimas medianas de 12 meses para um indicador (mais recente primeiro)."""
    registros = buscar_focus(
        "ExpectativasMercadoInflacao12Meses",
        top=quantidade,
        filter="Indicador eq '%s' and Suavizada eq 'N'" % indicador,
        orderby="Data desc",
    )
    return [_normalizar(item) for item in registros]


def expectativas_anuais(indicador: str = INDICADOR_IPCA, quantidade: int = 1) -> list[dict]:
    """Últimas medianas anuais (ano fechado) para um indicador."""
    registros = buscar_focus(
        "ExpectativasMercadoAnuais",
        top=quantidade,
        filter="Indicador eq '%s'" % indicador,
        orderby="Data desc",
    )
    return [_normalizar(item) for item in registros]


def expectativas_selic(quantidade: int = 1) -> list[dict]:
    """Últimas medianas da Selic por reunião do Copom."""
    registros = buscar_focus(
        "ExpectativasMercadoSelic",
        top=quantidade,
        orderby="Data desc",
    )
    return [_normalizar(item, referencia=str(item.get("Reuniao") or "").strip() or None) for item in registros]


def expectativas_do_focus() -> dict:
    """Resumo do Focus para a interface. Nunca levanta exceção.

    Devolve sempre um dicionário com `disponivel` (bool), `motivo` (quando indisponível)
    e as medianas: `ipca_12_meses`, `igpm_12_meses`, `ipca_anual`, `selic` — cada uma pode
    vir `None` se aquele recorte não foi publicado.
    """
    resumo: dict = {
        "disponivel": True,
        "motivo": None,
        "ipca_12_meses": None,
        "igpm_12_meses": None,
        "ipca_anual": None,
        "selic": None,
    }

    def primeiro(itens: list[dict]) -> dict | None:
        return itens[0] if itens else None

    try:
        resumo["ipca_12_meses"] = primeiro(expectativas_12_meses(INDICADOR_IPCA))
        resumo["igpm_12_meses"] = primeiro(expectativas_12_meses(INDICADOR_IGPM))
        resumo["ipca_anual"] = primeiro(expectativas_anuais(INDICADOR_IPCA))
        resumo["selic"] = primeiro(expectativas_selic())
    except Exception as erro:  # noqa: BLE001 - o Olinda fora do ar nao pode derrubar a API
        resumo["disponivel"] = False
        resumo["motivo"] = str(erro)

    return resumo
