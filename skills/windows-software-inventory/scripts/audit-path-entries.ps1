# Audit Windows PATH entries and deletion-blocking ACLs. Read-only.
#   powershell -NoProfile -ExecutionPolicy Bypass -File audit-path-entries.ps1 [dir-to-scan-for-DENY ...]
# Reports: every PATH entry in both registry hives, whether its directory still
# exists, duplicates, and any DENY ACE under the given roots that will block rm -rf.

$ErrorActionPreference = 'Continue'

$hives = @(
  @{ Label = 'USER    (HKCU\Environment)'; Key = 'HKCU:\Environment' },
  @{ Label = 'MACHINE (HKLM ...\Environment)'; Key = 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Environment' }
)

foreach ($h in $hives) {
  Write-Output ""
  Write-Output "=== $($h.Label) ==="
  $raw = (Get-ItemProperty -Path $h.Key -Name Path -ErrorAction SilentlyContinue).Path
  if (-not $raw) { Write-Output '  <no Path value in this hive>'; continue }

  $seen = @{}
  $n = 0
  foreach ($entry in ($raw -split ';' | Where-Object { $_ -ne '' })) {
    $n++
    $expanded = [Environment]::ExpandEnvironmentVariables($entry)
    $exists = Test-Path -LiteralPath $expanded -PathType Container
    $key = $expanded.ToLower()
    $dup = $seen.ContainsKey($key)
    $seen[$key] = $true
    $flags = @()
    if (-not $exists) { $flags += 'MISSING' }
    if ($dup)         { $flags += 'DUPLICATE' }
    $mark = if ($flags.Count -gt 0) { '[' + ($flags -join ',') + ']' } else { 'ok' }
    Write-Output ('  {0,3}. {1,-18} {2}' -f $n, $mark, $entry)
  }
}

Write-Output ""
Write-Output '=== DENY ACEs (block rm -rf while no process holds the file) ==='
if ($args.Count -eq 0) {
  Write-Output '  pass one or more directories as arguments to scan them; nothing scanned.'
} else {
  foreach ($root in $args) {
    Write-Output "--- $root"
    if (-not (Test-Path -LiteralPath $root)) { Write-Output '  <missing>'; continue }
    $hits = 0
    Get-ChildItem -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object {
      $acl = Get-Acl -LiteralPath $_.FullName -ErrorAction SilentlyContinue
      if ($acl) {
        foreach ($r in @($acl.Access | Where-Object { $_.AccessControlType -eq 'Deny' })) {
          $hits++
          Write-Output ('  {0}  {1}  inherited={2}' -f $_.FullName, $r.FileSystemRights, $r.IsInherited)
        }
      }
    }
    if ($hits -eq 0) { Write-Output '  no DENY ACE' }
  }
}

Write-Output ""
Write-Output 'Remediation (run from PowerShell, not MSYS bash, which mangles DOMAIN\user):'
Write-Output "  icacls '<dir>' /remove:d '<DOMAIN\user>' /T /C /Q"
