param(
    [switch]$Recreate
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPath = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"

if ($Recreate -and (Test-Path -LiteralPath $VenvPath)) {
    throw "El borrado automatico esta deshabilitado. Elimine .venv manualmente si desea recrearlo."
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    $Python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $Python) {
        throw "No se encontro Python. Instale Python 3.10 o superior y vuelva a ejecutar este script."
    }
    Write-Output "Creando entorno virtual en $VenvPath"
    & $Python.Source -m venv $VenvPath
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo crear el entorno virtual."
    }
}

Write-Output "Comprobando el entorno..."
& $VenvPython --version
& $VenvPython -m pip install --disable-pip-version-check -r (Join-Path $ProjectRoot "requirements.txt")
& $VenvPython -B -m unittest discover -s (Join-Path $ProjectRoot "tests") -v

Write-Output ""
Write-Output "Entorno listo. Ejecute:"
Write-Output "  .\scripts\run_demo.ps1"
Write-Output "o directamente:"
Write-Output "  .\.venv\Scripts\python.exe .\demo\dsar_simulator.py"
