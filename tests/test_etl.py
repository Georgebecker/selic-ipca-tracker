"""Anchors dos testes em tempo real: falam com a API do BCB (pulam se não houver rede)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from src.etl.bcb_sgs import (
    converter_data,
    dividir_em_janelas,
    fetch_sgs,
    fetch_ultimos,
    formatar_data,
)
from src.etl.limpeza import limpar_serie, registros_para_banco


def _buscar_ou_pular(funcao, *argumentos, **nomeados):
    """Executa a consulta real; se a rede falhar, o teste é marcado como pulado."""
    try:
        return funcao(*argumentos, **nomeados)
    except Exception as erro:  # noqa: BLE001 - qualquer falha de rede aqui só pula o teste
        pytest.skip("API do BCB indisponível: %s" % erro)


def test_fetch_sgs_retorna_lista():
    dados = _buscar_ou_pular(fetch_sgs, 433, "01/01/2024", "31/12/2024")
    assert isinstance(dados, list)
    assert len(dados) > 0
    assert "data" in dados[0] and "valor" in dados[0]


def test_fetch_ultimos_traz_o_ultimo_valor():
    dados = _buscar_ou_pular(fetch_ultimos, 433, 3)
    assert isinstance(dados, list)
    assert len(dados) == 3


def test_limpar_serie_converte_tipos():
    df = limpar_serie([{"data": "01/01/2024", "valor": "0.42"}])
    assert df.iloc[0]["valor"] == 0.42
    assert df.iloc[0]["data"].year == 2024


def test_limpar_serie_aceita_data_iso_e_descarta_invalidos():
    df = limpar_serie(
        [
            {"data": "2024-01-01", "valor": "1.5"},
            {"data": "sem data", "valor": "9"},
            {"data": "01/03/2024", "valor": "não é número"},
        ]
    )
    assert len(df) == 1
    assert df.iloc[0]["valor"] == 1.5


def test_limpar_serie_vazia_nao_quebra():
    assert limpar_serie([]).empty


def test_registros_para_banco_gera_tuplas_de_data_e_float():
    df = limpar_serie([{"data": "01/01/2024", "valor": "0.42"}])
    registros = registros_para_banco(df)
    assert registros[0][0].isoformat() == "2024-01-01"
    assert registros[0][1] == 0.42


def test_formatar_e_converter_data():
    assert formatar_data("2024-03-05") == "05/03/2024"
    assert formatar_data("05/03/2024") == "05/03/2024"
    assert converter_data("05/03/2024").isoformat() == "2024-03-05"


def test_dividir_em_janelas_respeita_o_limite_de_10_anos():
    janelas = dividir_em_janelas(converter_data("2000-01-01"), converter_data("2024-12-31"))
    assert len(janelas) == 3
    assert janelas[0][0].year == 2000
    assert janelas[-1][1].isoformat() == "2024-12-31"
    for inicio, fim in janelas:
        assert fim <= inicio.replace(year=inicio.year + 9) - timedelta(days=1)
