"""Verificação da seção `## Classificação` do README (modelo.md, seção 1.1.4)."""

from __future__ import annotations

import re
from pathlib import Path

README = Path("README.md")

VALORES_DE_MATURIDADE = ["rascunho", "funcional", "usável", "estável"]
VALORES_DE_PROPOSITO = ["estudo", "utilidade", "entrega"]


def _conteudo() -> str:
    return README.read_text(encoding="utf-8")


def test_readme_tem_classificacao():
    assert README.exists(), "README.md não encontrado na raiz do projeto"
    assert "## Classificação" in _conteudo()


def test_classificacao_sem_placeholder():
    conteudo = _conteudo()
    assert "(ex:" not in conteudo
    assert "| **Propósito** |  |" not in conteudo
    assert "| **Maturidade** |  |" not in conteudo


def test_maturidade_valida():
    conteudo = _conteudo()
    encontrado = re.search(r"\*\*Maturidade\*\* \| `([^`]+)`", conteudo)
    assert encontrado is not None, "linha **Maturidade** ausente ou sem valor entre crases"
    assert encontrado.group(1) in VALORES_DE_MATURIDADE


def test_proposito_valido():
    conteudo = _conteudo()
    encontrado = re.search(r"\*\*Propósito\*\* \| (.+) \|", conteudo)
    assert encontrado is not None, "linha **Propósito** ausente"
    itens = [valor.strip().strip("`") for valor in encontrado.group(1).split("·")]
    assert itens, "Propósito sem valores"
    assert len(itens) <= 2, "Propósito aceita no máximo 2 valores"
    for item in itens:
        assert item in VALORES_DE_PROPOSITO, "Propósito inválido: %s" % item


def test_treinando_e_quem_usaria_preenchidos():
    conteudo = _conteudo()
    for rotulo in ("**O que estou treinando**", "**Quem usaria**"):
        encontrado = re.search(re.escape(rotulo) + r" \| (.+) \|", conteudo)
        assert encontrado is not None, "linha %s ausente" % rotulo
        assert encontrado.group(1).strip(), "linha %s vazia" % rotulo
