<#
.SYNOPSIS
  Create <core home>\nodes -> <clash dir>\nodes junction for Clash Verge Rev service mode.
  Needs admin: when not elevated it relaunches itself once via UAC.
.DESCRIPTION
  Service-mode core home = %ProgramData%\clash-verge-service\users\<sha256(user SID), lower hex>\runtime
  (confirmed on Verge Rev 2.5.10: the hash is SHA-256 of the SID string, e.g. "S-1-5-21-...-1001").
  If that dir is missing, falls back to the only users\*\runtime that contains config.yaml.
  Never prints file contents. Exit code 0 = junction OK.
.PARAMETER NodesDir   Target folder holding <code>.yaml node files. Default: $HOME\dev\clash\nodes
.PARAMETER UserSid    SID of the Verge user. Default: current user (pass it explicitly when run as SYSTEM).
.PARAMETER RuntimeDir Override the detected core home.
.PARAMETER Force      Replace an existing junction that points elsewhere.
.PARAMETER Quiet      For the scheduled task: log only.
.PARAMETER WhatIf     Detect and report, change nothing (works without admin only for the hash part).
#>
param(
  [string]$NodesDir = (Join-Path $HOME 'dev\clash\nodes'),
  [string]$UserSid = ([Security.Principal.WindowsIdentity]::GetCurrent().User.Value),
  [string]$RuntimeDir = '',
  [string]$LogPath = '',
  [switch]$Force,
  [switch]$Quiet,
  [switch]$WhatIf
)
$ErrorActionPreference = 'Stop'
if (-not $LogPath) { $LogPath = Join-Path $env:TEMP 'clash-fixed-exits-junction.log' }

function Write-Log([string]$msg) {
  $line = (Get-Date -Format 'yyyy-MM-ddTHH:mm:ss') + ' ' + $msg
  Add-Content -Path $LogPath -Value $line -Encoding UTF8
  if (-not $Quiet) { Write-Host $msg }
}
function Get-SidHash([string]$sid) {
  $bytes = [Text.Encoding]::UTF8.GetBytes($sid)
  $sha = [Security.Cryptography.SHA256]::Create()
  return -join ($sha.ComputeHash($bytes) | ForEach-Object { $_.ToString('x2') })
}
function Test-Admin {
  $p = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
  return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

$NodesDir = [IO.Path]::GetFullPath($NodesDir)
$serviceUsers = Join-Path $env:ProgramData 'clash-verge-service\users'
$hash = Get-SidHash $UserSid
if (-not $RuntimeDir) { $RuntimeDir = Join-Path $serviceUsers ($hash + '\runtime') }

if ($WhatIf) {
  Write-Host "NodesDir   : $NodesDir (exists=$(Test-Path $NodesDir))"
  Write-Host "Expected   : $RuntimeDir"
  Write-Host "Admin      : $(Test-Admin)  (non-admin cannot list ProgramData\clash-verge-service\users)"
  exit 0
}

if (-not (Test-Admin)) {
  # Relaunch elevated once; pass the ORIGINAL user's SID and paths explicitly.
  $exe = (Get-Process -Id $PID).Path
  $argList = @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + $PSCommandPath + '"'),
               '-NodesDir',('"' + $NodesDir + '"'),'-UserSid',$UserSid,'-LogPath',('"' + $LogPath + '"'),'-Quiet')
  if ($RuntimeDir) { $argList += @('-RuntimeDir',('"' + $RuntimeDir + '"')) }
  if ($Force) { $argList += '-Force' }
  Write-Host 'Requesting elevation (UAC) ...'
  try { $p = Start-Process -FilePath $exe -ArgumentList $argList -Verb RunAs -Wait -PassThru }
  catch { Write-Host 'UAC was declined or failed.'; exit 3 }
  if (Test-Path $LogPath) { Get-Content $LogPath -Tail 15 | ForEach-Object { Write-Host $_ } }
  exit $p.ExitCode
}

try {
  Write-Log "start user=$env:USERNAME sidhash=$hash nodes=$NodesDir"
  if (-not (Test-Path $NodesDir)) { Write-Log "ERROR nodes dir not found: $NodesDir"; exit 4 }

  if (-not (Test-Path $RuntimeDir)) {
    $cands = @(Get-ChildItem $serviceUsers -Directory -ErrorAction SilentlyContinue |
      ForEach-Object { Join-Path $_.FullName 'runtime' } |
      Where-Object { Test-Path (Join-Path $_ 'config.yaml') })
    if ($cands.Count -eq 1) { Write-Log "expected home missing, using the only candidate: $($cands[0])"; $RuntimeDir = $cands[0] }
    else { Write-Log "ERROR core home not found; candidates=$($cands.Count): $($cands -join '; '). Start Verge in service mode first, or pass -RuntimeDir."; exit 5 }
  }

  $link = Join-Path $RuntimeDir 'nodes'
  if (Test-Path $link) {
    $item = Get-Item $link -Force
    $target = @($item.Target)[0]
    if ($item.LinkType -eq 'Junction' -and $target -and ([IO.Path]::GetFullPath($target).TrimEnd('\') -ieq $NodesDir.TrimEnd('\'))) {
      Write-Log "OK junction already present: $link -> $target"
    } elseif ($item.LinkType -eq 'Junction' -and $Force) {
      Write-Log "replacing junction that pointed to: $target"
      [IO.Directory]::Delete($link)   # removes only the link, not the target's files
      New-Item -ItemType Junction -Path $link -Target $NodesDir | Out-Null
      Write-Log "junction re-created: $link -> $NodesDir"
    } else {
      Write-Log "ERROR $link exists (LinkType='$($item.LinkType)' target='$target'); not touching it. Use -Force only for a wrong junction."
      exit 6
    }
  } else {
    New-Item -ItemType Junction -Path $link -Target $NodesDir | Out-Null
    Write-Log "junction created: $link -> $NodesDir"
  }
  $files = (Get-ChildItem $link -Filter *.yaml -File | ForEach-Object Name) -join ','
  Write-Log "visible through junction: $files"
  Write-Log 'done'
  exit 0
} catch {
  Write-Log ('ERROR ' + $_.Exception.GetType().Name)
  exit 1
}
