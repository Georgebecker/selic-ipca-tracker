"""Orquestração da coleta: busca as séries no SGS, normaliza e grava no banco.

Uso:
  python -m src.etl.coleta                  # todas as séries
  python -m src.etl.coleta --series 433,189 # apenas algumas
"""

from __future__ import annotations

import argparse
from datetime import date

from src.db.models import Serie
from src.db.repository import abrir_sessao, listar_series, registrar_atualizacao, salvar_valores, semear_series
from src.etl.bcb_sgs import buscar_serie
from src.etl.limpeza import limpar_serie, registros_para_banco

# A API do BCB recusa janelas maiores que 10 anos em séries diárias (o cliente
# divide em janelas de 9 anos). Aqui fica só a profundidade do histórico coletado:
# mensais desde 2010 e diárias desde 2015, conforme o `inicio_alvo` de cada série
# em meu-loop-agente/referencias_oficiais.json.
INICIO_MENSAL = date(2010, 1, 1)
INICIO_DIARIO = date(2015, 1, 1)


def periodo_de_coleta(periodicidade: str | None, hoje: date | None = None) -> tuple[date, date]:
    """Período de coleta conforme a periodicidade da série."""
    referencia = hoje or date.today()
    inicio = INICIO_DIARIO if (periodicidade or "").lower().startswith("diar") else INICIO_MENSAL
    return inicio, referencia


def coletar_serie(sessao, serie: Serie, hoje: date | None = None) -> int:
    """Coleta e grava uma série. Devolve quantos valores foram gravados."""
    de, ate = periodo_de_coleta(serie.periodicidade, hoje)
    bruto = buscar_serie(serie.codigo_sgs, de, ate)
    quadro = limpar_serie(bruto)
    if quadro.empty:
        return 0
    return salvar_valores(sessao, serie.id, registros_para_banco(quadro))


def atualizar_todas(tipo: str = "manual", codigos: list[int] | None = None) -> dict:
    """Coleta as séries pedidas (ou todas) e registra o resultado em `atualizacoes`."""
    with abrir_sessao() as sessao:
        semear_series(sessao)
        series = listar_series(sessao)
        if codigos:
            desejados = {int(codigo) for codigo in codigos}
            series = [item for item in series if item.codigo_sgs in desejados]

        gravados: dict[str, int] = {}
        falhas: dict[str, str] = {}
        for serie in series:
            try:
                gravados[str(serie.codigo_sgs)] = coletar_serie(sessao, serie)
            except Exception as erro:  # noqa: BLE001 - a falha de uma série não derruba as outras
                falhas[str(serie.codigo_sgs)] = str(erro)

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
    argumentos = analisador.parse_args()

    codigos = (
        [int(item) for item in argumentos.series.split(",") if item.strip()]
        if argumentos.series
        else None
    )

    resultado = atualizar_todas(tipo="manual", codigos=codigos)
    print("status: " + resultado["status"])
    print("séries atualizadas: %d" % resultado["series_atualizadas"])
    for codigo, total in sorted(resultado["valores_gravados"].items(), key=lambda item: int(item[0])):
        print("  - série %s: %d valores" % (codigo, total))
    for codigo, texto in sorted(resultado["falhas"].items()):
        print("  ! série %s falhou: %s" % (codigo, texto))

    return 1 if resultado["falhas"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
