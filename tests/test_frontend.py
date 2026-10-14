"""Invariantes do front-end: layout responsivo, acessibilidade e ausência do relógio.

Não é um teste de navegador: garante que os arquivos não percam o que foi decidido
(campos que encolhem, tabela com a coluna do mês fixa, gráfico descrito para leitor de
tela) e que a interface não volte a ter contagem regressiva. A varredura de verdade —
de 320 a 1920 px medindo sobreposição — foi feita no navegador; aqui fica a trava
contra regressão silenciosa.
"""

from __future__ import annotations

import re
from pathlib import Path

FRONTEND = Path("frontend")
HTML = (FRONTEND / "index.html").read_text(encoding="utf-8")
CSS = (FRONTEND / "style.css").read_text(encoding="utf-8")
JS = (FRONTEND / "app.js").read_text(encoding="utf-8")


# ------------------------------- sem relógio -------------------------------

def test_nao_existe_contador_regressivo():
    assert 'id="timer"' not in HTML
    assert 'class="timer' not in HTML
    assert ".timer" not in CSS
    assert "iniciarRelogio" not in JS
    assert "formatarDuracao" not in JS
    assert "segundos_restantes" not in JS


def test_botao_de_atualizacao_e_pequeno_e_enxuto():
    assert "botao--pequeno" in HTML
    assert re.search(r"\.botao--pequeno\s*\{[^}]*padding:\s*7px 14px", CSS)
    assert "coletando" in JS.lower()


def test_atualizacao_acompanha_o_progresso():
    assert "/atualizar" in JS
    assert "acompanharColeta" in JS
    assert "em_andamento" in JS


# ------------------------- layout responsivo (travas) ----------------------

def test_campos_do_formulario_encolhem():
    bloco = re.search(r"\.formulario input,\s*\.formulario select\s*\{(.*?)\}", CSS, re.S)
    assert bloco, "regra de input/select do formulário não encontrada"
    assert "width: 100%" in bloco.group(1)
    assert "min-width: 0" in bloco.group(1)


def test_rotulo_do_formulario_nao_transborda():
    bloco = re.search(r"\.formulario label\s*\{(.*?)\}", CSS, re.S)
    assert bloco
    assert "min-width: 0" in bloco.group(1)
    assert "overflow-wrap" in bloco.group(1)


def test_grades_usam_min_para_nao_forcar_rolagem():
    for classe in (".grade", ".kpis", ".formulario"):
        bloco = re.search(re.escape(classe) + r"\s*\{(.*?)\}", CSS, re.S)
        assert bloco, "regra %s não encontrada" % classe
        assert "minmax(min(" in bloco.group(1), "%s deveria usar minmax(min(...))" % classe


def test_formulario_vira_uma_coluna_no_celular():
    media = re.search(r"@media \(max-width: 520px\)\s*\{(.*?)\n\}", CSS, re.S)
    assert media, "media query do celular não encontrada"
    assert "grid-template-columns: 1fr" in media.group(1)


def test_coluna_do_mes_fica_fixa_na_tabela():
    bloco = re.search(r"\.tabela th:first-child,\s*\.tabela td:first-child\s*\{(.*?)\}", CSS, re.S)
    assert bloco
    assert "position: sticky" in bloco.group(1)


# ----------------------------- acessibilidade -----------------------------

def test_grafico_tem_descricao_para_leitor_de_tela():
    assert 'role="img"' in HTML
    assert "aria-label" in HTML
    assert "setAttribute('aria-label'" in JS, "o app.js deveria atualizar a descrição do gráfico"


def test_avisos_e_tabela_tem_rotulos():
    assert 'aria-label="Indicadores atuais"' in HTML
    assert "<th" in HTML  # cabeçalho de tabela de verdade, não só célula


def test_mes_corrente_parcial_esta_explicado_na_tela():
    assert "mês corrente aparece parcial" in HTML
