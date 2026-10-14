"""Coleta automática opcional (APScheduler).

A atualização normal é **manual**: os indicadores são mensais e o dashboard tem o botão
"Atualizar". Este módulo existe para quem quiser que o **servidor** atualize sozinho
(máquina sempre ligada, servidor publicado) sem depender de alguém clicar.

Como ligar (variável de ambiente, nunca em arquivo versionado):

```powershell
$env:COLETA_AUTOMATICA = "true"
$env:COLETA_INTERVALO_HORAS = "24"

# ou, para valer sempre na sua máquina:
[Environment]::SetEnvironmentVariable('COLETA_AUTOMATICA', 'true', 'User')
```

Fica **desligado por padrão**: agendador ligado sem querer faria chamadas ao BCB sem
ninguém pedir. `GET /status` informa se está ligado (campo `coleta_automatica`).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

INTERVALO_HORAS = 24
VARIAVEL_LIGADA = "COLETA_AUTOMATICA"
VARIAVEL_INTERVALO = "COLETA_INTERVALO_HORAS"
VALORES_LIGADOS = {"1", "true", "sim", "yes", "on"}


def coleta_automatica_ligada() -> bool:
    """`COLETA_AUTOMATICA` está ligada? (padrão: desligada)"""
    return (os.environ.get(VARIAVEL_LIGADA) or "").strip().lower() in VALORES_LIGADOS


def intervalo_horas() -> int:
    """Intervalo entre coletas automáticas, em horas (padrão 24; mínimo 1)."""
    bruto = (os.environ.get(VARIAVEL_INTERVALO) or "").strip()
    if not bruto:
        return INTERVALO_HORAS
    try:
        return max(1, int(float(bruto)))
    except ValueError:
        return INTERVALO_HORAS


def proxima_atualizacao(
    ultima: datetime | None, intervalo: int = INTERVALO_HORAS
) -> datetime | None:
    """Momento da próxima coleta automática, contado a partir da última."""
    if ultima is None:
        return None
    return ultima + timedelta(hours=intervalo)


def segundos_restantes(
    ultima: datetime | None,
    agora: datetime | None = None,
    intervalo: int = INTERVALO_HORAS,
) -> int:
    """Segundos até a próxima coleta (0 quando já venceu ou não há histórico)."""
    proxima = proxima_atualizacao(ultima, intervalo)
    if proxima is None:
        return 0
    referencia = agora or datetime.now()
    return max(0, int((proxima - referencia).total_seconds()))


def iniciar_agendador(intervalo: int = INTERVALO_HORAS):
    """Agendador em segundo plano (APScheduler). Devolve o agendador ou None.

    Devolve None quando o APScheduler não está instalado: sem ele a aplicação funciona
    igual, apenas não faz coleta automática.
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
        hours=intervalo,
        kwargs={"tipo": "automatica"},
        id="atualizacao_automatica",
        replace_existing=True,
    )
    agendador.start()
    return agendador


def ligar_se_configurado():
    """Liga o agendador só se `COLETA_AUTOMATICA` estiver ativa.

    Chamado na subida da aplicação. Devolve None quando está desligado, quando o
    APScheduler não está instalado ou quando o agendador não pôde ser criado — coleta
    automática nunca deve derrubar a API.
    """
    if not coleta_automatica_ligada():
        return None
    try:
        return iniciar_agendador(intervalo_horas())
    except Exception:  # noqa: BLE001 - opcional: falhar aqui nao pode impedir o servico
        return None
