"""Coleta: paralelismo, tolerância a falha de uma série e gravação.

Os testes não tocam a rede (`src.etl.coleta.buscar_serie` é substituído) nem escrevem
nas séries do banco de fixture — a gravação é interceptada, e o único teste que grava
de verdade usa uma série dedicada (999901) criada por ele mesmo.
"""

from __future__ import annotations

import inspect
from datetime import date

import pytest

from src.db.models import Serie
from src.db.repository import abrir_sessao, salvar_valores, serie_por_codigo, valores_da_serie
from src.etl import coleta

SERIE_TESTE = 12  # CDI diário: nenhum outro teste depende dos valores dela
SERIE_DEDICADA = 999901

CODIGOS_PADRAO = {432, 4390, 433, 13522, 189, 188, 12, 1, 7478, 192, 190, 25}


def _registros_sinteticos(quantidade: int = 40) -> list[dict]:
    return [
        {"data": "01/%02d/2024" % ((indice % 12) + 1), "valor": "%.2f" % (indice / 100.0)}
        for indice in range(quantidade)
    ]


@pytest.fixture
def sem_rede(monkeypatch):
    """Substitui a busca no SGS por dados sintéticos e registra os códigos pedidos."""
    pedidos: list[int] = []

    def buscar_falso(codigo, data_inicial, data_final):
        pedidos.append(int(codigo))
        return _registros_sinteticos()

    monkeypatch.setattr(coleta, "buscar_serie", buscar_falso)
    return pedidos


@pytest.fixture
def sem_escrita(monkeypatch):
    """Intercepta a gravação: os testes não mexem nas séries do banco de fixture."""
    gravacoes: list[tuple[int, int]] = []

    def salvar_falso(sessao, serie_id, registros):
        lista = list(registros)
        gravacoes.append((int(serie_id), len(lista)))
        return len(lista)

    monkeypatch.setattr(coleta, "salvar_valores", salvar_falso)
    return gravacoes


def test_periodo_de_coleta_respeita_a_periodicidade():
    hoje = date(2026, 10, 14)
    assert coleta.periodo_de_coleta("diaria", hoje) == (coleta.INICIO_DIARIO, hoje)
    assert coleta.periodo_de_coleta("mensal", hoje) == (coleta.INICIO_MENSAL, hoje)
    assert coleta.periodo_de_coleta(None, hoje) == (coleta.INICIO_MENSAL, hoje)


def test_baixar_serie_normaliza_o_retorno(sem_rede):
    quadro = coleta.baixar_serie(433, "mensal")
    assert not quadro.empty
    assert list(quadro.columns) == ["data", "valor"]


def test_atualizar_uma_serie_conta_os_valores(sem_rede, sem_escrita):
    resultado = coleta.atualizar_todas(codigos=[SERIE_TESTE], workers=2)

    assert resultado["status"] == "sucesso"
    assert resultado["series_atualizadas"] == 1
    assert sem_rede == [SERIE_TESTE]
    assert len(sem_escrita) == 1


def test_atualizar_todas_baixa_as_series_padrao(sem_rede, sem_escrita):
    resultado = coleta.atualizar_todas(workers=4)

    assert resultado["status"] == "sucesso"
    assert resultado["falhas"] == {}
    assert CODIGOS_PADRAO.issubset(set(sem_rede)), "alguma série padrão não foi pedida"
    assert len(sem_rede) == len(set(sem_rede)), "série pedida duas vezes"
    assert resultado["series_atualizadas"] == len(sem_escrita)


def test_falha_de_uma_serie_nao_derruba_as_outras(monkeypatch, sem_escrita):
    def buscar_com_falha(codigo, data_inicial, data_final):
        if int(codigo) == SERIE_TESTE:
            raise RuntimeError("erro simulado da API")
        return _registros_sinteticos(quantidade=6)

    monkeypatch.setattr(coleta, "buscar_serie", buscar_com_falha)
    resultado = coleta.atualizar_todas(codigos=[SERIE_TESTE, 433, 189], workers=3)

    assert resultado["status"] == "parcial"
    assert str(SERIE_TESTE) in resultado["falhas"]
    assert "erro simulado" in resultado["falhas"][str(SERIE_TESTE)]
    assert resultado["series_atualizadas"] == 2


def test_aviso_de_progresso_e_chamado_por_serie(sem_rede, sem_escrita):
    mensagens: list[str] = []
    coleta.atualizar_todas(codigos=[SERIE_TESTE, 433], workers=2, avisar=mensagens.append)

    assert len(mensagens) == 2
    assert all("série" in texto for texto in mensagens)


def test_codigo_inexistente_nao_grava_nada(sem_rede):
    resultado = coleta.atualizar_todas(codigos=[999999], workers=1)

    assert resultado["status"] == "erro"
    assert resultado["series_atualizadas"] == 0
    with abrir_sessao() as sessao:
        assert serie_por_codigo(sessao, 999999) is None


def test_gravacao_real_em_serie_dedicada(sem_rede):
    """Grava de verdade, mas só na série dedicada criada aqui (nada mais é tocado)."""
    with abrir_sessao() as sessao:
        serie = serie_por_codigo(sessao, SERIE_DEDICADA)
        if serie is None:
            serie = Serie(
                codigo_sgs=SERIE_DEDICADA,
                nome="Serie de teste",
                unidade="%",
                periodicidade="mensal",
            )
            sessao.add(serie)
            sessao.flush()

    with abrir_sessao() as sessao:
        serie = serie_por_codigo(sessao, SERIE_DEDICADA)
        gravados = coleta.coletar_serie(sessao, serie)

    assert gravados > 0
    with abrir_sessao() as sessao:
        valores = valores_da_serie(sessao, SERIE_DEDICADA)
    assert len(valores) == gravados
    assert all(isinstance(item.valor, float) for item in valores)


def test_atualizar_todas_nao_depende_da_ordem_de_chegada(sem_rede, sem_escrita):
    """A gravação sai por série, mesmo com as respostas chegando fora de ordem."""
    resultado = coleta.atualizar_todas(codigos=[1, 12, 25], workers=3)

    assert resultado["status"] == "sucesso"
    assert set(resultado["valores_gravados"]) == {"1", "12", "25"}


def test_gravacao_continua_idempotente():
    """Guarda contra regressão: a gravação segue sendo upsert (INSERT ... ON CONFLICT)."""
    assert "sqlite_insert" in inspect.getsource(salvar_valores)
