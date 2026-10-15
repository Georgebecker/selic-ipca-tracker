"""Fórmulas financeiras do projeto.

Todas as taxas são decimais: 0,5% = 0.005.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence


def fator_acumulado(taxas: Iterable[float]) -> float:
    """Produto de (1 + i) para cada taxa — o fator de correção do período."""
    fator = 1.0
    for taxa in taxas:
        fator *= 1.0 + float(taxa)
    return fator


def acumular(taxas: Iterable[float]) -> float:
    """Acumula taxas decimais: produto(1 + i) - 1."""
    return fator_acumulado(taxas) - 1.0


def corrigir(valor: float, taxa_acumulada: float) -> float:
    """Corrige um valor por uma taxa acumulada: valor x (1 + taxa)."""
    return float(valor) * (1.0 + float(taxa_acumulada))


def deflacionar(valor_nominal: float, inflacao_acumulada: float) -> float:
    """Valor real: valor nominal / (1 + inflação acumulada)."""
    return float(valor_nominal) / (1.0 + float(inflacao_acumulada))


def variacao_percentual(valor_inicial: float, valor_final: float) -> float:
    """Variação percentual entre dois valores."""
    if not valor_inicial:
        raise ValueError("valor_inicial precisa ser diferente de zero")
    return ((float(valor_final) / float(valor_inicial)) - 1.0) * 100.0


def acumulado_12m(taxas: Sequence[float]) -> float:
    """Acumula as 12 últimas taxas mensais decimais."""
    if len(taxas) < 12:
        raise ValueError("acumulado 12 meses exige pelo menos 12 taxas")
    return acumular(taxas[-12:])


def equivalente_anual(taxa_mensal: float) -> float:
    """Converte uma taxa mensal na taxa anual equivalente."""
    return (1.0 + float(taxa_mensal)) ** 12 - 1.0


def equivalente_mensal(taxa_anual: float) -> float:
    """Converte uma taxa anual na taxa mensal equivalente."""
    return (1.0 + float(taxa_anual)) ** (1.0 / 12.0) - 1.0


def media_movel(valores: Sequence[float], janela: int) -> list[float | None]:
    """Média móvel de `janela` períodos; os primeiros itens ficam None."""
    if janela <= 0:
        raise ValueError("janela precisa ser positiva")
    saida: list[float | None] = []
    for indice in range(len(valores)):
        if indice + 1 < janela:
            saida.append(None)
            continue
        recorte = valores[indice + 1 - janela: indice + 1]
        saida.append(sum(float(item) for item in recorte) / janela)
    return saida
