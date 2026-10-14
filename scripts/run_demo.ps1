param(
    [ValidateSet("interactive", "access", "pending", "erasure")]
    [string]$Scenario = "interactive",
    [string]$Request,
    [switch]$NoAI
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Simulator = Join-Path $ProjectRoot "demo\dsar_simulator.py"

if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "El entorno no existe. Ejecute primero .\scripts\setup.ps1"
}

$Arguments = @($Simulator)
if ($Request) {
    $Arguments += @("--request", (Resolve-Path -LiteralPath $Request).Path)
}
else {
    $Arguments += @("--scenario", $Scenario)
}
if ($NoAI) {
    $Arguments += "--no-ai"
}

Push-Location $ProjectRoot
try {
    & $VenvPython @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "La simulacion termino con codigo $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
