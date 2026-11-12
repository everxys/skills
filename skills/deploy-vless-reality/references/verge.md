# Clash Verge Rev on the client: layers, checks, changes

Consolidated from the 2026-11-10 incident (Clash Verge Rev 2.5.10, verge-mihomo 1.19.33, TUN, fake-ip, host `everx`). Read-only check: `scripts/verge-check.ps1 [-File <profile>] [-Watch 75]`. It prints no secrets.

## Ask first

Changing Verge settings needs the user's explicit OK first. That covers `verge.yaml`, `config.yaml`, `Merge.yaml`, the active profile copy, restarts, and switching the current profile. Diagnose read-only, propose the change with its rollback, then act. Never switch the user's current profile to test another one.

## Where the effective config comes from

Verge writes `%APPDATA%\io.github.clash-verge-rev.clash-verge-rev\clash-verge.yaml`. It starts from the active profile copy (`profiles\<uid>.yaml`, uid = `current:` in `profiles.yaml`), then applies the global `profiles\Merge.yaml`, which overrides **every** profile (dns, ipv6, sniffer…). Last come `config.yaml` and the UI switches:

| Field | Profile | Effective comes from |
|---|---|---|
| `mixed-port`, `allow-lan`, `tun.*`, `external-controller` | ignored | UI / `config.yaml` |
| top-level `ipv6` | profile value | Verge's IPv6 switch = `config.yaml` `ipv6` (seen: profile `false`, effective `true`) |
| `dns`, `sniffer` | profile block | overridden key by key by global `Merge.yaml`; `dns_config.yaml` only when `enable_dns_settings: true` |

- Read the effective file, not the profile, and report effective values (port 7897, not the profile's 7890).
- Keys no layer sets (`tcp-concurrent`, `keep-alive-*`, `find-process-mode`) pass through. A bare `-t` accepts unknown keys, so passing `-t` does not prove a key is used.
- `Unregistered Clash configuration key String("ipv6"|"tun"); reloading configuration` appears when the UI toggles that switch, and each one triggers a full reload that drops connections. It is not a loop.
- Editing the profile copy changes nothing until Verge regenerates `clash-verge.yaml` (re-select the profile, or restart).

## Profile-level Merge, proxies extension, and fixed-exit listeners

Clash Verge Rev 2.5.10 gives each profile its own extension files (Merge, Script, Rules, Proxies, Groups). These are not the same as the global `profiles\Merge.yaml` above.

- The profile-level **Merge** does **not** process `append-proxies`. A node added there never appears in the effective config. Put or append nodes in that profile's **proxies** extension (append).
- Top-level keys that the profile Merge *does* pass through include `listeners`. A `mixed` listener on `127.0.0.1:<port>` with `proxy: <node name>` is a fixed-exit port: traffic to it always leaves via that node and **bypasses the rule set**.
- TUN does not intercept loopback. An app pointed at the fixed-exit port (for example `HTTPS_PROXY=127.0.0.1:7902`) exits through that listener's node; apps that ignore the proxy environment still go through TUN and the rules. Do not confuse these ports with Verge's mixed-port (effective 7897), which is the system/TUN entry and still follows rules.

Seen 2026-11-11: fixed-exit listeners on `127.0.0.1:7901` / `127.0.0.1:7902` added through the profile Merge worked; `append-proxies` in the same Merge file did not. The nodes themselves had to live in the profile's proxies extension.

> 固定出口端口（每国一个 127.0.0.1 端口、节点按国家放 `<clash目录>\nodes\<code>.yaml`、全局生效）现在用单独的 skill `clash-fixed-exits`（`C:\Users\everx\.agents\skills\clash-fixed-exits`）：全局 Script.js + file provider + 内核 home 里的 nodes junction。本节的 profile Merge 写法只作历史记录，新部署不要再用。

## Environment checklist (`verge-check.ps1` automates it)

1. `config.yaml` `ipv6` must be `false` when the client has no global IPv6. So must `Merge.yaml` `ipv6` / `dns.ipv6` and the generated profile. Otherwise fake AAAA answers (`2001:2::…` / `fdfe:…`) reach apps, then die as `fake DNS record missing` and get routed to a v4-only node.
2. The sniffer must be on, with `force-dns-mapping`, `parse-pure-ip` and `override-destination` for HTTP/TLS/QUIC. It is in generated profiles, and it belongs in `Merge.yaml` too because Merge wins. It recovers the domain from SNI/Host when a fake-IP mapping is gone: "missing" lines fell from ~366 to ~129 per 3 min.
3. `tun.stack` must be one of `system`, `gvisor`, `mixed` or `mips`. **`mips` is valid**: it is Clash Verge Rev's own TUN stack (confirmed by the user, 2026-11-10), not an error, so leave it alone. Flag only other values.
4. Rule-providers on loopback (e.g. `127.0.0.1:28768`, a local helper serving `dev\clash\blocklist.yaml`) must be listening. When they are not, mihomo silently keeps the cached `./rules/my_blocklist.yaml`. It was dead at 14:00 and up again at 15:20 that day, so check each time.
5. Rules: `GEOSITE,cn,DIRECT` already covers domestic sites. Measured: baidu, bilibili, taobao, jd, qq, 163, zhihu, weibo and alicdn all matched `GeoSite(cn) → DIRECT`, and none ever hit a later `GEOIP,CN`. Keep exactly one `GEOIP,CN,DIRECT,no-resolve` as a backstop. Do not add `GEOSITE,CN` / `GEOIP,CN` without `no-resolve`: the user tried that and reverted it.
6. The proxy guard (`enable_proxy_guard`, 30 s) is **not** what flushes fake-ip (below).

## fake-ip pool flushed every 30 s

- **Meaning of `[Metadata PreHandle] error: fake DNS record 198.18.x.x missing`.** An app connected to a fake IP whose domain mapping is gone. Without the sniffer the connection reaches `MATCH` as a bare IP, and the node cannot dial it.
- **Detection: marker domain.** Once a second, run `Clear-DnsClientCache; Resolve-DnsName vrmark-<random>.example.org -Type A -DnsOnly`. A stable pool returns the same fake IP. A flush gives a new one, restarting near `198.18.0.4` (the pool start) with ~30 s gaps. `verge-check.ps1 -Watch 75` does this.
- **Trigger, by elimination.**
  - With the guard off, it still flushes.
  - With the `clash-verge.exe` GUI suspended for 70 s, it still flushes.
  - With `clash-verge-service.exe` (the core's parent) suspended for 42 s, the tick stopped.
  - A temporary mihomo started from the same config without the service and without TUN stayed stable.
  - No config reload appeared in the core's debug log, and there were no route or network events.
  - Conclusion: likely Verge service mode. Not proven, and no service log exists. Next step, with the user's OK: run the core in sidecar (non-service) mode for 2 minutes, or update Verge/the service, then report upstream.
- **Impact after the mitigations** (IPv6 off, sniffer on): Google through TUN went 39/39 and 42/42 OK, median ~0.6 s, across the flush ticks.

## Testing: bypassing TUN is not enough

`client-test.ps1` binds a temporary mihomo to the NIC and **bypasses** TUN. A clean result there (600/600 over 10 min) proves the node and the line, not the user's TUN path. Before calling a profile stable, always run a TUN-path round of at least 65 s (crossing two 30 s ticks): `verge-check.ps1 -Watch 75`. Occasional `dial 节点选择 … context deadline exceeded` to a NAT VPS node is loss on the line, not a config error.

`-Watch` is passive. It only sends DNS queries for a random `.example.org` name and `generate_204` GETs. It makes no API call, no reload, no route or adapter change, and no DNS-cache flush (removed 2026-11-10: unnecessary because fake-ip answers have TTL 1).

**Network drops during a check: prove the cause before blaming the config.** Read `Microsoft-Windows-NCSI/Operational` event 4042 on the physical NIC. `ChangeReason: SuspectArpProbeFailed` means Windows could not ARP the default gateway: a Wi-Fi/LAN/router problem below Clash, which TUN cannot cause. Also check Verge `logs\latest.log` for `[Validate]`/`[Config]` lines (reload, profile switch), check that the PIDs of `clash-verge`, `clash-verge-service` and `verge-mihomo` are unchanged (no restart or crash), check the WLAN-AutoConfig and Dhcp-Client logs, and check the node (`rc-service xray status`, cgroup `oom_kill`). Seen 2026-11-10 15:27–15:34: ARP probe to the gateway failed at 15:28:40. There was no Verge reload, no core restart and no VPS fault; it recovered at 15:34:20.

## Changing and reloading (after the user agreed)

1. **Back up** every file you touch to `C:\Users\everx\dev\clash-backups\<yyyyMMdd-HHmmss>\` (`verge-appdata\…`, `dev-clash\…`) and compare hashes.
2. Edit the right layer: profile copy plus `dev\clash` source, `Merge.yaml`, or `config.yaml`/`verge.yaml`. Run `verge-mihomo.exe -t -d <verge dir> -f <file>` and print only pass/fail.
3. **Reload without a restart:** `PUT http://127.0.0.1:9090/configs?force=true` with `Authorization: Bearer <secret from clash-verge.yaml, never printed>` and body `{"path":"","payload":"<full clash-verge.yaml text>"}`. `path` is rejected (400 "not subpath of home directory or SAFE_PATHS") because the service core's home is under ProgramData. Apply the same edit to `clash-verge.yaml` first. Verify with `GET /rules` and `GET /configs`. `/rules` does not show `no-resolve`, so check that in the file.
4. **Restart when needed** (settings in `verge.yaml`/`config.yaml`): Verge runs elevated, so `Stop-Process` from a normal shell fails. From an elevated PowerShell (`Start-Process powershell -Verb RunAs …`), kill `clash-verge`, then run `Start-ScheduledTask 'Clash Verge (Admin)'`. Afterwards check the processes, TUN and `current:`.
5. **Rollback:** copy the backup files back, hash-check them, `-t`, then reload (step 3) or restart (step 4).

## Comparing with an airport subscription (e.g. SakuraCat)

"SakuraCat is always stable, the VPS profile is flaky." The DNS is not the difference: both use fake-ip `198.18.0.1/16` with `dns.ipv6: false`, and the global Merge applies identically to both. The difference is the line and failover:

- SakuraCat: 103 trojan nodes on IEPL private lines (SG/US), a `url-test` group, and 867 rules (~770 domain rules).
- The VPS profile: one NAT VPS node on a public cross-border path (~150 ms, occasional connect timeouts) in a single `select` group.

Suggestions: add a second node/VPS behind a `url-test`/`fallback` group, or keep the airport as primary and the VPS as backup. Do not copy airport DNS settings expecting a fix.
