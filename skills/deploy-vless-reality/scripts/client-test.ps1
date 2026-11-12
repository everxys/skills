# Client-side end-to-end test on a Windows host that runs Clash Verge Rev in TUN mode.
# Starts a TEMPORARY mihomo (Verge's own binary) bound to the physical NIC, so neither the test
# traffic nor the raw-path probes go through Verge's TUN; nothing in Verge or its profiles changes.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File client-test.ps1 -Profile <yaml> -Node <name> -Server <ip> -Port <public port> [-Iface <alias>]
# If -Iface is omitted, the adapter that owns the default IPv4 route is used (TUN / Mihomo excluded).
# Prints the chosen NIC, exit IP, delay, 20x generate_204, download speed, TCP ping + closed-port control, ICMP, domestic uplink.
# Prints NO secrets; the temp dir holding the copied proxy entry is deleted at the end.
param([Parameter(Mandatory)]$Profile, [Parameter(Mandatory)]$Node, [Parameter(Mandatory)]$Server,
      [Parameter(Mandatory)][int]$Port, $Iface = $null, $Mihomo = 'C:\Program Files\Clash Verge\verge-mihomo.exe')
$ErrorActionPreference = 'Continue'
if ([string]::IsNullOrWhiteSpace($Iface)) {
  $route = Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' |
    Where-Object { $_.NextHop -ne '0.0.0.0' } |
    Sort-Object RouteMetric, InterfaceMetric |
    Select-Object -First 1
  if (-not $route) { 'no default IPv4 route found'; exit 1 }
  $ad = Get-NetAdapter -InterfaceIndex $route.InterfaceIndex -ErrorAction SilentlyContinue
  if (-not $ad) { "no adapter for default route ifIndex $($route.InterfaceIndex)"; exit 1 }
  if ($ad.Name -match 'Mihomo|Meta|Wintun|Clash') { "default route is on TUN ($($ad.Name)), not a physical NIC"; exit 1 }
  if ($ad.Status -ne 'Up') { "default-route NIC $($ad.Name) is $($ad.Status)"; exit 1 }
  $Iface = $ad.Name
}
"using_iface=$Iface"
$work = Join-Path $env:TEMP ("vr-test-" + [guid]::NewGuid().ToString('N').Substring(0,8)); New-Item -ItemType Directory -Force $work | Out-Null
$src = Get-Content -Raw $Profile
# take only the entry of $Node from the profile's proxies: list
$prox = [regex]::Match($src, "(?ms)^  - name: $([regex]::Escape($Node))\r?\n.*?(?=^  - name: |^\S|\z)").Value.TrimEnd()
if (-not $prox) { "node $Node not found in $Profile"; exit 1 }
$cfg = "mixed-port: 17897`nallow-lan: false`nmode: rule`nlog-level: warning`nipv6: false`ninterface-name: $Iface`nexternal-controller: 127.0.0.1:19097`ndns:`n  enable: false`nproxies:`n$prox`n    interface-name: $Iface`nrules:`n  - MATCH,$Node`n"
Set-Content -Path "$work\t.yaml" -Value $cfg -Encoding utf8
& $Mihomo -t -d $work -f "$work\t.yaml" 2>&1 | Select-Object -Last 1
$p = Start-Process -FilePath $Mihomo -ArgumentList '-d',$work,'-f',"$work\t.yaml" -PassThru -WindowStyle Hidden -RedirectStandardOutput "$work\out.log" -RedirectStandardError "$work\err.log"
Start-Sleep 3
try {
  $px = 'http://127.0.0.1:17897'; $api = 'http://127.0.0.1:19097'
  "exit_ip_v4=" + (curl.exe -s -m 15 -x $px https://api.ipify.org)
  "exit_ip_64=" + (curl.exe -s -m 15 -x $px https://api64.ipify.org)
  $c0 = (Invoke-RestMethod "$api/connections").downloadTotal
  $d = 1..10 | % { try { (Invoke-RestMethod "$api/proxies/$([uri]::EscapeDataString($Node))/delay?url=https%3A%2F%2Fwww.gstatic.com%2Fgenerate_204&timeout=5000").delay } catch { -1 } }
  "mihomo_delay_ms=" + ($d -join ',')
  $t = 1..20 | % { curl.exe -s -o NUL -m 10 -x $px -w '%{http_code} %{time_total}' https://www.gstatic.com/generate_204 }
  $ok = @($t | ? { $_ -like '204 *' }); $tt = @($ok | % { [double]($_.Split(' ')[1]) } | Sort-Object)
  if ($tt.Count) { "gen204 ok=$($ok.Count)/20 min=$([math]::Round($tt[0],3)) median=$([math]::Round($tt[[int]($tt.Count/2)],3)) max=$([math]::Round($tt[-1],3))" } else { "gen204 ok=0/20" }
  foreach ($u in 'https://speed.cloudflare.com/__down?bytes=50000000','http://cachefly.cachefly.net/50mb.test') {  # 50mb.test is really 100 MiB
    $a = (curl.exe -s -o NUL -m 40 -x $px -w '%{http_code} %{size_download} %{speed_download} %{time_total}' $u).Split(' ')
    "download $u code=$($a[0]) bytes=$($a[1]) MBps=$([math]::Round([double]$a[2]/1MB,2)) Mbps=$([math]::Round([double]$a[2]*8/1e6,1)) time=$($a[3])"
  }
  "mihomo_download_total_delta_MB=" + [math]::Round(((Invoke-RestMethod "$api/connections").downloadTotal - $c0)/1MB,1)
} finally { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
$nic = (Get-NetIPAddress -InterfaceAlias $Iface -AddressFamily IPv4).IPAddress
function TcpPing($ip, $port, $n) { for ($i = 0; $i -lt $n; $i++) {
  $s = New-Object Net.Sockets.Socket([Net.Sockets.AddressFamily]::InterNetwork, [Net.Sockets.SocketType]::Stream, [Net.Sockets.ProtocolType]::Tcp)
  $s.Bind((New-Object Net.IPEndPoint([Net.IPAddress]::Parse($nic), 0))); $sw = [Diagnostics.Stopwatch]::StartNew()
  $ar = $s.BeginConnect($ip, $port, $null, $null)
  if ($ar.AsyncWaitHandle.WaitOne(3000) -and $s.Connected) { $sw.Elapsed.TotalMilliseconds } else { -1 }
  $s.Close(); Start-Sleep -Milliseconds 300 } }
$g = @(TcpPing $Server $Port 30 | ? { $_ -ge 0 } | Sort-Object)
"tcp_ping ${Port} via ${Iface}: sent=30 ok=$($g.Count) loss=$([math]::Round((30-$g.Count)/30*100,1))% min=$([math]::Round($g[0],1)) avg=$([math]::Round(($g|Measure-Object -Average).Average,1)) max=$([math]::Round($g[-1],1)) over1s=$(@($g|?{$_ -gt 1000}).Count)"
"control closed port 9999 (must be -1, else TUN is answering and every probe is void): " + ((TcpPing $Server 9999 2) -join ',')
"icmp: " + ((ping -n 20 -S $nic $Server | Select-String 'Packets|Minimum') -join ' | ')
"domestic uplink: " + ((ping -n 10 -S $nic 223.5.5.5 | Select-String 'Packets|Minimum') -join ' | ')
Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
"cleanup done"
