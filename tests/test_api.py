"""Endpoints da API: séries, resumo, comparação, calculadora e timer."""

from __future__ import annotations

import time

import pytest


def test_endpoint_series(api):
    r = api.get("/series")
    assert r.status_code == 200
    assert len(r.json()) >= 4


def test_endpoint_resumo(api):
    r = api.get("/indicadores/resumo")
    assert r.status_code == 200
    assert "selic" in r.json()
    assert "ipca" in r.json()


def test_resumo_traz_o_acumulado_12_meses_do_ipca(api):
    corpo = api.get("/indicadores/resumo").json()
    # O acumulado calculado a partir das taxas mensais arredondadas fica a poucos
    # centésimos do valor oficial: e exatamente esse desvio que a metrica do Loop mede.
    assert corpo["ipca"]["acumulado_12m"] == pytest.approx(4.83, abs=0.01)
    assert corpo["ipca"]["acumulado_12m_oficial"] == 4.83
    assert corpo["ipca"]["atual"] == 0.52


def test_calculadora(api):
    r = api.post(
        "/calculadora/corrigir",
        json={
            "valor": 1000,
            "data_inicial": "2024-01-01",
            "data_final": "2024-12-31",
            "indice": "IPCA",
        },
    )
    assert r.status_code == 200
    corpo = r.json()
    assert "valor_corrigido" in corpo
    assert corpo["meses"] == 12
    assert corpo["valor_corrigido"] == 1048.31


def test_calculadora_periodo_invertido_falha(api):
    r = api.post(
        "/calculadora/corrigir",
        json={
            "valor": 1000,
            "data_inicial": "2024-12-31",
            "data_final": "2024-01-01",
            "indice": "IPCA",
        },
    )
    assert r.status_code == 422


def test_calculadora_indice_desconhecido_falha(api):
    r = api.post(
        "/calculadora/corrigir",
        json={
            "valor": 1000,
            "data_inicial": "2024-01-01",
            "data_final": "2024-12-31",
            "indice": "Tucano",
        },
    )
    assert r.status_code == 422


def test_calculadora_sem_dados_no_periodo_falha(api):
    r = api.post(
        "/calculadora/corrigir",
        json={
            "valor": 1000,
            "data_inicial": "1990-01-01",
            "data_final": "1990-12-31",
            "indice": "IPCA",
        },
    )
    assert r.status_code == 404


def test_endpoint_dados_da_serie_com_filtro(api):
    r = api.get("/series/433/dados", params={"de": "2024-01-01", "ate": "2024-06-30"})
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["total"] == 6
    assert corpo["valores"][0]["data"] == "2024-01-01"


def test_endpoint_ultimos_valores(api):
    r = api.get("/series/433/ultimos/3")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["total"] == 3
    assert corpo["valores"][-1]["valor"] == 0.52


def test_serie_inexistente_devolve_404(api):
    assert api.get("/series/9999/dados").status_code == 404
    assert api.get("/series/9999/ultimos/3").status_code == 404


def test_endpoint_comparacao_alinha_os_meses(api):
    r = api.get("/comparacao", params={"de": "2024-01-01", "series": "433,189"})
    assert r.status_code == 200
    corpo = r.json()
    assert len(corpo["eixo"]) == 12
    assert len(corpo["series"]) == 2
    assert corpo["series"][0]["valores"][0] == 0.42


def test_frontend_servido_pela_api(api):
    pagina = api.get("/app/")
    assert pagina.status_code == 200
    assert "selic-ipca-tracker" in pagina.text
    assert 'id="timer"' not in pagina.text, "o relógio de 24h não deve voltar"

    estilo = api.get("/app/style.css")
    assert estilo.status_code == 200
    assert "min-width: 0" in estilo.text

    script = api.get("/app/app.js")
    assert script.status_code == 200
    assert "acompanharColeta" in script.text


def test_endpoint_status(api):
    r = api.get("/status")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["intervalo_horas"] == 24
    assert corpo["series_monitoradas"] >= 4
    assert corpo["segundos_restantes"] >= 0
    assert "coleta" in corpo, "o /status precisa informar o progresso da coleta"
    assert corpo["coleta"]["em_andamento"] is False


def test_atualizar_roda_em_segundo_plano_e_reporta_progresso(api, monkeypatch):
    """POST /atualizar responde 202 na hora e o progresso aparece em GET /status."""
    from src.api import execucao

    execucao.reiniciar_estado()
    chamadas: list[int] = []

    def coletor_falso(tipo="manual", codigos=None, workers=1, avisar=None):
        chamadas.append(1)
        for indice in range(1, 4):
            time.sleep(0.05)
            if avisar:
                avisar("[%d/3] série %d: 5 valores" % (indice, indice))
        return {"status": "sucesso", "series_atualizadas": 3, "valores_gravados": {}, "falhas": {}}

    monkeypatch.setattr(execucao, "atualizar_todas", coletor_falso)

    try:
        resposta = api.post("/atualizar")
        assert resposta.status_code == 202, "a coleta em segundo plano responde 202, não 200"
        assert resposta.json()["em_andamento"] is True

        durante = api.get("/status").json()["coleta"]
        assert durante["em_andamento"] is True

        # O total só aparece quando a primeira série termina: espera o progresso chegar.
        limite = time.time() + 5
        while durante["total_series"] != 3 and time.time() < limite:
            time.sleep(0.05)
            durante = api.get("/status").json()["coleta"]
        assert durante["total_series"] == 3
        assert 0 <= durante["concluidas"] <= 3

        assert execucao.aguardar(timeout=10) is True

        depois = api.get("/status").json()["coleta"]
        assert depois["em_andamento"] is False
        assert depois["status"] == "sucesso"
        assert depois["concluidas"] == 3
        assert len(chamadas) == 1
    finally:
        execucao.reiniciar_estado()
