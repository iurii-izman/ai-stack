$ErrorActionPreference = "Stop"
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    throw "python not found. Install Python 3.11+ to use stack.ps1."
}

& $python.Source (Join-Path $PSScriptRoot "ops\ai_stack.py") @Args
exit $LASTEXITCODE
