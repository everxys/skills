<#
.SYNOPSIS
  OPTIONAL. Install (or -Uninstall) a scheduled task that runs make-junction.ps1 as SYSTEM
  at startup and every N minutes, re-creating <core home>\nodes if Verge/service removed it.
  Only install after the user explicitly agrees. Needs admin (one UAC).
.DESCRIPTION
  Copies make-junction.ps1 to %ProgramData%\clash-fixed-exits\ and locks that folder to
  SYSTEM/Administrators (write) + Users (read), so a SYSTEM task never runs a user-writable script.
#>
param(
  [string]$NodesDir = (Join-Path $HOME 'dev\clash\nodes'),
  [string]$UserSid = ([Security.Principal.WindowsIdentity]::GetCurrent().User.Value),
  [int]$RepeatMinutes = 30,
  [string]$TaskName = 'ClashFixedExits-Junction',
  [switch]$Uninstall
)
$ErrorActionPreference = 'Stop'
$p = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  $exe = (Get-Process -Id $PID).Path
  $a = @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + $PSCommandPath + '"'),
         '-NodesDir',('"' + [IO.Path]::GetFullPath($NodesDir) + '"'),'-UserSid',$UserSid,
         '-RepeatMinutes',$RepeatMinutes,'-TaskName',$TaskName)
  if ($Uninstall) { $a += '-Uninstall' }
  $r = Start-Process -FilePath $exe -ArgumentList $a -Verb RunAs -Wait -PassThru
  exit $r.ExitCode
}

$dir = Join-Path $env:ProgramData 'clash-fixed-exits'
if ($Uninstall) {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
  if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
  Write-Host "removed task $TaskName and $dir (the junction itself is left in place)"
  exit 0
}

New-Item -ItemType Directory -Force -Path $dir | Out-Null
Copy-Item (Join-Path $PSScriptRoot 'make-junction.ps1') (Join-Path $dir 'make-junction.ps1') -Force
icacls $dir /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-32-545:(OI)(CI)RX' | Out-Null

$script = Join-Path $dir 'make-junction.ps1'
$log = Join-Path $dir 'junction.log'
$arg = "-NoProfile -ExecutionPolicy Bypass -File `"$script`" -NodesDir `"$([IO.Path]::GetFullPath($NodesDir))`" -UserSid $UserSid -LogPath `"$log`" -Quiet"
$action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Argument $arg
$t1 = New-ScheduledTaskTrigger -AtStartup
$t2 = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $RepeatMinutes)
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 2) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($t1,$t2) -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Start-Sleep 3
Write-Host "installed $TaskName (SYSTEM, at startup + every $RepeatMinutes min). Log: $log"
if (Test-Path $log) { Get-Content $log -Tail 5 }
