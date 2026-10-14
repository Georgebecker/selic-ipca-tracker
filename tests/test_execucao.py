"""Execução da coleta em segundo plano: progresso, uma por vez e falhas.

Nenhum teste toca a rede: `src.api.execucao.atualizar_todas` é substituído por um
coletor de mentira que avisa o progresso e respeita o tempo que o teste precisar.
"""

from __future__ import annotations

import time

import pytest

from src.api import execucao


@pytest.fixture(autouse=True)
def limpar_estado():
    execucao.reiniciar_estado()
    yield
    execucao.reiniciar_estado()


def _coletor_de_mentira(series: int = 3, atraso: float = 0.02):
    def atualizar(tipo="manual", codigos=None, workers=1, avisar=None):
        for indice in range(1, series + 1):
            time.sleep(atraso)
            if avisar:
                avisar("[%d/%d] série %d: 10 valores" % (indice, series, indice))
        return {
            "status": "sucesso",
            "series_atualizadas": series,
            "valores_gravados": {},
            "falhas": {},
        }

    return atualizar


def test_iniciar_e_concluir_registra_sucesso(monkeypatch):
    monkeypatch.setattr(execucao, "atualizar_todas", _coletor_de_mentira(3))

    iniciou, estado_inicial = execucao.iniciar()
    assert iniciou is True
    assert estado_inicial["em_andamento"] is True

    assert execucao.aguardar(timeout=10) is True

    final = execucao.estado()
    assert final["em_andamento"] is False
    assert final["status"] == "sucesso"
    assert final["concluidas"] == 3
    assert final["iniciado_em"] is not None
    assert final["finalizado_em"] is not None
    assert final["mensagem"] is None


def test_progresso_aparece_durante_a_execucao(monkeypatch):
    monkeypatch.setattr(execucao, "atualizar_todas", _coletor_de_mentira(4, atraso=0.15))

    execucao.iniciar()
    time.sleep(0.35)  # deixa pelo menos uma série passar

    durante = execucao.estado()
    assert durante["em_andamento"] is True
    assert durante["total_series"] == 4
    assert 0 < durante["concluidas"] < 4

    execucao.aguardar(timeout=10)


def test_segunda_chamada_nao_inicia_outra_coleta(monkeypatch):
    chamadas: list[int] = []

    def coletor_lento(tipo="manual", codigos=None, workers=1, avisar=None):
        chamadas.append(1)
        time.sleep(0.3)
        return {"status": "sucesso", "series_atualizadas": 1, "valores_gravados": {}, "falhas": {}}

    monkeypatch.setattr(execucao, "atualizar_todas", coletor_lento)

    primeiro, _ = execucao.iniciar()
    segundo, estado = execucao.iniciar()

    assert primeiro is True
    assert segundo is False, "a segunda chamada deveria apenas ler o progresso"
    assert estado["em_andamento"] is True

    execucao.aguardar(timeout=10)
    assert len(chamadas) == 1


def test_falha_do_coletor_vira_status_erro(monkeypatch):
    def coletor_que_falha(tipo="manual", codigos=None, workers=1, avisar=None):
        raise RuntimeError("sem rede")

    monkeypatch.setattr(execucao, "atualizar_todas", coletor_que_falha)

    execucao.iniciar()
    assert execucao.aguardar(timeout=10) is True

    final = execucao.estado()
    assert final["em_andamento"] is False
    assert final["status"] == "erro"
    assert "sem rede" in final["mensagem"]


def test_falhas_parciais_viram_mensagem(monkeypatch):
    def coletor_parcial(tipo="manual", codigos=None, workers=1, avisar=None):
        return {
            "status": "parcial",
            "series_atualizadas": 1,
            "valores_gravados": {},
            "falhas": {"189": "timeout"},
        }

    monkeypatch.setattr(execucao, "atualizar_todas", coletor_parcial)

    execucao.iniciar()
    execucao.aguardar(timeout=10)

    final = execucao.estado()
    assert final["status"] == "parcial"
    assert "189: timeout" in final["mensagem"]


def test_avisador_ignora_mensagem_fora_do_formato():
    recebido: list[tuple[int, int]] = []
    avisar = execucao.criar_avisador(lambda c, t: recebido.append((c, t)))

    avisar("[2/12] série 189: 201 valores")
    avisar("mensagem estranha sem progresso")
    avisar("[3/12] série 12 FALHOU: timeout")

    assert recebido == [(2, 12), (3, 12)]
