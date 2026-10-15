"""Tabelas do banco (SQLAlchemy 2.0) — séries, valores e log de atualizações.

Espelha o esquema descrito em `sql/schema.sql`.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base declarativa do projeto."""


class Serie(Base):
    """Metadados de uma série temporal do BCB/SGS."""

    __tablename__ = "series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo_sgs: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    descricao: Mapped[str | None] = mapped_column(String(255))
    unidade: Mapped[str | None] = mapped_column(String(30))
    periodicidade: Mapped[str | None] = mapped_column(String(20))
    fonte: Mapped[str] = mapped_column(
        String(30), nullable=False, default="BCB/SGS", server_default="BCB/SGS"
    )

    valores: Mapped[list["Valor"]] = relationship(
        back_populates="serie", cascade="all, delete-orphan"
    )


class Valor(Base):
    """Um ponto da série (data + valor)."""

    __tablename__ = "valores"
    __table_args__ = (
        UniqueConstraint("serie_id", "data", name="uq_valores_serie_data"),
        Index("idx_valores_serie_data", "serie_id", "data"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    serie_id: Mapped[int] = mapped_column(ForeignKey("series.id"), nullable=False)
    data: Mapped[date] = mapped_column(Date, nullable=False)
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    coletado_em: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    serie: Mapped[Serie] = relationship(back_populates="valores")


class Atualizacao(Base):
    """Registro de cada coleta (automática ou manual)."""

    __tablename__ = "atualizacoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    data_hora: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    series_atualizadas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    mensagem: Mapped[str | None] = mapped_column(String(500))
