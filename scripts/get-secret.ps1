param(
  [Parameter(Mandatory=$true)][string]$Name,
  [string]$Vault = ''
)

# Try Microsoft.PowerShell.SecretManagement first
try {
  if (Get-Command -Name Get-Secret -ErrorAction SilentlyContinue) {
    if ($Vault) {
      $secret = Get-Secret -Name $Name -Vault $Vault -ErrorAction Stop
    } else {
      $secret = Get-Secret -Name $Name -ErrorAction Stop
    }
    if ($secret -is [System.Security.SecureString]) {
      $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
      $plain = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
      [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
      Write-Output $plain
      exit 0
    } else {
      Write-Output $secret
      exit 0
    }
  }
} catch {
  # ignore and continue to next method
}

# Try CredentialManager module (Get-StoredCredential)
try {
  if (Get-Command -Name Get-StoredCredential -ErrorAction SilentlyContinue) {
    $target = "ai-stack:$Name"
    $cred = Get-StoredCredential -Target $target -ErrorAction SilentlyContinue
    if ($cred) {
      if ($cred -is [PSCustomObject] -and $cred.Password) {
        Write-Output $cred.Password
        exit 0
      } elseif ($cred -ne $null) {
        try {
          $net = $cred.GetNetworkCredential()
          if ($net.Password) { Write-Output $net.Password; exit 0 }
        } catch { }
      }
    }
  }
} catch {
  # ignore
}

# Fallback to secure local .env.local saved by installer
$secureDir = Join-Path $env:LOCALAPPDATA 'ai-stack-secrets'
$path = Join-Path $secureDir '.env.local'
if (Test-Path $path) {
  $lines = Get-Content $path -ErrorAction SilentlyContinue
  foreach ($line in $lines) {
    if ($line -match '^[\s]*' + [Regex]::Escape($Name) + '[\s]*=[\s]*(.*)$') {
      $m = [Regex]::Match($line, '^[\s]*' + [Regex]::Escape($Name) + '[\s]*=[\s]*(.*)$')
      Write-Output $m.Groups[1].Value
      exit 0
    }
  }
}

# Not found
exit 2
