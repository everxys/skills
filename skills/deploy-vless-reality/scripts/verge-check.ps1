# Read-only Clash Verge Rev environment check (Windows). Changes nothing and prints NO secrets: it
# reads only whitelisted keys, never the profile's proxies, never subscription or rule-provider URLs
# (a loopback provider prints host:port only).
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File verge-check.ps1 [-Watch 75] [-File <yaml>]
#   -Watch N  also test THROUGH TUN for N seconds (>= 65 crosses two 30 s ticks): a marker domain shows
#             fake-ip pool flushes, and generate_204 each second shows whether requests survive them.
#             A test that bypasses TUN (client-test.ps1) being stable does NOT prove TUN is stable.
#             Side effects: only DNS queries for a random .example.org name and HTTPS GETs; no API call,
#             no reload, no route or adapter change, no DNS-cache flush.
#   -File     also check a generated profile (e.g. C:\Users\everx\dev\clash\vps-<ip>.yaml) for the defaults.
param([int]$Watch = 0, [string]$File = '')
$ErrorActionPreference = 'Stop'
$dir = Join-Path $env:APPDATA 'io.github.clash-verge-rev.clash-verge-rev'
function Read-Text($p) { if (Test-Path $p) { [IO.File]::ReadAllText($p) } else { '' } }
function Get-Top($t, $k) { $m = [regex]::Match($t, "(?m)^$([regex]::Escape($k)):[ \t]*([^\r\n#]*)"); if ($m.Success) { $m.Groups[1].Value.Trim() } else { '<absent>' } }
function Get-Block($t, $k) { [regex]::Match($t, "(?ms)^$([regex]::Escape($k)):[^\r\n]*\r?\n(.*?)(?=^[A-Za-z#]|\z)").Groups[1].Value }
function Get-Sub($b, $k) { $m = [regex]::Match($b, "(?m)^[ ]{2}$([regex]::Escape($k)):[ \t]*([^\r\n#]*)"); if ($m.Success) { $m.Groups[1].Value.Trim() } else { '<absent>' } }
function Write-Check($level, $msg) { '{0,-5} {1}' -f $level, $msg }
function Test-ProfileText($label, $t) {
  $dns = Get-Block $t 'dns'; $sn = Get-Block $t 'sniffer'; $rules = Get-Block $t 'rules'
  $v6 = Get-Top $t 'ipv6'; $d6 = Get-Sub $dns 'ipv6'; $se = Get-Sub $sn 'enable'
  Write-Check $(if ($v6 -eq 'false') {'OK'} else {'WARN'}) "$label ipv6=$v6 (want false without client IPv6)"
  Write-Check $(if ($d6 -eq 'false') {'OK'} else {'WARN'}) "$label dns.ipv6=$d6"
  Write-Check $(if ($se -eq 'true') {'OK'} else {'WARN'}) "$label sniffer.enable=$se"
  foreach ($k in 'force-dns-mapping','parse-pure-ip','override-destination') { $v = Get-Sub $sn $k; if ($se -eq 'true' -and $v -ne 'true') { Write-Check 'WARN' "$label sniffer.$k=$v" } }
  Write-Check 'INFO' "$label dns.enhanced-mode=$(Get-Sub $dns 'enhanced-mode') fake-ip-range6=$(Get-Sub $dns 'fake-ip-range6')"
  $cnSite = ([regex]::Matches($rules, '(?mi)^\s*-\s*GEOSITE,cn,')).Count; $cnIp = ([regex]::Matches($rules, '(?mi)^\s*-\s*GEOIP,CN,')).Count
  $nr = [regex]::IsMatch($rules, '(?mi)^\s*-\s*GEOIP,CN,DIRECT,no-resolve\s*$')
  Write-Check $(if ($cnSite -eq 1 -and $cnIp -eq 1 -and $nr) {'OK'} elseif ($label -like 'effective*') {'INFO'} else {'WARN'}) "$label rules: GEOSITE cn x$cnSite, GEOIP CN x$cnIp, no-resolve=$nr (want 1/1/True; GEOSITE cn already covers domestic sites)"
  $rp = Get-Block $t 'rule-providers'
  foreach ($m in [regex]::Matches($rp, '(?m)^\s+url:\s*["'']?(https?://[^"''\s]+)')) {
    $u = [uri]$m.Groups[1].Value
    if ($u.IsLoopback) {
      $open = $false; try { $c = New-Object Net.Sockets.TcpClient; $c.Connect($u.Host, $u.Port); $open = $c.Connected; $c.Close() } catch { }
      Write-Check $(if ($open) {'OK'} else {'WARN'}) "$label rule-provider $($u.Host):$($u.Port) listening=$open (dead => mihomo keeps the cached file; fix or drop it)"
    } else { Write-Check 'INFO' "$label rule-provider remote (URL not shown)" }
  }
}
try {
  if (-not (Test-Path $dir)) { Write-Check 'FAIL' "Verge data dir not found: $dir"; exit 1 }
  foreach ($n in 'clash-verge','clash-verge-service','verge-mihomo') { Write-Check $(if (Get-Process $n -EA SilentlyContinue) {'OK'} else {'WARN'}) "process $n running=$([bool](Get-Process $n -EA SilentlyContinue))" }
  $verge = Read-Text "$dir\verge.yaml"; $cfg = Read-Text "$dir\config.yaml"; $merge = Read-Text "$dir\profiles\Merge.yaml"
  $profs = Read-Text "$dir\profiles.yaml"; $eff = Read-Text "$dir\clash-verge.yaml"
  $cur = Get-Top $profs 'current'
  $nm = [regex]::Match($profs, "(?m)^- uid:[ \t]*$([regex]::Escape($cur))[ \t]*\r?\n(?:[ ]{2}[^\r\n]*\r?\n)*?[ ]{2}name:[ \t]*([^\r\n]*)").Groups[1].Value
  Write-Check 'INFO' "current profile: $nm ($cur)"
  Write-Check 'INFO' "verge.yaml: enable_proxy_guard=$(Get-Top $verge 'enable_proxy_guard') enable_tun_mode=$(Get-Top $verge 'enable_tun_mode') enable_dns_settings=$(Get-Top $verge 'enable_dns_settings') (the proxy guard is NOT the 30 s fake-ip flush)"
  $uiV6 = Get-Top $cfg 'ipv6'; $stack = Get-Sub (Get-Block $cfg 'tun') 'stack'
  Write-Check $(if ($uiV6 -eq 'false') {'OK'} else {'WARN'}) "config.yaml (Verge UI switch) ipv6=$uiV6 - overrides every profile"
  Write-Check $(if ($stack -match '^(?i)(system|gvisor|mixed|mips|<absent>)$') {'OK'} else {'WARN'}) "config.yaml tun.stack=$stack (valid: system/gvisor/mixed, and mips = Clash Verge Rev's own stack)"
  Write-Check 'INFO' "global Merge.yaml (overrides every profile): ipv6=$(Get-Top $merge 'ipv6') dns.ipv6=$(Get-Sub (Get-Block $merge 'dns') 'ipv6') sniffer.enable=$(Get-Sub (Get-Block $merge 'sniffer') 'enable')"
  Test-ProfileText 'effective(clash-verge.yaml)' $eff
  Write-Check 'INFO' "effective tun.enable=$(Get-Sub (Get-Block $eff 'tun') 'enable') tun.stack=$(Get-Sub (Get-Block $eff 'tun') 'stack')"
  $g6 = @(Get-NetIPAddress -AddressFamily IPv6 -EA SilentlyContinue | ? { $_.IPAddress -match '^[23]' -and $_.InterfaceAlias -notmatch 'Mihomo|Meta|Wintun|Clash|Verge' })
  Write-Check 'INFO' "client global IPv6 addresses: $($g6.Count) (0 => keep every ipv6 switch off)"
  if ($File) { if (Test-Path $File) { Test-ProfileText "file($(Split-Path $File -Leaf))" (Read-Text $File) } else { Write-Check 'FAIL' "file not found: $File" } }
  if ($Watch -gt 0) {
    Write-Check 'INFO' "watching $Watch s through TUN (marker domain + generate_204)"
    $mk = 'vrmark-' + (Get-Random) + '.example.org'; $prev = ''; $flush = @(); $ok = 0; $n = 0; $slow = 0
    $end = (Get-Date).AddSeconds($Watch)
    while ((Get-Date) -lt $end) {
      # no Clear-DnsClientCache: it flushes the whole OS cache every second; fake-ip answers have TTL 1 anyway
      $ip = (Resolve-DnsName $mk -Type A -DnsOnly -QuickTimeout -EA SilentlyContinue | ? IPAddress | select -First 1).IPAddress
      if ($prev -and $ip -and $ip -ne $prev) { $flush += (Get-Date) }
      if ($ip) { $prev = $ip }
      $r = (& curl.exe -s -o NUL -m 8 -w '%{http_code} %{time_total}' https://www.google.com/generate_204) -split ' '
      $n++; if ($r[0] -eq '204') { $ok++; if ([double]$r[1] -gt 3) { $slow++ } }
      Start-Sleep -Milliseconds 1000
    }
    $gaps = for ($i = 1; $i -lt $flush.Count; $i++) { [math]::Round(($flush[$i] - $flush[$i-1]).TotalSeconds) }
    Write-Check $(if ($flush.Count -eq 0) {'OK'} else {'WARN'}) "fake-ip marker changed $($flush.Count)x at $(($flush | % { $_.ToString('HH:mm:ss') }) -join ',') gaps=$($gaps -join ',')s (regular ~30 s = pool flush; seen with clash-verge-service, not the guard)"
    Write-Check $(if ($ok -eq $n) {'OK'} else {'WARN'}) "google generate_204 via TUN: $ok/$n ok, >3s: $slow"
  }
} catch { Write-Check 'FAIL' 'check aborted (details suppressed)' }
