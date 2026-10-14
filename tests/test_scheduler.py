"""Coleta automática opcional: leitura das variáveis, contagem e ligar/desligar.

O agendador de verdade não sobe nos testes (seria uma thread chamando o BCB); o que se
testa é a decisão de ligar, o cálculo do próximo horário e a tolerância a falha.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.scheduler import timer


@pytest.fixture(autouse=True)
def limpar_variaveis(monkeypatch):
    for nome in (timer.VARIAVEL_LIGADA, timer.VARIAVEL_INTERVALO):
        monkeypatch.delenv(nome, raising=False)


def test_desligado_por_padrao():
    assert timer.coleta_automatica_ligada() is False
    assert timer.ligar_se_configurado() is None


@pytest.mark.parametrize("valor", ["1", "true", "TRUE", "sim", "yes", "on", " true "])
def test_formas_de_ligar(monkeypatch, valor):
    monkeypatch.setenv(timer.VARIAVEL_LIGADA, valor)
    assert timer.coleta_automatica_ligada() is True


@pytest.mark.parametrize("valor", ["0", "false", "nao", "off", "", "talvez"])
def test_formas_de_manter_desligado(monkeypatch, valor):
    monkeypatch.setenv(timer.VARIAVEL_LIGADA, valor)
    assert timer.coleta_automatica_ligada() is False


def test_intervalo_padrao_e_minimo_de_uma_hora(monkeypatch):
    assert timer.intervalo_horas() == 24

    monkeypatch.setenv(timer.VARIAVEL_INTERVALO, "6")
    assert timer.intervalo_horas() == 6

    monkeypatch.setenv(timer.VARIAVEL_INTERVALO, "0")
    assert timer.intervalo_horas() == 1, "intervalo zero deixaria o agendador em loop"

    monkeypatch.setenv(timer.VARIAVEL_INTERVALO, "abacaxi")
    assert timer.intervalo_horas() == 24, "valor inválido volta ao padrão"


def test_proxima_atualizacao_e_contagem():
    ultima = datetime(2026, 10, 14, 12, 0, 0)

    assert timer.proxima_atualizacao(None) is None
    assert timer.proxima_atualizacao(ultima) == ultima + timedelta(hours=24)
    assert timer.proxima_atualizacao(ultima, 6) == ultima + timedelta(hours=6)

    agora = ultima + timedelta(hours=20)
    assert timer.segundos_restantes(ultima, agora) == 4 * 3600
    assert timer.segundos_restantes(ultima, agora, intervalo=6) == 0, "já venceu: 0"
    assert timer.segundos_restantes(None) == 0


def test_ligar_usa_o_intervalo_configurado(monkeypatch):
    capturado = {}

    def agendador_falso(intervalo):
        capturado["intervalo"] = intervalo
        return "agendador-de-mentira"

    monkeypatch.setenv(timer.VARIAVEL_LIGADA, "true")
    monkeypatch.setenv(timer.VARIAVEL_INTERVALO, "8")
    monkeypatch.setattr(timer, "iniciar_agendador", agendador_falso)

    assert timer.ligar_se_configurado() == "agendador-de-mentira"
    assert capturado["intervalo"] == 8


def test_falha_ao_ligar_nao_derruba_a_aplicacao(monkeypatch):
    def agendador_que_explode(intervalo):
        raise RuntimeError("sem permissao para thread")

    monkeypatch.setenv(timer.VARIAVEL_LIGADA, "true")
    monkeypatch.setattr(timer, "iniciar_agendador", agendador_que_explode)

    assert timer.ligar_se_configurado() is None
