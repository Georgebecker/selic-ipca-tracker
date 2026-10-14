"""Acesso ao banco: engine, sessões, seed das séries e gravação dos valores."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import date, datetime

from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import criar_pasta_do_banco, modo_sql, url_do_banco
from src.db.models import Atualizacao, Base, Serie, Valor

# Séries acompanhadas pelo projeto (modelo.md, seções 2.1, 2.4 e 10).
SERIES_PADRAO: list[dict] = [
    {
        "codigo_sgs": 432,
        "nome": "Selic meta",
        "descricao": "Taxa Selic definida pelo Copom (% ao ano)",
        "unidade": "% a.a.",
        "periodicidade": "diaria",
    },
    {
        "codigo_sgs": 4390,
        "nome": "Selic acumulada no mês",
        "descricao": "Taxa Selic acumulada no mês (%)",
        "unidade": "%",
        "periodicidade": "mensal",
    },
    {
        "codigo_sgs": 433,
        "nome": "IPCA mensal",
        "descricao": "Variação mensal do IPCA (%)",
        "unidade": "%",
        "periodicidade": "mensal",
    },
    {
        "codigo_sgs": 13522,
        "nome": "IPCA acumulado 12 meses",
        "descricao": "IPCA acumulado em 12 meses (%)",
        "unidade": "%",
        "periodicidade": "mensal",
    },
    {
        "codigo_sgs": 189,
        "nome": "IGP-M mensal",
        "descricao": "Variação mensal do IGP-M (%)",
        "unidade": "%",
        "periodicidade": "mensal",
    },
    {
        "codigo_sgs": 188,
        "nome": "INPC mensal",
        "descricao": "Variação mensal do INPC (%)",
        "unidade": "%",
        "periodicidade": "mensal",
    },
    {
        "codigo_sgs": 12,
        "nome": "CDI diário",
        "descricao": "Taxa CDI diária (% ao dia)",
        "unidade": "% a.d.",
        "periodicidade": "diaria",
    },
    {
        "codigo_sgs": 1,
        "nome": "Dólar PTAX venda",
        "descricao": "Cotação do dólar (PTAX venda)",
        "unidade": "R$",
        "periodicidade": "diaria",
    },
    {
        "codigo_sgs": 7478,
        "nome": "IPCA-15",
        "descricao": "Prévia mensal do IPCA (%)",
        "unidade": "%",
        "periodicidade": "mensal",
    },
    {
        "codigo_sgs": 192,
        "nome": "INCC-DI",
        "descricao": "Custo da construção civil (%)",
        "unidade": "%",
        "periodicidade": "mensal",
    },
    {
        "codigo_sgs": 190,
        "nome": "IGP-DI",
        "descricao": "Índice geral de preços - disponibilidade interna (%)",
        "unidade": "%",
        "periodicidade": "mensal",
    },
    {
        "codigo_sgs": 25,
        "nome": "Poupança",
        "descricao": "Rendimento da caderneta de poupança (%)",
        "unidade": "%",
        "periodicidade": "mensal",
    },
]

_motor: Engine | None = None
_url_do_motor: str | None = None


def obter_engine(reiniciar: bool = False) -> Engine:
    """Engine única do processo, recriada se a `DB_URL` mudar ou se pedido."""
    global _motor, _url_do_motor

    url = url_do_banco()
    if _motor is None or reiniciar or _url_do_motor != url:
        criar_pasta_do_banco()
        argumentos: dict = {}
        if url.startswith("sqlite"):
            # check_same_thread=False: o SQLite é usado por threads do Uvicorn.
            argumentos["connect_args"] = {"check_same_thread": False}
        _motor = create_engine(url, echo=modo_sql(), **argumentos)
        Base.metadata.create_all(_motor)
        _url_do_motor = url
    return _motor


@contextmanager
def abrir_sessao() -> Iterator[Session]:
    """Sessão com commit automático e rollback em caso de erro."""
    fabrica = sessionmaker(bind=obter_engine(), expire_on_commit=False)
    sessao = fabrica()
    try:
        yield sessao
        sessao.commit()
    except Exception:
        sessao.rollback()
        raise
    finally:
        sessao.close()


def semear_series(sessao: Session) -> int:
    """Insere as séries padrão que ainda não existem. Devolve quantas foram criadas."""
    existentes = {codigo for (codigo,) in sessao.execute(select(Serie.codigo_sgs)).all()}
    criadas = 0
    for item in SERIES_PADRAO:
        if item["codigo_sgs"] in existentes:
            continue
        sessao.add(Serie(**item))
        criadas += 1
    sessao.flush()
    return criadas


def listar_series(sessao: Session) -> list[Serie]:
    return list(sessao.execute(select(Serie).order_by(Serie.codigo_sgs)).scalars())


def serie_por_codigo(sessao: Session, codigo_sgs: int) -> Serie | None:
    return sessao.execute(
        select(Serie).where(Serie.codigo_sgs == int(codigo_sgs))
    ).scalar_one_or_none()


def valores_da_serie(
    sessao: Session,
    codigo_sgs: int,
    de: date | None = None,
    ate: date | None = None,
) -> list[Valor]:
    """Valores de uma série em ordem cronológica, com filtro de período opcional."""
    consulta = (
        select(Valor)
        .join(Serie, Serie.id == Valor.serie_id)
        .where(Serie.codigo_sgs == int(codigo_sgs))
        .order_by(Valor.data)
    )
    if de is not None:
        consulta = consulta.where(Valor.data >= de)
    if ate is not None:
        consulta = consulta.where(Valor.data <= ate)
    return list(sessao.execute(consulta).scalars())


def ultimos_valores(sessao: Session, codigo_sgs: int, quantidade: int = 12) -> list[Valor]:
    """Últimos N valores, devolvidos em ordem cronológica."""
    consulta = (
        select(Valor)
        .join(Serie, Serie.id == Valor.serie_id)
        .where(Serie.codigo_sgs == int(codigo_sgs))
        .order_by(Valor.data.desc())
        .limit(int(quantidade))
    )
    return list(reversed(list(sessao.execute(consulta).scalars())))


def total_de_valores(sessao: Session, codigo_sgs: int) -> int:
    return int(
        sessao.execute(
            select(func.count(Valor.id))
            .join(Serie, Serie.id == Valor.serie_id)
            .where(Serie.codigo_sgs == int(codigo_sgs))
        ).scalar_one()
    )


def salvar_valores(
    sessao: Session, serie_id: int, registros: Sequence[tuple[date, float]]
) -> int:
    """Grava (ou atualiza) os valores de uma série. Devolve quantos pontos foram enviados."""
    if not registros:
        return 0

    linhas = [
        {"serie_id": int(serie_id), "data": dia, "valor": float(valor)}
        for dia, valor in registros
    ]
    comando = sqlite_insert(Valor).values(linhas)
    comando = comando.on_conflict_do_update(
        index_elements=["serie_id", "data"], set_={"valor": comando.excluded.valor}
    )
    sessao.execute(comando)
    sessao.flush()
    return len(linhas)


def registrar_atualizacao(
    sessao: Session,
    tipo: str,
    series_atualizadas: int,
    status: str,
    mensagem: str | None = None,
) -> Atualizacao:
    registro = Atualizacao(
        data_hora=datetime.now(),
        tipo=tipo,
        series_atualizadas=int(series_atualizadas),
        status=status,
        mensagem=(mensagem or "")[:500] or None,
    )
    sessao.add(registro)
    sessao.flush()
    return registro


def ultima_atualizacao(sessao: Session) -> Atualizacao | None:
    """Última coleta bem-sucedida (a base do timer de 24h)."""
    return sessao.execute(
        select(Atualizacao)
        .where(Atualizacao.status != "erro")
        .order_by(Atualizacao.data_hora.desc(), Atualizacao.id.desc())
        .limit(1)
    ).scalar_one_or_none()
