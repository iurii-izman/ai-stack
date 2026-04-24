$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "stack.ps1") smoke
exit $LASTEXITCODE
