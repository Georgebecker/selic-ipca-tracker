"""O esquema de referência (`sql/schema.sql`) não pode divergir do modelo real.

`sql/schema.sql` existe para consulta manual e para recriar o banco sem Python. Se ele
atrasar em relação ao SQLAlchemy, alguém vai criar um banco errado — este teste avisa.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.db.models import Base
from src.db.repository import SERIES_PADRAO

SQL = Path("sql/schema.sql").read_text(encoding="utf-8")

TABELA = re.compile(r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\n\)\s*;", re.S)
COLUNA = re.compile(r"^\s{4}(\w+)\s+([A-Za-z])", re.M)
INDICE = re.compile(r"CREATE INDEX IF NOT EXISTS\s+(\w+)", re.I)
SEED = re.compile(r"INSERT OR IGNORE INTO series.*?VALUES(.*?);", re.S)


def _tabelas_do_sql() -> dict[str, set[str]]:
    return {
        nome: {coluna[0] for coluna in COLUNA.findall(corpo)}
        for nome, corpo in TABELA.findall(SQL)
    }


def _tabelas_do_modelo() -> dict[str, set[str]]:
    return {nome: {coluna.name for coluna in tabela.columns}
            for nome, tabela in Base.metadata.tables.items()}


def test_as_tabelas_do_sql_e_do_modelo_sao_as_mesmas():
    assert set(_tabelas_do_sql()) == set(_tabelas_do_modelo())


def test_as_colunas_de_cada_tabela_batem():
    sql = _tabelas_do_sql()
    modelo = _tabelas_do_modelo()
    for nome in sorted(modelo):
        assert sql.get(nome) == modelo[nome], "colunas divergentes em %s" % nome


def test_os_indices_do_sql_existem():
    indices = set(INDICE.findall(SQL))
    assert indices, "nenhum índice declarado no schema.sql"
    for nome in indices:
        assert nome.startswith("idx_")


def test_o_seed_do_sql_cobre_as_series_do_codigo():
    trecho = SEED.search(SQL)
    assert trecho, "bloco de seed (INSERT INTO series) não encontrado no schema.sql"
    codigos_sql = {int(item) for item in re.findall(r"\((\d+),", trecho.group(1))}
    codigos_codigo = {item["codigo_sgs"] for item in SERIES_PADRAO}
    assert codigos_sql == codigos_codigo


def test_o_sql_nao_guarda_segredo_nem_dado_de_conexao():
    assert "sqlite:///" not in SQL
    assert "postgresql://" not in SQL
    assert "password" not in SQL.lower()
