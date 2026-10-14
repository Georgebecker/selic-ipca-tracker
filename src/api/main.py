"""Aplicação FastAPI do selic-ipca-tracker.

Subir em desenvolvimento:
  uvicorn src.api.main:app --reload
Documentação interativa: http://localhost:8000/docs
Dashboard: http://localhost:8000/app/
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from src import config
from src.api.routers import calculadora, indicadores
from src.api.schemas import AtualizacaoOut, StatusOut
from src.db.repository import (
    abrir_sessao,
    listar_series,
    obter_engine,
    semear_series,
    ultima_atualizacao,
)
from src.etl.coleta import atualizar_todas
from src.scheduler.timer import INTERVALO_HORAS, proxima_atualizacao, segundos_restantes


@asynccontextmanager
async def ciclo_de_vida(_app: FastAPI):
    """Cria o banco e semeia as séries na subida da aplicação."""
    obter_engine()
    with abrir_sessao() as sessao:
        semear_series(sessao)
    yield


app = FastAPI(
    title="selic-ipca-tracker",
    version="0.1.0",
    description=(
        "Indicadores econômicos brasileiros (Selic, IPCA, IGP-M, INPC) coletados "
        "das APIs do Banco Central, com correção monetária e timer de atualização de 24h."
    ),
    lifespan=ciclo_de_vida,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(indicadores.router)
app.include_router(calculadora.router)


@app.get("/status", response_model=StatusOut, tags=["atualização"], summary="Status do timer de 24h")
def get_status() -> StatusOut:
    with abrir_sessao() as sessao:
        ultima = ultima_atualizacao(sessao)
        momento = ultima.data_hora if ultima else None
        return StatusOut(
            ultima_atualizacao=momento,
            proxima_atualizacao=proxima_atualizacao(momento, INTERVALO_HORAS),
            segundos_restantes=segundos_restantes(momento, intervalo_horas=INTERVALO_HORAS),
            intervalo_horas=INTERVALO_HORAS,
            series_monitoradas=len(listar_series(sessao)),
        )


@app.post("/atualizar", response_model=AtualizacaoOut, tags=["atualização"], summary="Força a coleta agora")
def post_atualizar() -> AtualizacaoOut:
    try:
        return AtualizacaoOut(**atualizar_todas(tipo="manual"))
    except Exception as erro:  # noqa: BLE001 - reporta a falha da coleta como 502
        raise HTTPException(status_code=502, detail="falha ao atualizar: %s" % erro) from erro


if config.PASTA_FRONTEND.exists():
    app.mount("/app", StaticFiles(directory=str(config.PASTA_FRONTEND), html=True), name="frontend")


@app.get("/", include_in_schema=False)
def raiz():
    destino = "/app/" if config.PASTA_FRONTEND.exists() else "/docs"
    return RedirectResponse(url=destino)
