#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""medir_qualidade.py - metrica principal do Loop do selic-ipca-tracker.

Formula: score_qualidade = cobertura x precisao

- cobertura: fracao das series acompanhadas que tem dados recentes no banco.
- precisao:  1 - (erro medio das validacoes / tolerancia), comparando o acumulado
             calculado pelo projeto com os valores oficiais de
             `referencias_oficiais.json`.

Uso:
  python meu-loop-agente/medir_qualidade.py
  python meu-loop-agente/medir_qualidade.py --detalhe

Saida minima (lida pela regex de config_loop.json):
  score_qualidade: 0.8333

Este arquivo NAO pertence ao escopo do agente: fica em meu-loop-agente/.
Sem emojis de proposito: compatibilidade com o console do Windows.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
PROJETO = RAIZ.parent
ARQ_REFERENCIAS = RAIZ / "referencias_oficiais.json"

sys.path.insert(0, str(PROJETO))


def falhar(mensagem: str) -> None:
    print("[erro] " + mensagem)
    raise SystemExit(1)


def carregar_referencias() -> dict:
    if not ARQ_REFERENCIAS.exists():
        falhar("nao encontrei o arquivo " + ARQ_REFERENCIAS.name)
    try:
        return json.loads(ARQ_REFERENCIAS.read_text(encoding="utf-8"))
    except json.JSONDecodeError as erro:
        falhar(
            "referencias_oficiais.json tem erro de formato na linha "
            + str(erro.lineno) + ": " + erro.msg
        )


def abrir_banco() -> sqlite3.Connection:
    """Abre o banco do projeto usando a mesma configuracao do codigo (src/config.py)."""
    try:
        from src.config import caminho_do_banco
    except Exception as erro:  # noqa: BLE001 - queremos a mensagem crua no console
        falhar("nao consegui importar src.config: " + repr(erro))

    caminho = caminho_do_banco()
    if not caminho.exists():
        falhar(
            "banco de dados nao encontrado em " + str(caminho)
            + " - rode a coleta: python -m src.etl.coleta"
        )
    conexao = sqlite3.connect(str(caminho))
    conexao.row_factory = sqlite3.Row
    return conexao


def valores_da_serie(conexao: sqlite3.Connection, codigo_sgs: int) -> list[tuple[date, float]]:
    """Valores (data, valor) da serie, em ordem cronologica."""
    linhas = conexao.execute(
        "SELECT v.data, v.valor FROM valores v "
        "JOIN series s ON s.id = v.serie_id "
        "WHERE s.codigo_sgs = ? AND v.valor IS NOT NULL "
        "ORDER BY v.data",
        (int(codigo_sgs),),
    ).fetchall()

    valores = []
    for data_bruta, valor in linhas:
        try:
            dia = date.fromisoformat(str(data_bruta)[:10])
        except ValueError:
            continue
        valores.append((dia, float(valor)))
    return valores


def acumular_percentual(valores: list[tuple[date, float]]) -> float:
    """Acumula taxas percentuais mensais usando o calculo do proprio projeto."""
    from src.analise.calculos import acumular

    taxas = [valor / 100.0 for _, valor in valores]
    return acumular(taxas) * 100.0


def medir_cobertura(conexao: sqlite3.Connection, referencias: dict):
    acompanhadas = referencias.get("series_acompanhadas", [])
    dias_max = int(referencias.get("dias_max_para_considerar_recente", 75))
    min_valores = int(referencias.get("min_valores_por_serie", 12))
    limite = date.today() - timedelta(days=dias_max)

    codigos = [int(item["codigo_sgs"]) for item in acompanhadas]
    if not codigos:
        falhar("referencias_oficiais.json nao lista nenhuma serie acompanhada")

    marcadores = ",".join("?" * len(codigos))
    linhas = conexao.execute(
        "SELECT s.codigo_sgs AS codigo, COUNT(v.valor) AS total, MAX(v.data) AS ultima "
        "FROM series s LEFT JOIN valores v ON v.serie_id = s.id "
        "WHERE s.codigo_sgs IN (" + marcadores + ") "
        "GROUP BY s.codigo_sgs",
        codigos,
    ).fetchall()
    situacao = {int(linha["codigo"]): linha for linha in linhas}

    validadas, sem_dados = [], []
    for codigo in codigos:
        linha = situacao.get(codigo)
        total = int(linha["total"]) if linha else 0
        ultima = None
        if linha and linha["ultima"]:
            try:
                ultima = date.fromisoformat(str(linha["ultima"])[:10])
            except ValueError:
                ultima = None
        if total >= min_valores and ultima is not None and ultima >= limite:
            validadas.append((codigo, total, ultima))
        else:
            sem_dados.append((codigo, total, ultima))

    cobertura = len(validadas) / len(codigos) if codigos else 0.0
    return cobertura, validadas, sem_dados


def avaliar_validacao(conexao: sqlite3.Connection, validacao: dict):
    """Devolve (erro_pp, detalhe). erro_pp None quando nao foi possivel validar."""
    tipo = validacao.get("tipo")
    oficial = validacao.get("valor_oficial")

    if tipo == "periodo":
        codigo = int(validacao["codigo_sgs"])
        de = date.fromisoformat(str(validacao["de"])[:10])
        ate = date.fromisoformat(str(validacao["ate"])[:10])
        valores = [item for item in valores_da_serie(conexao, codigo) if de <= item[0] <= ate]
        if not valores:
            return None, "sem valores da serie " + str(codigo) + " no periodo"
        nosso = acumular_percentual(valores)
        if oficial is None:
            return None, "valor_oficial ausente no arquivo de referencias"
        return abs(nosso - float(oficial)), (
            "nosso %.4f%% x oficial %.4f%% (%d meses)"
            % (nosso, float(oficial), len(valores))
        )

    if tipo == "acumulado_12m":
        codigo = int(validacao["codigo_sgs"])
        codigo_oficial = int(validacao["comparar_com"])
        valores = valores_da_serie(conexao, codigo)
        oficiais = valores_da_serie(conexao, codigo_oficial)
        if len(valores) < 12:
            return None, "a serie " + str(codigo) + " tem menos de 12 valores"
        if not oficiais:
            return None, "sem valores da serie oficial " + str(codigo_oficial)

        janela = valores[-12:]
        fim_janela = janela[-1][0]
        candidatos = [item for item in oficiais if item[0] <= fim_janela]
        if not candidatos:
            return None, "a serie oficial " + str(codigo_oficial) + " nao cobre " + str(fim_janela)
        referencia = candidatos[-1]

        nosso = acumular_percentual(janela)
        return abs(nosso - referencia[1]), (
            "nosso %.4f%% x oficial %.4f%% ate %s"
            % (nosso, referencia[1], referencia[0].isoformat())
        )

    return None, "tipo de validacao desconhecido: " + str(tipo)


def medir_precisao(conexao: sqlite3.Connection, referencias: dict):
    tolerancia = float(referencias.get("tolerancia_pp", 0.05))
    if tolerancia <= 0:
        falhar("tolerancia_pp precisa ser maior que zero")

    erros, detalhes = [], []
    for validacao in referencias.get("validacoes", []):
        erro, detalhe = avaliar_validacao(conexao, validacao)
        nome = str(validacao.get("nome", "validacao"))
        if erro is None:
            erros.append(tolerancia)
            detalhes.append((nome, tolerancia, "nao validado: " + detalhe))
        else:
            erros.append(erro)
            detalhes.append((nome, erro, detalhe))

    if not erros:
        return 0.0, 0.0, detalhes

    erro_medio = sum(erros) / len(erros)
    precisao = max(0.0, 1.0 - erro_medio / tolerancia)
    return precisao, erro_medio, detalhes


def main() -> int:
    analisador = argparse.ArgumentParser(description="Mede o score_qualidade do Loop.")
    analisador.add_argument("--detalhe", action="store_true", help="mostra cada verificacao")
    argumentos = analisador.parse_args()

    referencias = carregar_referencias()
    conexao = abrir_banco()
    try:
        cobertura, validadas, sem_dados = medir_cobertura(conexao, referencias)
        precisao, erro_medio, detalhes = medir_precisao(conexao, referencias)
    finally:
        conexao.close()

    score = cobertura * precisao
    tolerancia = float(referencias.get("tolerancia_pp", 0.05))

    print("score_qualidade: %.4f" % score)
    print("cobertura: %.4f (%d/%d series com dados recentes)"
          % (cobertura, len(validadas), len(validadas) + len(sem_dados)))
    print("precisao: %.4f (erro medio %.4f p.p. | tolerancia %.4f p.p.)"
          % (precisao, erro_medio, tolerancia))

    if argumentos.detalhe:
        print("")
        print("series validadas:")
        for codigo, total, ultima in validadas:
            print("  - %s: %d valores, ultimo em %s" % (codigo, total, ultima.isoformat()))
        if sem_dados:
            print("series sem dados recentes:")
            for codigo, total, ultima in sem_dados:
                print("  - %s: %d valores, ultimo em %s"
                      % (codigo, total, ultima.isoformat() if ultima else "nenhum"))
        print("verificacoes de precisao:")
        for nome, erro, detalhe in detalhes:
            print("  - %s: erro %.4f p.p. (%s)" % (nome, erro, detalhe))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
