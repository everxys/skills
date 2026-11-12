[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('push', 'send', 'pull', 'get', 'devices', 'connect', 'pair', 'ls', 'shell', 'install')]
    [string]$Action = 'devices',

    [Parameter(Position = 1)]
    [string]$Path1,

    [Parameter(Position = 2)]
    [string]$Path2,

    [Parameter()]
    [string]$Device,

    [Parameter()]
    [string]$AdbPath
)

$ErrorActionPreference = 'Stop'

function Find-Adb {
    param([string]$CustomPath)
    if ($CustomPath -and (Test-Path -LiteralPath $CustomPath)) {
        return (Resolve-Path -LiteralPath $CustomPath).ProviderPath
    }
    $inPath = Get-Command adb -ErrorAction SilentlyContinue
    if ($inPath) {
        return $inPath.Source
    }
    $candidates = @(
        "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe",
        "$env:USERPROFILE\AppData\Local\Android\Sdk\platform-tools\adb.exe",
        "$env:ProgramFiles\Android\platform-tools\adb.exe",
        "${env:ProgramFiles(x86)}\Android\android-sdk\platform-tools\adb.exe",
        "$env:ProgramData\chocolatey\bin\adb.exe",
        "$env:USERPROFILE\scoop\shims\adb.exe"
    )
    foreach ($cand in $candidates) {
        if ($cand -and (Test-Path -LiteralPath $cand)) {
            return (Resolve-Path -LiteralPath $cand).ProviderPath
        }
    }
    throw "adb.exe not found! Please install Android SDK platform-tools or specify -AdbPath."
}

$adb = Find-Adb $AdbPath

function Get-AdbDevices {
    $raw = & $adb devices -l
    $list = @()
    foreach ($line in ($raw -split "`r?`n")) {
        $trim = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($trim) -or $trim.StartsWith("List of devices")) {
            continue
        }
        if ($trim -match '^([^\s]+)\s+([^\s]+)(.*)$') {
            $serial = $matches[1]
            $state = $matches[2]
            $extra = $matches[3]
            $model = if ($extra -match 'model:([^\s]+)') { $matches[1] } else { '' }
            $product = if ($extra -match 'product:([^\s]+)') { $matches[1] } else { '' }
            $list += [PSCustomObject]@{
                Serial  = $serial
                State   = $state
                Model   = $model
                Product = $product
                Raw     = $trim
            }
        }
    }
    return $list
}

function Resolve-TargetDevice {
    param([string]$Requested)
    $all = Get-AdbDevices
    $online = $all | Where-Object { $_.State -eq 'device' }
    if ($online.Count -eq 0) {
        throw "No active Android device found! Connect via USB or run: .\transfer.ps1 connect <ip>[:port]"
    }
    if ($Requested) {
        $match = $online | Where-Object {
            $_.Serial -ieq $Requested -or
            $_.Model -ieq $Requested -or
            $_.Product -ieq $Requested -or
            $_.Serial.Contains($Requested)
        }
        if ($match) {
            return $match[0].Serial
        }
        throw "Specified device '$Requested' not found. Available online devices: $($online.Serial -join ', ')"
    }
    if ($online.Count -eq 1) {
        return $online[0].Serial
    }
    # Multiple devices: default to first
    return $online[0].Serial
}

switch ($Action.ToLower()) {
    'devices' {
        $devs = Get-AdbDevices
        if ($devs.Count -eq 0) {
            Write-Host "No devices detected." -ForegroundColor Yellow
        } else {
            Write-Host "Connected devices:" -ForegroundColor Green
            $devs | Format-Table -Property Serial, State, Model, Product -AutoSize
        }
    }

    'connect' {
        if (-not $Path1) {
            throw "Usage: .\transfer.ps1 connect <ip:port>"
        }
        $addr = $Path1
        if (-not ($addr -match ':\d+$')) {
            $addr = "$addr`:5555"
        }
        Write-Host "Connecting to $addr..."
        & $adb connect $addr
    }

    'pair' {
        if (-not $Path1 -or -not $Path2) {
            throw "Usage: .\transfer.ps1 pair <ip:port> <code>"
        }
        Write-Host "Pairing with $Path1 using code $Path2..."
        & $adb pair $Path1 $Path2
    }

    { $_ -in @('push', 'send') } {
        if (-not $Path1) {
            throw "Usage: .\transfer.ps1 push <local-path> [remote-path] [-Device <device>]"
        }
        $local = (Resolve-Path -LiteralPath $Path1).ProviderPath
        $targetDev = Resolve-TargetDevice $Device
        $remote = if ($Path2) { $Path2.Replace('\', '/') } else { "/sdcard/Download/" }

        # If remote is directory, calculate final remote file path for media scanner
        $fileName = Split-Path -Leaf $local
        $finalRemote = if ($remote.EndsWith('/')) {
            "${remote}${fileName}"
        } elseif (-not (Split-Path -Extension $remote)) {
            "${remote}/${fileName}"
        } else {
            $remote
        }

        Write-Host "Sending: $local" -ForegroundColor Cyan
        Write-Host "Target Device: $targetDev" -ForegroundColor Cyan
        Write-Host "Remote Path: $remote" -ForegroundColor Cyan

        & $adb -s $targetDev push $local $remote
        if ($LASTEXITCODE -ne 0) {
            throw "adb push failed with exit code $LASTEXITCODE"
        }

        # Trigger Android media scanner to refresh file visibility in File Manager / Gallery
        try {
            & $adb -s $targetDev shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d "file://$finalRemote" *>$null
        } catch {
            # Ignore scan failures on custom roms
        }

        Write-Host "File successfully transferred to: $finalRemote" -ForegroundColor Green
    }

    { $_ -in @('pull', 'get') } {
        if (-not $Path1) {
            throw "Usage: .\transfer.ps1 pull <remote-path> [local-path] [-Device <device>]"
        }
        $targetDev = Resolve-TargetDevice $Device
        $remote = $Path1.Replace('\', '/')
        $local = if ($Path2) { $Path2 } else { "." }

        Write-Host "Pulling: $remote from $targetDev to $local..." -ForegroundColor Cyan
        & $adb -s $targetDev pull $remote $local
        if ($LASTEXITCODE -ne 0) {
            throw "adb pull failed with exit code $LASTEXITCODE"
        }
        Write-Host "File successfully pulled to: $local" -ForegroundColor Green
    }

    'install' {
        if (-not $Path1) {
            throw "Usage: .\transfer.ps1 install <path-to-apk> [-Device <device>]"
        }
        $apk = (Resolve-Path -LiteralPath $Path1).ProviderPath
        $targetDev = Resolve-TargetDevice $Device
        Write-Host "Installing APK $apk on ${targetDev}..." -ForegroundColor Cyan
        & $adb -s $targetDev install -r $apk
        if ($LASTEXITCODE -ne 0) {
            throw "adb install failed with exit code $LASTEXITCODE"
        }
        Write-Host "APK successfully installed!" -ForegroundColor Green
    }

    'ls' {
        $targetDev = Resolve-TargetDevice $Device
        $remote = if ($Path1) { $Path1.Replace('\', '/') } else { "/sdcard/Download/" }
        Write-Host "Listing $remote on ${targetDev}:" -ForegroundColor Cyan
        & $adb -s $targetDev shell ls -la $remote
    }

    'shell' {
        if (-not $Path1) {
            throw "Usage: .\transfer.ps1 shell <command> [-Device <device>]"
        }
        $targetDev = Resolve-TargetDevice $Device
        & $adb -s $targetDev shell $Path1
    }
}
