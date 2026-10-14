# backup.ps1 - copia o banco do projeto para data\backups, com data no nome e retencao.
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File scripts\backup.ps1
#   ... -Manter 20          # quantos backups guardar (padrao 10)
#   ... -Listar             # so mostra o que existe, sem copiar
#
# Segue a Regra de Ouro: backup antes de operacao destrutiva, com data no nome e politica
# de retencao - e com a restauracao conferida (backup que nao volta nao e backup).
# O caminho do banco vem de src/config.py (o DB_URL do .env); nenhum valor e impresso.

[CmdletBinding()]
param(
    [int]$Manter = 10,
    [switch]$Listar
)

$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot
Push-Location $raiz

try {
    $pastaBackups = Join-Path $raiz 'data\backups'

    if ($Listar) {
        if (Test-Path $pastaBackups) {
            Get-ChildItem $pastaBackups -File | Sort-Object LastWriteTime -Descending |
                ForEach-Object {
                    Write-Output ("   {0}  {1:N0} KB  {2}" -f $_.LastWriteTime.ToString('dd/MM/yyyy HH:mm'), ($_.Length / 1KB), $_.Name)
                }
        }
        else {
            Write-Output '   (nenhum backup ainda)'
        }
        return
    }

    $caminho = (& python -c "import sys; sys.path.insert(0, r'$raiz'); from src.config import caminho_do_banco; print(caminho_do_banco())").Trim()
    if (-not $caminho) { throw 'Nao consegui descobrir o caminho do banco (src/config.py).' }
    if (-not (Test-Path $caminho)) { throw "Banco nao encontrado: $caminho - rode a coleta primeiro." }

    New-Item -ItemType Directory -Force -Path $pastaBackups | Out-Null

    $nome = [System.IO.Path]::GetFileNameWithoutExtension($caminho)
    $carimbo = Get-Date -Format 'yyyyMMdd-HHmmss'
    $destino = Join-Path $pastaBackups ($nome + '_' + $carimbo + '.db')

    Copy-Item -LiteralPath $caminho -Destination $destino -Force

    # Confere que o backup abre e tem dados: backup que nao volta nao e backup.
    $verificacao = @"
import sqlite3
conexao = sqlite3.connect(r'$destino')
tabelas = sorted(linha[0] for linha in conexao.execute("select name from sqlite_master where type='table'"))
valores = conexao.execute('select count(*) from valores').fetchone()[0]
conexao.close()
print('tabelas: ' + ', '.join(tabelas))
print('valores: ' + str(valores))
"@
    $saida = $verificacao | & python -

    Write-Output ''
    Write-Output ("   backup criado: {0} ({1:N0} KB)" -f (Split-Path -Leaf $destino), ((Get-Item $destino).Length / 1KB))
    $saida | ForEach-Object { Write-Output ("   " + $_) }

    # Politica de retencao: mantem os N mais recentes.
    $antigos = Get-ChildItem $pastaBackups -File | Sort-Object LastWriteTime -Descending | Select-Object -Skip $Manter
    if ($antigos) {
        Write-Output ''
        Write-Output ("   removendo {0} backup(s) antigo(s) (retencao: {1})" -f $antigos.Count, $Manter)
        $antigos | ForEach-Object {
            Write-Output ("     - " + $_.Name)
            Remove-Item $_.FullName -Force
        }
    }

    Write-Output ''
    Write-Output '   backups guardados:'
    Get-ChildItem $pastaBackups -File | Sort-Object LastWriteTime -Descending |
        ForEach-Object { Write-Output ("     {0}  {1:N0} KB" -f $_.Name, ($_.Length / 1KB)) }
}
finally {
    Pop-Location
}
