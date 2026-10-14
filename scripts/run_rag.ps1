param(
    [Parameter(Mandatory = $true)]
    [string]$Query,

    [ValidateRange(1, 10)]
    [int]$TopK = 3,

    [switch]$Json,

    [switch]$RebuildIndex
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Retriever = Join-Path $ProjectRoot "rag\dsar_rag.py"

if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "El entorno no existe. Ejecute primero .\scripts\setup.ps1"
}

$Arguments = @($Retriever, "--query", $Query, "--top-k", $TopK)
if ($Json) {
    $Arguments += "--json"
}
if ($RebuildIndex) {
    $Arguments += "--rebuild-index"
}

& $VenvPython @Arguments
if ($LASTEXITCODE -ne 0) {
    throw "La consulta RAG termino con codigo $LASTEXITCODE"
}
