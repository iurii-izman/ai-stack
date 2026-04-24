# Quick PowerShell secret scan (refined)
Write-Host "Running refined PowerShell secret scan..."

$patterns = @(
    'sk-[A-Za-z0-9_-]{16,}',
    'AIza[0-9A-Za-z_-]{35,}',
    'ghp_[0-9A-Za-z_-]{36,}',
    'gho_[0-9A-Za-z_-]{36,}',
    'AKIA[0-9A-Z]{16,}',
    '-----BEGIN PRIVATE KEY-----'
)

$found = $false

if (Test-Path .git) {
    $files = git ls-files
} else {
    $files = Get-ChildItem -Recurse -File -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName
}

foreach ($f in $files) {
    # Skip .git, backups, node_modules and known whitelist files (CI, scripts, samples, docs)
    if ($f -match '\.git[\\/]') { continue }
    if ($f -match '[\\/]backups[\\/]') { continue }
    if ($f -match 'node_modules') { continue }
    if ($f -match '^\.github[\\/]') { continue }
    if ($f -match 'scripts[\\/]check-secrets') { continue }
    if ($f -match '\.sample') { continue }
    if ($f -match '\.md$') { continue }
    try {
        $content = Get-Content -Raw -ErrorAction SilentlyContinue $f
        foreach ($p in $patterns) {
            if ($content -match $p) {
                Write-Host "Potential secret match in: $f -> $p"
                $found = $true
                break
            }
        }
    } catch {
        # ignore read errors
    }
}

if ($found) { Write-Error "Potential secrets found. Review before committing."; exit 1 } else { Write-Host "No obvious secrets found."; exit 0 }
