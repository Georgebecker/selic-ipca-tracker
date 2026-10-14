"""Os scripts de operação precisam continuar existindo, funcionando e sendo ASCII.

O teste do ASCII não é capricho: o PowerShell 5.1 lê arquivo `.ps1` sem BOM como ANSI, e
um caractere acentuado ou travessão quebra o parser com erros que apontam para linhas
erradas. Aconteceu com o `backup.ps1` (travessão em uma mensagem de erro) e custou uma
sessão de depuração — esta trava evita a repetição.
"""

from __future__ import annotations

from pathlib import Path

SCRIPTS = Path("scripts")
ESPERADOS = {"servir.ps1", "coletar.ps1", "backup.ps1"}
GITIGNORE = Path(".gitignore").read_text(encoding="utf-8")


def test_os_scripts_de_operacao_existem():
    for nome in sorted(ESPERADOS):
        assert (SCRIPTS / nome).is_file(), "script ausente: scripts/%s" % nome


def test_scripts_sao_ascii_puro():
    for nome in sorted(ESPERADOS):
        texto = (SCRIPTS / nome).read_text(encoding="utf-8-sig")
        nao_ascii = sorted({caractere for caractere in texto if ord(caractere) > 127})
        assert not nao_ascii, "scripts/%s tem caractere nao-ASCII: %s" % (nome, nao_ascii)


def test_scripts_nao_guardam_segredo():
    padrao = ("sk-", "api_key=", "token=", "password=", "senha=")
    for nome in sorted(ESPERADOS):
        texto = (SCRIPTS / nome).read_text(encoding="utf-8-sig").lower()
        for termo in padrao:
            assert termo not in texto, "scripts/%s parece guardar segredo (%s)" % (nome, termo)


def test_servir_aponta_para_o_app_e_aceita_porta():
    texto = (SCRIPTS / "servir.ps1").read_text(encoding="utf-8-sig")
    assert "uvicorn" in texto
    assert "src.api.main:app" in texto
    assert "Porta" in texto
    assert "/app/" in texto


def test_coletar_usa_o_modulo_de_coleta_e_workers():
    texto = (SCRIPTS / "coletar.ps1").read_text(encoding="utf-8-sig")
    assert "-m', 'src.etl.coleta" in texto or "src.etl.coleta" in texto
    assert "--workers" in texto
    assert "--tentativas-extras" in texto


def test_backup_tem_retencao_e_confere_o_arquivo():
    texto = (SCRIPTS / "backup.ps1").read_text(encoding="utf-8-sig")
    assert "data\\backups" in texto
    assert "Manter" in texto, "o backup precisa de politica de retencao"
    assert "sqlite3" in texto, "o backup precisa conferir que o arquivo abre"


def test_backups_nao_vao_para_o_git():
    assert "data/backups/" in GITIGNORE
    assert "*.db" in GITIGNORE
