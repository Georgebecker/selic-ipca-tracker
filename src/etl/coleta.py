"""Orquestração da coleta: busca as séries no SGS, normaliza e grava no banco.

A busca é paralela (rede em threads) e a gravação é sequencial: o SQLite aceita um
escritor por vez, então paralelizar a escrita só criaria contenção e "database is
locked". Com as 12 séries, isso derruba a coleta de ~3,5 min para dezenas de segundos.

Uso:
  python -m src.etl.coleta                    # todas as séries
  python -m src.etl.coleta --series 433,189   # apenas algumas
  python -m src.etl.coleta --workers 8        # ajusta o paralelismo
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import pandas as pd

from src.db.models import Serie
from src.db.repository import (
    abrir_sessao,
    listar_series,
    registrar_atualizacao,
    salvar_valores,
    semear_series,
)
from src.etl.bcb_sgs import buscar_serie
from src.etl.limpeza import limpar_serie, registros_para_banco

# A API do BCB recusa janelas maiores que 10 anos em séries diárias (o cliente
# divide em janelas de 9 anos). Aqui fica só a profundidade do histórico coletado,
# conforme o `inicio_alvo` de cada série em
# meu-loop-agente/referencias_oficiais.json: mensais desde 2005 e diárias desde 2010
# (20 anos de série mensal). Disponibilidade conferida no SGS antes de aprofundar.
INICIO_MENSAL = date(2005, 1, 1)
INICIO_DIARIO = date(2010, 1, 1)

# 6 threads: medido nesta maquina (12 series, historico completo) — sequencial ~9 s,
# 6 threads ~5 s em execucao quente; a primeira carga do historico caiu de 201 s para
# 73 s. Acima de 6 o ganho fica dentro do ruido da rede e so aumenta a carga no BCB.
WORKERS_PADRAO = 6


def periodo_de_coleta(periodicidade: str | None, hoje: date | None = None) -> tuple[date, date]:
    """Período de coleta conforme a periodicidade da série."""
    referencia = hoje or date.today()
    inicio = INICIO_DIARIO if (periodicidade or "").lower().startswith("diar") else INICIO_MENSAL
    return inicio, referencia


def baixar_serie(codigo_sgs: int, periodicidade: str | None, hoje: date | None = None) -> pd.DataFrame:
    """Baixa e normaliza uma série (parte de rede — segura para rodar em thread)."""
    de, ate = periodo_de_coleta(periodicidade, hoje)
    return limpar_serie(buscar_serie(codigo_sgs, de, ate))


def coletar_serie(sessao, serie: Serie, hoje: date | None = None) -> int:
    """Coleta e grava uma série, sozinha. Devolve quantos valores foram gravados."""
    quadro = baixar_serie(serie.codigo_sgs, serie.periodicidade, hoje)
    if quadro.empty:
        return 0
    return salvar_valores(sessao, serie.id, registros_para_banco(quadro))


def _baixar_em_paralelo(
    series: Iterable[Serie],
    hoje: date,
    workers: int,
    avisar: Callable[[str], None] | None = None,
) -> tuple[dict[int, pd.DataFrame], dict[str, str]]:
    """Baixa as séries em paralelo. Devolve (quadros por código, falhas por código)."""
    quadros: dict[int, pd.DataFrame] = {}
    falhas: dict[str, str] = {}
    lista = list(series)
    total = len(lista)
    concluidas = 0

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futuros = {
            pool.submit(baixar_serie, serie.codigo_sgs, serie.periodicidade, hoje): serie
            for serie in lista
        }
        for futuro in as_completed(futuros):
            serie = futuros[futuro]
            concluidas += 1
            try:
                quadro = futuro.result()
                quadros[serie.codigo_sgs] = quadro
                if avisar:
                    avisar(
                        "[%d/%d] série %s: %d valores"
                        % (concluidas, total, serie.codigo_sgs, len(quadro))
                    )
            except Exception as erro:  # noqa: BLE001 - a falha de uma série não derruba as outras
                falhas[str(serie.codigo_sgs)] = str(erro)
                if avisar:
                    avisar("[%d/%d] série %s FALHOU: %s" % (concluidas, total, serie.codigo_sgs, erro))

    return quadros, falhas


def atualizar_todas(
    tipo: str = "manual",
    codigos: list[int] | None = None,
    workers: int = WORKERS_PADRAO,
    avisar: Callable[[str], None] | None = None,
    tentativas_extras: int = 1,
) -> dict:
    """Coleta as séries pedidas (ou todas) e registra o resultado em `atualizacoes`.

    Quem falhar na primeira passada é tentado de novo (a API do BCB devolve resposta
    vazia de vez em quando); a segunda tentativa vai com menos threads para não insistir
    em rajada.
    """
    with abrir_sessao() as sessao:
        semear_series(sessao)
        series = listar_series(sessao)
        if codigos:
            desejados = {int(codigo) for codigo in codigos}
            series = [item for item in series if item.codigo_sgs in desejados]

        hoje = date.today()
        quadros, falhas = _baixar_em_paralelo(series, hoje, workers, avisar)

        for tentativa in range(tentativas_extras):
            if not falhas:
                break
            pendentes = [item for item in series if str(item.codigo_sgs) in falhas]
            if avisar:
                avisar(
                    "retentando %d série(s) que falharam (tentativa %d)"
                    % (len(pendentes), tentativa + 2)
                )
            quadros_novos, falhas_restantes = _baixar_em_paralelo(
                pendentes, hoje, max(1, workers // 2), avisar
            )
            quadros.update(quadros_novos)
            falhas = falhas_restantes

        # Gravação sequencial: um escritor só, na ordem das séries.
        gravados: dict[str, int] = {}
        for serie in series:
            quadro = quadros.get(serie.codigo_sgs)
            if quadro is None or quadro.empty:
                continue
            gravados[str(serie.codigo_sgs)] = salvar_valores(
                sessao, serie.id, registros_para_banco(quadro)
            )

        if not series or (falhas and not gravados):
            status = "erro"
        elif falhas:
            status = "parcial"
        else:
            status = "sucesso"

        mensagem = None
        if falhas:
            mensagem = "; ".join(
                "%s: %s" % (codigo, texto) for codigo, texto in sorted(falhas.items())
            )
        registrar_atualizacao(sessao, tipo, len(gravados), status, mensagem)

    return {
        "status": status,
        "series_atualizadas": len(gravados),
        "valores_gravados": gravados,
        "falhas": falhas,
    }


def main() -> int:
    analisador = argparse.ArgumentParser(
        description="Coleta as séries do BCB/SGS e grava no banco do projeto."
    )
    analisador.add_argument(
        "--series", default="", help="códigos SGS separados por vírgula (padrão: todas)"
    )
    analisador.add_argument(
        "--workers", type=int, default=WORKERS_PADRAO,
        help="quantas séries baixar em paralelo (padrão: %d)" % WORKERS_PADRAO,
    )
    analisador.add_argument(
        "--tentativas-extras", type=int, default=1,
        help="quantas vezes retentar as séries que falharam (padrão: 1)",
    )
    argumentos = analisador.parse_args()

    codigos = (
        [int(item) for item in argumentos.series.split(",") if item.strip()]
        if argumentos.series
        else None
    )

    resultado = atualizar_todas(
        tipo="manual", codigos=codigos, workers=argumentos.workers,
        avisar=lambda texto: print("   " + texto),
        tentativas_extras=argumentos.tentativas_extras,
    )
    print("status: " + resultado["status"])
    print("séries atualizadas: %d" % resultado["series_atualizadas"])
    for codigo, total in sorted(resultado["valores_gravados"].items(), key=lambda item: int(item[0])):
        print("  - série %s: %d valores gravados" % (codigo, total))
    for codigo, texto in sorted(resultado["falhas"].items()):
        print("  ! série %s falhou: %s" % (codigo, texto))

    return 1 if resultado["falhas"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
