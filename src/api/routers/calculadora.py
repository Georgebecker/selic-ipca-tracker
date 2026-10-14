"""Endpoint da calculadora de correção monetária."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.analise.calculos import corrigir, fator_acumulado
from src.api.schemas import CorrecaoRequest, CorrecaoResponse
from src.db.repository import abrir_sessao, valores_da_serie

router = APIRouter(tags=["calculadora"])

# Selic usa a série 4390 (Selic acumulada no mês): é a taxa mensal que compõe.
INDICES = {
    "IPCA": 433,
    "IGP-M": 189,
    "IGPM": 189,
    "INPC": 188,
    "SELIC": 4390,
    "POUPANCA": 25,
}


@router.post(
    "/calculadora/corrigir",
    response_model=CorrecaoResponse,
    summary="Corrige um valor pela inflação do período",
)
def corrigir_valor(pedido: CorrecaoRequest) -> CorrecaoResponse:
    indice = pedido.indice.strip().upper()
    codigo = INDICES.get(indice)
    if codigo is None:
        raise HTTPException(
            status_code=422,
            detail="índice desconhecido: %s (use IPCA, IGP-M, INPC ou Selic)" % pedido.indice,
        )

    with abrir_sessao() as sessao:
        valores = valores_da_serie(sessao, codigo, pedido.data_inicial, pedido.data_final)

    taxas = [item.valor for item in valores]
    if not taxas:
        raise HTTPException(
            status_code=404,
            detail="sem dados de %s no período informado" % indice,
        )

    fator = fator_acumulado([taxa / 100.0 for taxa in taxas])
    return CorrecaoResponse(
        valor_original=pedido.valor,
        valor_corrigido=round(corrigir(pedido.valor, fator - 1.0), 2),
        fator_acumulado=round(fator, 6),
        variacao_percentual=round((fator - 1.0) * 100.0, 4),
        indice=indice,
        periodo="%s a %s" % (pedido.data_inicial.isoformat(), pedido.data_final.isoformat()),
        meses=len(taxas),
    )
