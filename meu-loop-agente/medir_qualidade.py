#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""medir_qualidade.py - metrica principal do Loop do selic-ipca-tracker.

Metrica (versao 2):
  score_qualidade = cobertura de itens atendidos / total de itens

  Cada serie-alvo vale 2 itens:
    1. dados_recentes     - tem pelo menos `min_valores_por_serie` valores e o
                            ultimo dentro de `dias_max_para_considerar_recente` dias;
    2. historico_completo - o primeiro valor e igual ou anterior a `inicio_alvo`
                            da serie (historico profundo para os graficos).

  A precisao dos acumulados (comparacao com as series oficiais) virou GUARDA:
  nao precisa melhorar, mas nao pode cair abaixo de `precisao_minima`. Se cair,
  o medidor sai com codigo 1 e a iteracao e REJEITADA pelo verificador.

Uso:
  python meu-loop-agente/medir_qualidade.py
  python meu-loop-agente/medir_qualidade.py --detalhe

Saida minima (lida pela regex de config_loop.json):
  score_qualidade: 0.5000

A regua (referencias_oficiais.json) e este arquivo ficam em meu-loop-agente/ e NAO
pertencem ao escopo do agente: sao eles que medem o agente.
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


def falhar(mensagem: str, codigo: int = 1) -> None:
    print("[erro] " + mensagem)
    raise SystemExit(codigo)


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
    except Exception as erro:  # noqa: BLE001 - a mensagem crua ajuda a diagnosticar
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
    for linha in linhas:
        try:
            dia = date.fromisoformat(str(linha["data"])[:10])
        except ValueError:
            continue
        valores.append((dia, float(linha["valor"])))
    return valores


def acumular_percentual(valores: list[tuple[date, float]]) -> float:
    """Acumula taxas percentuais mensais usando o calculo do proprio projeto."""
    from src.analise.calculos import acumular

    return acumular([valor / 100.0 for _, valor in valores]) * 100.0


def medir_cobertura(conexao: sqlite3.Connection, referencias: dict):
    """Devolve (cobertura, itens, atendidos, faltando) com o detalhe por serie."""
    series_alvo = referencias.get("series_alvo", [])
    if not series_alvo:
        falhar("referencias_oficiais.json nao lista nenhuma serie alvo")

    dias_max = int(referencias.get("dias_max_para_considerar_recente", 75))
    min_valores = int(referencias.get("min_valores_por_serie", 12))
    limite_recente = date.today() - timedelta(days=dias_max)

    itens = []
    atendidos = 0
    faltando = []

    for alvo in series_alvo:
        codigo = int(alvo["codigo_sgs"])
        nome = str(alvo.get("nome", codigo))
        inicio_alvo = date.fromisoformat(str(alvo["inicio_alvo"])[:10])
        valores = valores_da_serie(conexao, codigo)

        # item 1: dados recentes
        recente = (
            len(valores) >= min_valores
            and valores
            and valores[-1][0] >= limite_recente
        )
        detalhe_recente = (
            "ultimo valor em " + valores[-1][0].isoformat() if valores else "sem dados"
        ) + (" | " + str(len(valores)) + " valores")

        # item 2: historico completo
        primeiro = valores[0][0] if valores else None
        historico = primeiro is not None and primeiro <= inicio_alvo
        detalhe_historico = (
            "primeiro valor em " + primeiro.isoformat() + " (alvo: "
            + inicio_alvo.isoformat() + ")"
            if primeiro
            else "sem dados"
        )

        for item, ok, detalhe in (
            ("dados_recentes", recente, detalhe_recente),
            ("historico_completo", historico, detalhe_historico),
        ):
            itens.append(
                {"codigo_sgs": codigo, "nome": nome, "item": item, "atendido": bool(ok),
                 "detalhe": detalhe}
            )
            if ok:
                atendidos += 1
            else:
                faltando.append((codigo, nome, item, detalhe))

    total = len(itens)
    cobertura = atendidos / total if total else 0.0
    return cobertura, total, atendidos, faltando


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
        fim = janela[-1][0]
        candidatos = [item for item in oficiais if item[0] <= fim]
        if not candidatos:
            return None, "a serie oficial nao cobre " + fim.isoformat()
        referencia = candidatos[-1]

        nosso = acumular_percentual(janela)
        return abs(nosso - referencia[1]), (
            "nosso %.4f%% x oficial %.4f%% ate %s"
            % (nosso, referencia[1], referencia[0].isoformat())
        )

    if tipo == "anual_oficial":
        codigo = int(validacao["codigo_sgs"])
        codigo_oficial = int(validacao["comparar_com"])
        ano = int(validacao["ano"])
        valores = [item for item in valores_da_serie(conexao, codigo) if item[0].year == ano]
        if len(valores) < 12:
            return None, "a serie " + str(codigo) + " nao tem 12 meses em " + str(ano)

        oficiais = valores_da_serie(conexao, codigo_oficial)
        candidatos = [item for item in oficiais if item[0].year == ano]
        if not candidatos:
            return None, "a serie oficial " + str(codigo_oficial) + " nao cobre " + str(ano)
        referencia = candidatos[-1]

        nosso = acumular_percentual(valores[:12])
        return abs(nosso - referencia[1]), (
            "%d: nosso %.4f%% x oficial %.2f%%"
            % (ano, nosso, referencia[1])
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
    analisador.add_argument("--detalhe", action="store_true", help="mostra cada item e validacao")
    argumentos = analisador.parse_args()

    referencias = carregar_referencias()
    conexao = abrir_banco()
    try:
        cobertura, total, atendidos, faltando = medir_cobertura(conexao, referencias)
        precisao, erro_medio, detalhes = medir_precisao(conexao, referencias)
    finally:
        conexao.close()

    tolerancia = float(referencias.get("tolerancia_pp", 0.05))
    precisao_minima = float(referencias.get("precisao_minima", 0.9))

    print("score_qualidade: %.4f" % cobertura)
    print("cobertura: %.4f (%d/%d itens atendidos)" % (cobertura, atendidos, total))
    print("precisao (guarda): %.4f (erro medio %.4f p.p. | tolerancia %.4f p.p. | minimo %.2f)"
          % (precisao, erro_medio, tolerancia, precisao_minima))

    if argumentos.detalhe:
        print("")
        print("itens faltando (o que o agente pode melhorar):")
        if not faltando:
            print("  (nenhum: cobertura completa)")
        for codigo, nome, item, detalhe in faltando:
            print("  - %s (%s) -> %s: %s" % (nome, codigo, item, detalhe))
        print("")
        print("validacoes de precisao:")
        for nome, erro, detalhe in detalhes:
            print("  - %s: erro %.4f p.p. (%s)" % (nome, erro, detalhe))

    if precisao < precisao_minima:
        print("")
        print("guarda_de_precisao: REPROVADA (precisao %.4f abaixo do minimo %.2f)"
              % (precisao, precisao_minima))
        return 1

    print("guarda_de_precisao: aprovada")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
