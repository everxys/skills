<#
.SYNOPSIS
  Read-only check of fixed-exit ports: provider state via the controller + exit IP per port.
  Prints no secret (controller secret is read from clash-verge.yaml and never echoed).
.PARAMETER ScriptPath  Global Script.js; ports/codes are parsed from its FIXED_EXITS table.
.PARAMETER Refresh     Also PUT /providers/proxies/nodes-<code> (re-read node files) first.
#>
param(
  [string]$VergeDir = (Join-Path $env:APPDATA 'io.github.clash-verge-rev.clash-verge-rev'),
  [string]$ScriptPath = '',
  [string]$MixedPort = '7897',
  [switch]$Refresh
)
$ErrorActionPreference = 'Stop'
if (-not $ScriptPath) { $ScriptPath = Join-Path $VergeDir 'profiles\Script.js' }
$cfg = Join-Path $VergeDir 'clash-verge.yaml'

function Get-YamlScalar([string]$file, [string]$key) {
  $m = Select-String -Path $file -Pattern ('^' + [regex]::Escape($key) + ':\s*(.*)$') | Select-Object -First 1
  if (-not $m) { return '' }
  return $m.Matches[0].Groups[1].Value.Trim().Trim("'").Trim('"')
}
$ctrl = Get-YamlScalar $cfg 'external-controller'; if (-not $ctrl) { $ctrl = '127.0.0.1:9090' }
$secretValue = Get-YamlScalar $cfg 'secret'
$headers = @{}; if ($secretValue) { $headers['Authorization'] = 'Bearer ' + $secretValue }
$base = 'http://' + $ctrl

$exits = @()
$text = Get-Content $ScriptPath -Raw -Encoding UTF8
foreach ($m in [regex]::Matches($text, 'code:\s*"([a-z0-9]+)"[^}]*?port:\s*(\d+)')) {
  $exits += [pscustomobject]@{ Code = $m.Groups[1].Value; Port = [int]$m.Groups[2].Value }
}
if (-not $exits) {
  # fallback: older scripts without FIXED_EXITS, read listeners named fixed-<code>-in
  foreach ($m in [regex]::Matches($text, 'name:\s*"fixed-([a-z0-9]+)-in"[^}]*?port:\s*(\d+)')) {
    $exits += [pscustomobject]@{ Code = $m.Groups[1].Value; Port = [int]$m.Groups[2].Value }
  }
}
if (-not $exits) { Write-Host "no FIXED_EXITS entries parsed from $ScriptPath"; exit 2 }

foreach ($e in $exits) {
  $name = 'nodes-' + $e.Code
  try {
    if ($Refresh) { Invoke-RestMethod -Method Put -Uri "$base/providers/proxies/$name" -Headers $headers | Out-Null }
    $p = Invoke-RestMethod -Uri "$base/providers/proxies/$name" -Headers $headers
    $nodes = @($p.proxies | ForEach-Object { $_.name }) -join ', '
    Write-Host ("{0}: vehicleType={1} nodes={2} [{3}]" -f $name, $p.vehicleType, @($p.proxies).Count, $nodes)
  } catch { Write-Host ("{0}: controller error ({1})" -f $name, $_.Exception.GetType().Name) }
}
$curl = "$env:SystemRoot\System32\curl.exe"
foreach ($port in @($exits | ForEach-Object { $_.Port }) + @([int]$MixedPort)) {
  $ip = & $curl -s --max-time 20 --proxy "http://127.0.0.1:$port" https://api.ipify.org 2>$null
  if ($LASTEXITCODE -ne 0 -or -not $ip) { $ip = "FAIL (curl exit $LASTEXITCODE)" }
  $tcp = Test-NetConnection 127.0.0.1 -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue
  Write-Host ("127.0.0.1:{0} tcp={1} exit={2}" -f $port, $tcp, $ip)
}
