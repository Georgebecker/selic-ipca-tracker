"""Configuração do projeto: lê o `.env` (local, fora do git) e expõe os ajustes do código.

Nenhum segredo vive aqui: as chaves e caminhos locais ficam no `.env`, que nunca é
versionado (o gancho .githooks/pre-commit barra o commit que traga valor de chave).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
ARQ_ENV = RAIZ / ".env"
PASTA_FRONTEND = RAIZ / "frontend"
PASTA_DADOS = RAIZ / "data"

URL_PADRAO = "sqlite:///data/selic_ipca.db"
PREFIXO_SQLITE = "sqlite:///"

# O .env é opcional e nunca sobrescreve variáveis já definidas no ambiente.
load_dotenv(ARQ_ENV)


def url_do_banco() -> str:
    """URL do banco: `DB_URL` do ambiente (ou do `.env`) com padrão SQLite local."""
    return os.environ.get("DB_URL") or URL_PADRAO


def caminho_do_banco() -> Path:
    """Caminho absoluto do arquivo SQLite apontado por `DB_URL`."""
    url = url_do_banco()
    if not url.startswith(PREFIXO_SQLITE):
        raise ValueError(
            "caminho_do_banco() só entende " + PREFIXO_SQLITE + "... ; DB_URL=" + url
        )
    caminho = Path(url[len(PREFIXO_SQLITE):])
    return caminho if caminho.is_absolute() else (RAIZ / caminho)


def criar_pasta_do_banco() -> Path:
    """Garante que a pasta do arquivo do banco existe e devolve o caminho."""
    caminho = caminho_do_banco()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    return caminho


def modo_sql() -> bool:
    """`DB_ECHO` ligado? (log das consultas SQL)."""
    return (os.environ.get("DB_ECHO") or "").strip().lower() in {"1", "true", "sim", "yes"}
