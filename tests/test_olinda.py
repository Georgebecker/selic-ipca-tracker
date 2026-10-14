"""Cliente do Olinda/Focus e o endpoint que compara esperado x realizado.

Nada de rede: `requests.get` é substituído por uma resposta falsa, e o endpoint usa um
cliente de mentira. Há um teste específico para a query do OData, porque o `$` do nome do
parâmetro precisa ser literal — quando o `requests` o codificava como `%24`, a API
respondia 400 e a expectativa sumia sem aviso.
"""

from __future__ import annotations

import json

import pytest

from src.api.routers import expectativas as router_expectativas
from src.etl import bcb_olinda


class RespostaFalsa:
    def __init__(self, corpo, status=200):
        self.text = corpo
        self.status_code = status

    def raise_for_status(self):
        return None

    def json(self):
        return json.loads(self.text)


@pytest.fixture
def capturar_url(monkeypatch):
    urls: list[str] = []

    def get_falso(url, **kwargs):
        urls.append(url)
        return RespostaFalsa(json.dumps({"value": []}))

    monkeypatch.setattr(bcb_olinda.requests, "get", get_falso)
    return urls


# --------------------------------- cliente ---------------------------------

def test_a_query_odata_usa_o_cifrao_literal(capturar_url):
    bcb_olinda.buscar_focus("ExpectativasMercadoAnuais", top=1, filter="Indicador eq 'IPCA'")

    url = capturar_url[0]
    assert "$format=json" in url, "o OData do Olinda exige o $ literal, não %24"
    assert "%24" not in url
    assert "$top=1" in url
    assert "$orderby" not in url  # não foi pedido
    assert "Indicador" in url and "IPCA" in url


def test_valores_da_query_sao_codificados(capturar_url):
    bcb_olinda.buscar_focus("ExpectativasMercadoInflacao12Meses", filter="Indicador eq 'IGP-M'", orderby="Data desc")

    url = capturar_url[0]
    assert "%27IGP-M%27" in url, "as aspas do filtro precisam ir codificadas"
    assert "Data%20desc" in url, "espaço deve virar %20, não +"


def test_corpo_vazio_e_erro_explicito(monkeypatch):
    monkeypatch.setattr(bcb_olinda.requests, "get", lambda url, **k: RespostaFalsa("   "))

    with pytest.raises(ValueError) as erro:
        bcb_olinda.buscar_focus("ExpectativasMercadoSelic")

    assert "vazia" in str(erro.value)


def test_corpo_sem_json_e_erro_claro(monkeypatch):
    monkeypatch.setattr(bcb_olinda.requests, "get", lambda url, **k: RespostaFalsa("<html>erro</html>"))

    with pytest.raises(ValueError) as erro:
        bcb_olinda.buscar_focus("ExpectativasMercadoSelic")

    assert "nao e JSON" in str(erro.value)


def test_normalizacao_converte_tipos():
    item = bcb_olinda._normalizar({
        "Indicador": "IPCA",
        "Data": "2026-10-09",
        "Mediana": "4.4757",
        "Media": 4.5,
        "Minimo": None,
        "Maximo": "",
        "numeroRespondentes": 132,
    })

    assert item["indicador"] == "IPCA"
    assert item["data"].isoformat() == "2026-10-09"
    assert item["mediana"] == 4.4757
    assert item["media"] == 4.5
    assert item["minimo"] is None
    assert item["maximo"] is None
    assert item["respondentes"] == 132


def test_resumo_do_focus_junta_os_quatro_recortes(monkeypatch):
    chamadas: list[str] = []

    def buscar_falso(recurso, **filtros):
        chamadas.append(recurso)
        return [{
            "Indicador": filtros.get("filter", "Selic").split("'")[1] if "filter" in filtros else "Selic",
            "Data": "2026-10-09",
            "Mediana": 4.0,
            "numeroRespondentes": 100,
        }]

    monkeypatch.setattr(bcb_olinda, "buscar_focus", buscar_falso)
    resumo = bcb_olinda.expectativas_do_focus()

    assert resumo["disponivel"] is True
    assert resumo["motivo"] is None
    assert resumo["ipca_12_meses"]["mediana"] == 4.0
    assert resumo["igpm_12_meses"]["mediana"] == 4.0
    assert resumo["ipca_anual"]["mediana"] == 4.0
    assert resumo["selic"]["mediana"] == 4.0
    assert set(chamadas) == {
        "ExpectativasMercadoInflacao12Meses",
        "ExpectativasMercadoAnuais",
        "ExpectativasMercadoSelic",
    }


def test_resumo_nao_levanta_excecao_quando_o_olinda_cai(monkeypatch):
    def buscar_que_falha(recurso, **filtros):
        raise RuntimeError("Olinda fora do ar")

    monkeypatch.setattr(bcb_olinda, "buscar_focus", buscar_que_falha)
    resumo = bcb_olinda.expectativas_do_focus()

    assert resumo["disponivel"] is False
    assert "Olinda fora do ar" in resumo["motivo"]
    assert resumo["ipca_12_meses"] is None


# -------------------------------- endpoint ---------------------------------

def _focus_falso():
    return {
        "disponivel": True,
        "motivo": None,
        "ipca_12_meses": {"indicador": "IPCA", "data": bcb_olinda.date(2026, 10, 9), "mediana": 4.4757,
                          "media": 4.5, "minimo": 2.75, "maximo": 6.22, "respondentes": 132, "referencia": None},
        "igpm_12_meses": {"indicador": "IGP-M", "data": bcb_olinda.date(2026, 10, 9), "mediana": 4.6584,
                          "media": None, "minimo": None, "maximo": None, "respondentes": 62, "referencia": None},
        "ipca_anual": {"indicador": "IPCA", "data": bcb_olinda.date(2026, 10, 9), "mediana": 5.2245,
                       "media": None, "minimo": 4.5, "maximo": 5.88, "respondentes": 144, "referencia": "2026"},
        "selic": {"indicador": "Selic", "data": bcb_olinda.date(2026, 10, 9), "mediana": 10.5,
                  "media": None, "minimo": 8.5, "maximo": 12.0, "respondentes": 32, "referencia": "R6/2028"},
    }


def test_endpoint_expectativas_compara_com_o_realizado(api, monkeypatch):
    monkeypatch.setattr(router_expectativas, "expectativas_do_focus", _focus_falso)

    r = api.get("/expectativas")
    assert r.status_code == 200

    corpo = r.json()
    assert corpo["disponivel"] is True
    assert corpo["ipca_12_meses"]["mediana"] == 4.4757
    assert corpo["ipca_12_meses"]["respondentes"] == 132
    assert corpo["selic"]["referencia"] == "R6/2028"
    assert corpo["realizado_ipca_12m"] is not None
    esperado = corpo["ipca_12_meses"]["mediana"] - corpo["realizado_ipca_12m"]
    assert corpo["diferenca_pp"] == pytest.approx(esperado, abs=1e-4)
    assert "Focus" in corpo["fonte"]


def test_endpoint_expectativas_degrada_sem_o_olinda(api, monkeypatch):
    monkeypatch.setattr(router_expectativas, "expectativas_do_focus", lambda: {
        "disponivel": False,
        "motivo": "timeout no Olinda",
        "ipca_12_meses": None,
        "igpm_12_meses": None,
        "ipca_anual": None,
        "selic": None,
    })

    r = api.get("/expectativas")
    assert r.status_code == 200, "o Olinda fora do ar não pode derrubar o painel"
    corpo = r.json()
    assert corpo["disponivel"] is False
    assert corpo["motivo"] == "timeout no Olinda"
    assert corpo["ipca_12_meses"] is None
    assert corpo["diferenca_pp"] is None
