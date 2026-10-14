"""Timer de atualização (24 horas).

O contador regressivo principal roda no front-end, que consulta `/status` e chama
`/atualizar` quando o tempo zera. O agendador opcional (APScheduler) mantém a
coleta rodando mesmo com a página fechada.
"""

from __future__ import annotations

from datetime import datetime, timedelta

INTERVALO_HORAS = 24


def proxima_atualizacao(
    ultima: datetime | None, intervalo_horas: int = INTERVALO_HORAS
) -> datetime | None:
    """Momento da próxima coleta automática, contado a partir da última."""
    if ultima is None:
        return None
    return ultima + timedelta(hours=intervalo_horas)


def segundos_restantes(
    ultima: datetime | None,
    agora: datetime | None = None,
    intervalo_horas: int = INTERVALO_HORAS,
) -> int:
    """Segundos até a próxima coleta (0 quando já venceu ou não há histórico)."""
    proxima = proxima_atualizacao(ultima, intervalo_horas)
    if proxima is None:
        return 0
    referencia = agora or datetime.now()
    return max(0, int((proxima - referencia).total_seconds()))


def iniciar_agendador(intervalo_horas: int = INTERVALO_HORAS):
    """Agendador opcional em segundo plano (APScheduler).

    Devolve o agendador iniciado ou None quando o APScheduler não está instalado.
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        return None

    from src.etl.coleta import atualizar_todas

    agendador = BackgroundScheduler(timezone="America/Sao_Paulo")
    agendador.add_job(
        atualizar_todas,
        "interval",
        hours=intervalo_horas,
        kwargs={"tipo": "automatica"},
        id="atualizacao_automatica",
        replace_existing=True,
    )
    agendador.start()
    return agendador
