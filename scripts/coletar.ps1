# coletar.ps1 - coleta as series do BCB e grava no banco do projeto
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File scripts\coletar.ps1
#   ... -Series 433,189        # so algumas series
#   ... -Workers 10            # mais paralelismo (padrao 6)
#
# As series sao baixadas em paralelo e gravadas uma a uma (o SQLite aceita um escritor
# por vez). Quem falhar e tentado de novo automaticamente.

[CmdletBinding()]
param(
    [string]$Series = '',
    [int]$Workers = 6,
    [int]$TentativasExtras = 1
)

$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot
Push-Location $raiz

try {
    $argumentos = @('-m', 'src.etl.coleta', '--workers', $Workers,
                    '--tentativas-extras', $TentativasExtras)
    if ($Series) { $argumentos += @('--series', $Series) }

    Write-Host "  coletando do BCB/SGS (workers=$Workers)..."
    Write-Host ""

    & python @argumentos
    $codigo = $LASTEXITCODE

    Write-Host ""
    if ($codigo -eq 0) {
        Write-Host "  coleta concluida sem falhas."
    }
    else {
        Write-Host "  atencao: houve falha em alguma serie (veja a lista acima)."
    }
    exit $codigo
}
finally {
    Pop-Location
}
