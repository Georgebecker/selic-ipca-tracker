"""Normalização dos dados brutos do SGS."""

from __future__ import annotations

from datetime import date

import pandas as pd

FORMATO_PADRAO = "%d/%m/%Y"
FORMATO_ISO = "%Y-%m-%d"


def limpar_serie(bruto) -> pd.DataFrame:
    """Converte a lista de dicts do SGS em DataFrame com `data` (datetime) e `valor` (float).

    Remove linhas sem data ou sem valor numérico, ordena e elimina datas repetidas.
    """
    if bruto is None:
        registros: list[dict] = []
    elif isinstance(bruto, dict):
        registros = [bruto]
    else:
        registros = list(bruto)

    vazio = pd.DataFrame(
        {"data": pd.Series(dtype="datetime64[ns]"), "valor": pd.Series(dtype="float64")}
    )
    if not registros:
        return vazio

    quadro = pd.DataFrame(registros)
    for coluna in ("data", "valor"):
        if coluna not in quadro.columns:
            raise ValueError("cada registro precisa das chaves 'data' e 'valor'")

    datas = pd.to_datetime(quadro["data"], format=FORMATO_PADRAO, errors="coerce")
    sem_data_br: pd.Series = datas.isna()
    if bool(sem_data_br.any()):
        # Aceita também datas ISO (usadas nos testes e em importações manuais).
        alternativas = pd.to_datetime(
            quadro.loc[sem_data_br, "data"], format=FORMATO_ISO, errors="coerce"
        )
        datas = datas.mask(sem_data_br, alternativas)

    limpo = pd.DataFrame(
        {
            "data": pd.to_datetime(datas).dt.normalize(),
            "valor": pd.to_numeric(quadro["valor"], errors="coerce"),
        }
    )
    limpo = limpo.dropna(subset=["data", "valor"])
    limpo = limpo.drop_duplicates(subset=["data"], keep="last")
    return limpo.sort_values("data").reset_index(drop=True)


def remover_nulos(quadro: pd.DataFrame) -> pd.DataFrame:
    """Remove linhas com valor ausente."""
    return quadro.dropna(subset=["valor"]).reset_index(drop=True)


def filtrar_periodo(
    quadro: pd.DataFrame, de: date | str | None = None, ate: date | str | None = None
) -> pd.DataFrame:
    """Recorta o DataFrame para o período pedido."""
    resultado = quadro
    if de is not None:
        resultado = resultado[resultado["data"] >= pd.Timestamp(de)]
    if ate is not None:
        resultado = resultado[resultado["data"] <= pd.Timestamp(ate)]
    return resultado.reset_index(drop=True)


def registros_para_banco(quadro: pd.DataFrame) -> list[tuple[date, float]]:
    """Converte o DataFrame limpo na lista (data, valor) usada pelo repositório."""
    return [
        (linha.data.date(), float(linha.valor))
        for linha in quadro.itertuples(index=False)
        if linha.data is not None and linha.valor is not None
    ]
