"""Execução da coleta em segundo plano, com progresso consultável.

Por que existe: `POST /atualizar` era síncrono — com o histórico completo a coleta
leva de ~5 s (execução quente) até ~1 min (primeira carga), o que trava a requisição
HTTP e não dá nenhum sinal de vida. Aqui a coleta roda numa thread e o front consulta
`GET /status` para mostrar "Coletando 3/12…".

Regras:
- uma coleta por vez (a segunda chamada só recebe o progresso, não inicia outra);
- o estado é lido/copiado sob lock (nenhuma thread vê estado pela metade);
- o resultado final fica guardado para o front buscar depois de terminar.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime
from typing import Any

from src.etl.coleta import WORKERS_PADRAO, atualizar_todas

_lock = threading.Lock()
_estado: dict[str, Any] = {
    "em_andamento": False,
    "total_series": 0,
    "concluidas": 0,
    "iniciado_em": None,
    "finalizado_em": None,
    "tipo": None,
    "status": None,
    "mensagem": None,
    "resultado": None,
}


def _agora() -> datetime:
    return datetime.now()


def estado() -> dict:
    """Cópia do estado atual (segura para ler de qualquer thread)."""
    with _lock:
        return dict(_estado)


def em_andamento() -> bool:
    with _lock:
        return bool(_estado["em_andamento"])


def registrar_progresso(concluidas: int, total: int) -> None:
    """Chamado a cada série baixada (usado também pelos testes)."""
    with _lock:
        _estado["concluidas"] = int(concluidas)
        _estado["total_series"] = int(total)


def _executar(tipo: str, codigos: list[int] | None, workers: int) -> None:
    def avisar(mensagem: str) -> None:
        # Formato do aviso: "[3/12] serie 189: 201 valores"
        try:
            parte = mensagem.split("]", 1)[0].lstrip("[")
            concluidas, total = parte.split("/")
            registrar_progresso(int(concluidas), int(total))
        except (ValueError, IndexError):
            pass

    try:
        resultado = atualizar_todas(tipo=tipo, codigos=codigos, workers=workers, avisar=avisar)
        erro = None
    except Exception as falha:  # noqa: BLE001 - reporta qualquer falha como estado final
        resultado = None
        erro = str(falha)

    with _lock:
        _estado["em_andamento"] = False
        _estado["finalizado_em"] = _agora()
        if resultado is None:
            _estado["status"] = "erro"
            _estado["mensagem"] = erro
        else:
            _estado["status"] = resultado.get("status")
            falhas = resultado.get("falhas") or {}
            _estado["mensagem"] = (
                "; ".join("%s: %s" % (codigo, texto) for codigo, texto in sorted(falhas.items()))
                or None
            )
            _estado["resultado"] = resultado
            _estado["concluidas"] = int(resultado.get("series_atualizadas", _estado["concluidas"]))


def _criar_thread(tipo: str, codigos: list[int] | None, workers: int) -> threading.Thread:
    return threading.Thread(
        target=_executar, args=(tipo, codigos, workers), name="coleta", daemon=True
    )


def iniciar(tipo: str = "manual", codigos: list[int] | None = None,
            workers: int = WORKERS_PADRAO) -> tuple[bool, dict]:
    """Inicia a coleta se ninguém estiver rodando.

    Devolve (iniciou, estado): `iniciou=False` quando já havia uma coleta em andamento.
    """
    with _lock:
        if _estado["em_andamento"]:
            return False, dict(_estado)
        _estado.update(
            {
                "em_andamento": True,
                "total_series": 0,
                "concluidas": 0,
                "iniciado_em": _agora(),
                "finalizado_em": None,
                "tipo": tipo,
                "status": None,
                "mensagem": None,
            }
        )

    _criar_thread(tipo, codigos, workers).start()
    return True, estado()


def reiniciar_estado() -> None:
    """Zera o estado (usado pelos testes para isolar cada cenário)."""
    with _lock:
        _estado.update(
            {
                "em_andamento": False,
                "total_series": 0,
                "concluidas": 0,
                "iniciado_em": None,
                "finalizado_em": None,
                "tipo": None,
                "status": None,
                "mensagem": None,
                "resultado": None,
            }
        )


def aguardar(timeout: float = 30.0) -> bool:
    """Espera a coleta atual terminar (usado pelos testes). Devolve True se terminou."""
    fim = datetime.now().timestamp() + timeout
    while em_andamento() and datetime.now().timestamp() < fim:
        threading.Event().wait(0.05)
    return not em_andamento()


def criar_avisador(callback: Callable[[int, int], None]) -> Callable[[str], None]:
    """Adapta um callback (concluidas, total) ao formato de aviso da coleta."""

    def avisar(mensagem: str) -> None:
        try:
            parte = mensagem.split("]", 1)[0].lstrip("[")
            concluidas, total = parte.split("/")
            callback(int(concluidas), int(total))
        except (ValueError, IndexError):
            pass

    return avisar
