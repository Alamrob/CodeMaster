$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path) | Out-Null
Set-Location ".."

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "creando entorno aislado..."
    python -m venv .venv
    .venv\Scripts\python.exe -m pip install -q -e ".[dev]"
}

$py = ".venv\Scripts\python.exe"
$ruff = ".venv\Scripts\ruff.exe"
$mypy = ".venv\Scripts\mypy.exe"

& $ruff format --check .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $ruff check .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $mypy
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $py -m pytest
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $py -m codemaster identify --json src > $null
exit $LASTEXITCODE