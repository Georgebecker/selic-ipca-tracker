# instalar.ps1 - ativa os ganchos de protecao do git neste projeto
# Uso: powershell -ExecutionPolicy Bypass -File .githooks\instalar.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    if (-not (Test-Path ".git")) {
        Write-Host "Nenhum repositorio git aqui. Inicializando 'git init'..."
        git init
    }
    git config core.hooksPath .githooks
    foreach ($gancho in "pre-commit", "pre-push") {
        if (-not (Test-Path ".githooks\$gancho")) { throw "Gancho ausente: .githooks\$gancho" }
    }
    Write-Host ""
    Write-Host "Protecao ativa nos dois momentos: commit e envio ao remoto."
    Write-Host "  - no commit: arquivo .githooks\pre-commit"
    Write-Host "  - no envio:  arquivo .githooks\pre-push"
    Write-Host "O .env nao entra no git de jeito nenhum."
} finally {
    Pop-Location
}
