"""Aplicação FastAPI do selic-ipca-tracker.

Subir em desenvolvimento:
  uvicorn src.api.main:app --reload
Documentação interativa: http://localhost:8000/docs
Dashboard: http://localhost:8000/app/
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from src import config
from src.api import execucao
from src.api.routers import calculadora, indicadores
from src.api.schemas import ProgressoColetaOut, StatusOut
from src.db.repository import (
    abrir_sessao,
    listar_series,
    obter_engine,
    semear_series,
    ultima_atualizacao,
)
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
    version="0.2.0",
    description=(
        "Indicadores econômicos brasileiros (Selic, IPCA, IGP-M, INPC) coletados "
        "das APIs do Banco Central, com correção monetária e coleta sob demanda."
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


def _progresso() -> ProgressoColetaOut:
    estado = execucao.estado()
    return ProgressoColetaOut(
        em_andamento=bool(estado.get("em_andamento")),
        total_series=int(estado.get("total_series") or 0),
        concluidas=int(estado.get("concluidas") or 0),
        iniciado_em=estado.get("iniciado_em"),
        finalizado_em=estado.get("finalizado_em"),
        status=estado.get("status"),
        mensagem=estado.get("mensagem"),
    )


@app.get("/status", response_model=StatusOut, tags=["atualização"], summary="Estado do serviço e da coleta")
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
            coleta=_progresso(),
        )


@app.post(
    "/atualizar",
    response_model=ProgressoColetaOut,
    status_code=202,
    tags=["atualização"],
    summary="Inicia a coleta em segundo plano (o progresso vem em GET /status)",
)
def post_atualizar() -> ProgressoColetaOut:
    iniciou, _ = execucao.iniciar(tipo="manual")
    return _progresso()


if config.PASTA_FRONTEND.exists():
    app.mount("/app", StaticFiles(directory=str(config.PASTA_FRONTEND), html=True), name="frontend")


@app.get("/", include_in_schema=False)
def raiz():
    destino = "/app/" if config.PASTA_FRONTEND.exists() else "/docs"
    return RedirectResponse(url=destino)
