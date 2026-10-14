"""Fixtures dos testes: banco SQLite temporário, séries semeadas e cliente da API.

Os testes rodam offline: os dados usados vêm deste arquivo (IPCA de 2024 igual ao
divulgado oficialmente), não da API do BCB.
"""

from __future__ import annotations

import os
from datetime import date

import pytest

# IPCA mensal de 2024 (série 433), conforme divulgado pelo BCB: acumula 4,83% no ano.
IPCA_2024 = {
    date(2024, 1, 1): 0.42,
    date(2024, 2, 1): 0.83,
    date(2024, 3, 1): 0.16,
    date(2024, 4, 1): 0.38,
    date(2024, 5, 1): 0.46,
    date(2024, 6, 1): 0.21,
    date(2024, 7, 1): 0.38,
    date(2024, 8, 1): -0.02,
    date(2024, 9, 1): 0.44,
    date(2024, 10, 1): 0.56,
    date(2024, 11, 1): 0.39,
    date(2024, 12, 1): 0.52,
}

# IPCA acumulado 12 meses (série 13522) no fechamento de 2024.
IPCA_12_MESES = {date(2024, 12, 1): 4.83}

IGPM_2024 = {date(2024, mes, 1): 0.55 for mes in range(1, 13)}
INPC_2024 = {date(2024, mes, 1): 0.40 for mes in range(1, 13)}
SELIC_MES_2024 = {date(2024, mes, 1): 0.90 for mes in range(1, 13)}
SELIC_META = {date(2024, 1, 2): 11.75, date(2024, 12, 2): 12.25, date(2025, 1, 2): 12.25}
VALORES_AVULSOS = {
    12: {date(2024, 12, 2): 0.041},
    1: {date(2024, 12, 2): 6.05},
    7478: {date(2024, 12, 1): 0.34},
    192: {date(2024, 12, 1): 0.52},
    190: {date(2024, 12, 1): 0.60},
    25: {date(2024, 12, 1): 0.58},
}


@pytest.fixture(scope="session", autouse=True)
def banco_temporario(tmp_path_factory):
    """Aponta DB_URL para um SQLite temporário, cria o esquema e semeia os dados."""
    caminho = tmp_path_factory.mktemp("banco") / "selic_ipca_teste.db"
    os.environ["DB_URL"] = "sqlite:///" + caminho.as_posix()

    from src.db.repository import (
        abrir_sessao,
        obter_engine,
        salvar_valores,
        semear_series,
        serie_por_codigo,
    )

    obter_engine(reiniciar=True)

    with abrir_sessao() as sessao:
        semear_series(sessao)
        for codigo, valores in (
            (433, IPCA_2024),
            (13522, IPCA_12_MESES),
            (189, IGPM_2024),
            (188, INPC_2024),
            (4390, SELIC_MES_2024),
            (432, SELIC_META),
        ):
            serie = serie_por_codigo(sessao, codigo)
            salvar_valores(sessao, serie.id, sorted(valores.items()))

        for codigo, valores in VALORES_AVULSOS.items():
            serie = serie_por_codigo(sessao, codigo)
            salvar_valores(sessao, serie.id, sorted(valores.items()))

    yield caminho


@pytest.fixture(scope="session")
def api(banco_temporario):
    """Cliente de teste da API, com o ciclo de vida da aplicação ativo."""
    from fastapi.testclient import TestClient

    from src.api.main import app

    with TestClient(app) as cliente:
        yield cliente
