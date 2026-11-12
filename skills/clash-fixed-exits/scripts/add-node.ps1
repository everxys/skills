<#
.SYNOPSIS
  Copy the node entries (top-level proxies: list) from a vps-<ip>.yaml profile into nodes\<code>.yaml.
  Backs up the target first, refuses duplicate names, prints only node names (never uuid/keys).
.EXAMPLE
  .\add-node.ps1 -From C:\Users\<user>\dev\clash\vps-203.0.113.10.yaml -Code us
#>
param(
  [Parameter(Mandatory)][string]$From,
  [Parameter(Mandatory)][ValidatePattern('^[a-z0-9]+$')][string]$Code,
  [string]$NodesDir = (Join-Path $HOME 'dev\clash\nodes'),
  [string]$Label = ''
)
$ErrorActionPreference = 'Stop'
try {
  $src = Get-Content $From -Encoding UTF8
  $block = New-Object System.Collections.Generic.List[string]
  $in = $false
  foreach ($line in $src) {
    if ($line -match '^proxies:\s*$') { $in = $true; continue }
    if ($in -and $line -match '^[^\s#]') { break }
    if ($in) { $block.Add($line) }
  }
  while ($block.Count -and -not $block[$block.Count-1].Trim()) { $block.RemoveAt($block.Count-1) }
  if (-not $block.Count) { Write-Host "no block-style top-level 'proxies:' found in $From"; exit 2 }
  $newNames = @($block | Where-Object { $_ -match '^\s*-\s*name:\s*(.+)$' } | ForEach-Object { ($_ -replace '^\s*-\s*name:\s*','').Trim().Trim("'").Trim('"') })
  if (-not $newNames) { Write-Host 'entries must start with "- name:" (block style); fix by hand'; exit 2 }

  $dst = Join-Path $NodesDir ($Code + '.yaml')
  if (-not (Test-Path $NodesDir)) { New-Item -ItemType Directory -Path $NodesDir | Out-Null }
  if (Test-Path $dst) {
    $old = Get-Content $dst -Encoding UTF8
    $oldNames = @($old | Where-Object { $_ -match '^\s*-\s*name:\s*(.+)$' } | ForEach-Object { ($_ -replace '^\s*-\s*name:\s*','').Trim().Trim("'").Trim('"') })
    $dup = @($newNames | Where-Object { $oldNames -contains $_ })
    if ($dup) { Write-Host ("duplicate node name(s) already in {0}: {1}" -f $dst, ($dup -join ', ')); exit 3 }
    if (-not ($old | Where-Object { $_ -match '^proxies:\s*(\[\])?\s*$' })) { Write-Host "$dst has no top-level proxies:; fix by hand"; exit 2 }
    $bak = $dst + '.bak-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
    Copy-Item $dst $bak
    $old = $old | ForEach-Object { $_ -replace '^proxies:\s*\[\]\s*$', 'proxies:' }
    $out = @($old) + @($block)
    Write-Host "backup: $bak"
  } else {
    $first = "# $Code fixed-exit nodes -> provider nodes-$Code"
    if ($Label) { $first += " / group 固定$Label" }
    $hdr = @($first,
             '# Contains secrets: keep out of shared folders and version control.',
             'proxies:')
    $out = $hdr + @($block)
  }
  $utf8 = New-Object System.Text.UTF8Encoding($false)
  [IO.File]::WriteAllText($dst, (($out -join "`n") + "`n"), $utf8)
  Write-Host ("added to {0}: {1}" -f $dst, ($newNames -join ', '))
  Write-Host "next: refresh provider nodes-$Code (Verge Proxies page -> 代理集合, or verify.ps1 -Refresh)"
} catch {
  Write-Host ('failed: ' + $_.Exception.GetType().Name)   # never print exception text (may echo file lines)
  exit 1
}
