param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "El entorno no existe. Ejecute primero .\scripts\setup.ps1"
}

Push-Location $ProjectRoot
try {
    Write-Output "Interfaz web en http://127.0.0.1:$Port (API en /docs)"
    & $VenvPython -m uvicorn app.main:app --host 127.0.0.1 --port $Port --reload
}
finally {
    Pop-Location
}
