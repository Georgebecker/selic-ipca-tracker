"""Comparação entre índices e montagem dos KPIs do dashboard."""

from __future__ import annotations

from datetime import date

from src.analise.calculos import acumular

# Indicadores exibidos na interface: série do valor corrente e série do acumulado.
INDICADORES: dict[str, dict] = {
    "selic": {
        "nome": "Selic",
        "codigo_sgs": 432,          # Selic meta (% a.a., diária)
        "codigo_acumulado": 4390,   # Selic acumulada no mês (%)
        "codigo_oficial": None,
    },
    "ipca": {
        "nome": "IPCA",
        "codigo_sgs": 433,
        "codigo_acumulado": 433,
        "codigo_oficial": 13522,    # IPCA acumulado 12 meses (BCB)
    },
    "igpm": {
        "nome": "IGP-M",
        "codigo_sgs": 189,
        "codigo_acumulado": 189,
        "codigo_oficial": None,
    },
    "inpc": {
        "nome": "INPC",
        "codigo_sgs": 188,
        "codigo_acumulado": 188,
        "codigo_oficial": None,
    },
}


def resumo_indicador(
    valores: list[tuple[date, float]],
    valores_do_acumulado: list[tuple[date, float]] | None = None,
    acumulado_oficial: float | None = None,
) -> dict:
    """Atual, variação mensal (p.p.) e acumulado 12 meses de um indicador.

    `valores` traz as taxas mensais; quando o indicador é uma taxa anualizada
    (Selic meta), `valores_do_acumulado` traz a série mensal correspondente.
    """
    if not valores:
        return {
            "atual": None,
            "data": None,
            "variacao_mensal_pp": None,
            "acumulado_12m": None,
            "acumulado_12m_oficial": acumulado_oficial,
        }

    ordenados = sorted(valores, key=lambda item: item[0])
    ultimo_dia, ultimo_valor = ordenados[-1]
    variacao = None
    if len(ordenados) >= 2:
        variacao = round(ultimo_valor - ordenados[-2][1], 4)

    base = sorted(valores_do_acumulado or valores, key=lambda item: item[0])
    acumulado = None
    if len(base) >= 12:
        acumulado = round(acumular([valor / 100.0 for _, valor in base[-12:]]) * 100.0, 4)

    return {
        "atual": round(ultimo_valor, 4),
        "data": ultimo_dia,
        "variacao_mensal_pp": variacao,
        "acumulado_12m": acumulado,
        "acumulado_12m_oficial": acumulado_oficial,
    }


def serie_para_grafico(
    valores: list[tuple[date, float]],
    de: date | None = None,
    ate: date | None = None,
) -> list[dict]:
    """Lista de pontos prontos para o gráfico, com filtro de período opcional."""
    pontos = [
        {"data": dia, "valor": valor}
        for dia, valor in sorted(valores, key=lambda item: item[0])
        if (de is None or dia >= de) and (ate is None or dia <= ate)
    ]
    return pontos


def alinhar_por_mes(series: list[dict]) -> dict:
    """Alinha várias séries no mesmo eixo de meses (valor ou None).

    `series` é uma lista de dicionários com `codigo_sgs`, `nome` e `valores`
    (lista de tuplas data/valor).
    """
    eixo = sorted(
        {
            dia.replace(day=1)
            for item in series
            for dia, _ in item.get("valores", [])
        }
    )
    alinhadas = []
    for item in series:
        por_mes = {
            dia.replace(day=1): valor for dia, valor in item.get("valores", [])
        }
        alinhadas.append(
            {
                "codigo_sgs": item["codigo_sgs"],
                "nome": item.get("nome", ""),
                "unidade": item.get("unidade"),
                "valores": [por_mes.get(mes) for mes in eixo],
            }
        )
    return {
        "eixo": [mes.isoformat() for mes in eixo],
        "series": alinhadas,
    }
