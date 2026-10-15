"""Endpoints de séries, indicadores e comparação."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from src.analise.comparacao import (
    INDICADORES,
    alinhar_por_mes,
    resumo_indicador,
)
from src.api.schemas import (
    ComparacaoOut,
    IndicadorOut,
    PontoOut,
    ResumoOut,
    SerieDadosOut,
    SerieOut,
)
from src.db.repository import (
    abrir_sessao,
    listar_series,
    serie_por_codigo,
    total_de_valores,
    ultima_atualizacao,
    ultimos_valores,
    valores_da_serie,
)

router = APIRouter(tags=["indicadores"])

LIMITE_DE_PONTOS = 5000


def _pontos(valores) -> list[PontoOut]:
    return [PontoOut(data=item.data, valor=item.valor) for item in valores]


def _codigos_do_comparativo(codigos: str | None) -> list[int]:
    if not codigos:
        return [info["codigo_sgs"] for info in INDICADORES.values()]
    return [int(item) for item in codigos.split(",") if item.strip()]


@router.get("/series", response_model=list[SerieOut], summary="Lista as séries disponíveis")
def get_series() -> list[SerieOut]:
    with abrir_sessao() as sessao:
        return [
            SerieOut(
                codigo_sgs=serie.codigo_sgs,
                nome=serie.nome,
                descricao=serie.descricao,
                unidade=serie.unidade,
                periodicidade=serie.periodicidade,
                fonte=serie.fonte,
                total_valores=total_de_valores(sessao, serie.codigo_sgs),
            )
            for serie in listar_series(sessao)
        ]


@router.get(
    "/series/{codigo}/dados",
    response_model=SerieDadosOut,
    summary="Série completa (filtros ?de= e ?ate=)",
)
def get_dados(
    codigo: int,
    de: date | None = Query(default=None, description="data inicial (aaaa-mm-dd)"),
    ate: date | None = Query(default=None, description="data final (aaaa-mm-dd)"),
) -> SerieDadosOut:
    with abrir_sessao() as sessao:
        serie = serie_por_codigo(sessao, codigo)
        if serie is None:
            raise HTTPException(status_code=404, detail="série %s não encontrada" % codigo)

        valores = valores_da_serie(sessao, codigo, de, ate)
        if len(valores) > LIMITE_DE_PONTOS:
            raise HTTPException(
                status_code=422,
                detail="período com %d pontos (limite %d); refine o filtro de datas"
                % (len(valores), LIMITE_DE_PONTOS),
            )
        return SerieDadosOut(
            codigo_sgs=serie.codigo_sgs,
            nome=serie.nome,
            unidade=serie.unidade,
            total=len(valores),
            valores=_pontos(valores),
        )


@router.get(
    "/series/{codigo}/ultimos/{quantidade}",
    response_model=SerieDadosOut,
    summary="Últimos N valores de uma série",
)
def get_ultimos(codigo: int, quantidade: int = 12) -> SerieDadosOut:
    if quantidade <= 0 or quantidade > LIMITE_DE_PONTOS:
        raise HTTPException(
            status_code=422, detail="quantidade precisa estar entre 1 e %d" % LIMITE_DE_PONTOS
        )

    with abrir_sessao() as sessao:
        serie = serie_por_codigo(sessao, codigo)
        if serie is None:
            raise HTTPException(status_code=404, detail="série %s não encontrada" % codigo)

        valores = ultimos_valores(sessao, codigo, quantidade)
        return SerieDadosOut(
            codigo_sgs=serie.codigo_sgs,
            nome=serie.nome,
            unidade=serie.unidade,
            total=len(valores),
            valores=_pontos(valores),
        )


@router.get(
    "/indicadores/resumo",
    response_model=ResumoOut,
    summary="KPIs de Selic, IPCA, IGP-M e INPC",
)
def get_resumo() -> ResumoOut:
    with abrir_sessao() as sessao:
        indicadores: dict[str, IndicadorOut] = {}

        for chave, info in INDICADORES.items():
            valores = [
                (item.data, item.valor) for item in valores_da_serie(sessao, info["codigo_sgs"])
            ]

            base = None
            if info["codigo_acumulado"] != info["codigo_sgs"]:
                # Selic meta (432) é anualizada: acumular 12 meses exige a série mensal
                # equivalente (4390). Para IPCA/IGP-M/INPC a própria série já é mensal.
                base = [
                    (item.data, item.valor)
                    for item in valores_da_serie(sessao, info["codigo_acumulado"])
                ]

            oficial = None
            if info.get("codigo_oficial"):
                ultimos = ultimos_valores(sessao, info["codigo_oficial"], 1)
                if ultimos:
                    oficial = ultimos[-1].valor

            indicadores[chave] = IndicadorOut(
                nome=info["nome"],
                serie=info["codigo_sgs"],
                **resumo_indicador(valores, base, oficial),
            )

        ultima = ultima_atualizacao(sessao)
        return ResumoOut(
            **indicadores, ultima_atualizacao=ultima.data_hora if ultima else None
        )


@router.get(
    "/comparacao",
    response_model=ComparacaoOut,
    summary="Compara índices mês a mês (?series=433,189,188)",
)
def get_comparacao(
    de: date | None = Query(default=None),
    ate: date | None = Query(default=None),
    series: str | None = Query(default=None, description="códigos SGS separados por vírgula"),
) -> ComparacaoOut:
    with abrir_sessao() as sessao:
        blocos = []
        for codigo in _codigos_do_comparativo(series):
            serie = serie_por_codigo(sessao, codigo)
            if serie is None:
                continue
            blocos.append(
                {
                    "codigo_sgs": serie.codigo_sgs,
                    "nome": serie.nome,
                    "unidade": serie.unidade,
                    "valores": [
                        (item.data, item.valor)
                        for item in valores_da_serie(sessao, codigo, de, ate)
                    ],
                }
            )

        alinhado = alinhar_por_mes(blocos)
        return ComparacaoOut(de=de, ate=ate, eixo=alinhado["eixo"], series=alinhado["series"])
