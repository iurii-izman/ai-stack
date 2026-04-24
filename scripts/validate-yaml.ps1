Param()

Write-Host "Running YAML validation (PowerShell wrapper)..."

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Error "Python is required to validate YAML files. Install Python and PyYAML (pip install pyyaml)."
    exit 1
}

$tmp = [System.IO.Path]::GetTempFileName()
$py = @'
import sys, subprocess, os
try:
    import yaml
except Exception:
    print('PyYAML not installed. Install with: pip install pyyaml', file=sys.stderr)
    sys.exit(1)

files = []
if os.path.isdir('.git'):
    try:
        out = subprocess.check_output(['git','ls-files','*.yaml','*.yml']).decode().strip()
        if out:
            files = out.splitlines()
    except Exception:
        pass
if not files:
    for root, dirs, filenames in os.walk('.'):
        if '.git' in root.split(os.sep) or 'node_modules' in root.split(os.sep):
            continue
        for fn in filenames:
            if fn.endswith(('.yaml', '.yml')):
                files.append(os.path.join(root, fn))

errors = 0
for f in files:
    try:
        with open(f, 'r', encoding='utf-8') as fh:
            yaml.safe_load(fh)
        print('OK  ' + f)
    except Exception as e:
        print('ERROR ' + f + ' -> ' + str(e))
        errors += 1

if errors:
    sys.exit(2)
'@

Set-Content -Path $tmp -Value $py -Encoding UTF8

& python $tmp
$exit = $LASTEXITCODE
Remove-Item $tmp -ErrorAction SilentlyContinue
if ($exit -ne 0) { exit $exit } else { Write-Host "YAML validation completed."; exit 0 }
