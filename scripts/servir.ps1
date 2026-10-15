# servir.ps1 - sobe a API + dashboard do selic-ipca-tracker
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File scripts\servir.ps1
#   ... -Porta 8080 -Recarregar          # recarrega ao salvar arquivo (desenvolvimento)
#   ... -AbrirNavegador                  # abre o dashboard no navegador
#
# Ctrl+C encerra. O servico vive enquanto esta janela estiver aberta.

[CmdletBinding()]
param(
    [string]$Endereco = '127.0.0.1',
    [int]$Porta = 8000,
    [switch]$Recarregar,
    [switch]$AbrirNavegador
)

$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot
Push-Location $raiz

try {
    if (-not (Test-Path 'src\api\main.py')) {
        throw "Rode este script de dentro do projeto (nao encontrei src\api\main.py em $raiz)."
    }

    if (-not (Test-Path '.env')) {
        Write-Host "[aviso] nao existe .env neste projeto. O padrao funciona, mas sem ele voce"
        Write-Host "        nao ajusta DB_URL. Para criar:"
        Write-Host "        Copy-Item .env.example .env"
    }

    $urlBase = "http://${Endereco}:${Porta}"
    Write-Host ""
    Write-Host "  selic-ipca-tracker"
    Write-Host "  ------------------------------------------------------------"
    Write-Host "  dashboard : $urlBase/app/"
    Write-Host "  docs      : $urlBase/docs"
    Write-Host "  status    : $urlBase/status"
    Write-Host "  Ctrl+C para parar."
    Write-Host ""

    if ($AbrirNavegador) {
        Start-Process "$urlBase/app/"
    }

    $argumentos = @('-m', 'uvicorn', 'src.api.main:app', '--host', $Endereco, '--port', $Porta)
    if ($Recarregar) { $argumentos += '--reload' }

    & python @argumentos
}
finally {
    Pop-Location
}
