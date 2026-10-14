"""Cálculos financeiros: acumulação, correção, equivalência e médias."""

from __future__ import annotations

import pytest

from src.analise.calculos import (
    acumular,
    acumulado_12m,
    corrigir,
    deflacionar,
    equivalente_anual,
    equivalente_mensal,
    fator_acumulado,
    media_movel,
    variacao_percentual,
)

IPCA_2024 = [0.42, 0.83, 0.16, 0.38, 0.46, 0.21, 0.38, -0.02, 0.44, 0.56, 0.39, 0.52]


def test_acumular_taxas():
    # [(1+0.01)*(1+0.02)*(1+0.03)] - 1 ~= 0.0611
    assert round(acumular([0.01, 0.02, 0.03]), 4) == 0.0611


def test_corrigir_valor():
    # 1000 reais corrigidos por 6.11% ~= 1061.10
    assert round(corrigir(1000, 0.0611), 2) == 1061.10


def test_fator_acumulado_e_o_inverso_da_correcao():
    assert corrigir(500, fator_acumulado([0.1]) - 1.0) == pytest.approx(550.0)


def test_acumulado_12m_com_o_ipca_de_2024():
    # IPCA de 2024 divulgado pelo BCB: 4,83% no ano.
    assert round(acumulado_12m([taxa / 100 for taxa in IPCA_2024]) * 100, 2) == 4.83


def test_acumulado_12m_exige_doze_taxas():
    with pytest.raises(ValueError):
        acumulado_12m([0.01] * 11)


def test_taxa_equivalente_anual_para_mensal():
    # 12% a.a. -> ~0.9489% a.m.
    assert round(equivalente_mensal(0.12), 4) == 0.0095


def test_taxa_equivalente_mensal_para_anual():
    assert round(equivalente_anual(0.01), 4) == 0.1268


def test_variacao_percentual():
    assert variacao_percentual(100, 150) == pytest.approx(50.0)


def test_variacao_percentual_com_base_zero_falha():
    with pytest.raises(ValueError):
        variacao_percentual(0, 10)


def test_deflacionar_mostra_a_perda_para_a_inflacao():
    assert round(deflacionar(1000, 0.10), 2) == 909.09


def test_media_movel():
    assert media_movel([1, 2, 3, 4], 2) == [None, 1.5, 2.5, 3.5]


def test_media_movel_com_janela_invalida():
    with pytest.raises(ValueError):
        media_movel([1, 2, 3], 0)
