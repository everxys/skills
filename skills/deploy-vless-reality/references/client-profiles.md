# Client output: Clash Verge Rev / mihomo profile and share links

## What `gen-client.sh` prints (from the state file)

| Mode | Output |
|---|---|
| `--profile` | **default hand-over**: a complete standalone Clash Verge Rev profile (below) |
| (none) | `proxies:` + `proxy-groups:` snippet and share links |
| `--proxies-only` | `proxies:` + links, no groups (for merging into a profile that has its own `节点选择`) |
| `--links-only` / `--yaml-only` | links only / snippet only |

Options: `--blocklist-url URL` (default `http://127.0.0.1:28768/blocklist.yaml`, the local helper on host `everx`), `--no-blocklist`. Test with fake data: `VR_STATE=/path/fake.env sh gen-client.sh --profile`.

The output contains secrets in clear text for the owner's own config. Never paste it into shared logs, tickets or transcripts, keep generated profiles out of version control, and report only the path.

## Defaults of `--profile` (2026-11-10 user decisions)

- **One IPv4 node** `<NAME>-v4` in a `节点选择` select group. A `<NAME>-v6` entry plus a `<NAME>-auto` fallback group (`generate_204`, `interval: 300`, `timeout: 3000`, `lazy: true`) appear only after `install.sh --ipv6` / `--public-v6`.
- **`ipv6: false` and `dns.ipv6: false`.** They become `true` only when a v6 entry exists. Verge's own IPv6 switch and the global `Merge.yaml` override these lines, so keep them consistent ([verge.md](verge.md#where-the-effective-config-comes-from)).
- **Sniffer on**: `force-dns-mapping`, `parse-pure-ip`, `override-destination`; HTTP 80/8080-8880, TLS and QUIC 443/8443.
- **DNS**: fake-ip `198.18.0.1/16` with a small `fake-ip-filter` (`*.lan`, `*.local`, msftconnecttest/msftncsi, `time.*.com`, `ntp.*.com`). `default-nameserver` is 223.5.5.5 / 119.29.29.29; `nameserver` and `proxy-server-nameserver` are doh.pub and alidns DoH.
- **Rules** (the user's structure, in this order): `RULE-SET,my_blocklist,REJECT` → `GEOSITE,private,DIRECT` → `GEOSITE,cn,DIRECT` → `GEOIP,CN,DIRECT,no-resolve` → `DOMAIN-KEYWORD,google` / `DOMAIN-KEYWORD,gmail` / `DOMAIN-SUFFIX,google.com` → `节点选择` → `MATCH,节点选择`. `GEOSITE cn` already catches domestic sites. **Do not add more CN rules or drop `no-resolve`**: tried and reverted 2026-11-10, with no routing difference.
- **Omitted**, because Verge overrides them: `mixed-port`, `port`, `socks-port`, `allow-lan`, `tun`, `external-controller`.

Proxy entry shape (validated with mihomo 1.19.33 `-t`):

```yaml
- name: VPS-amd-v4
  type: vless
  server: "203.0.113.7"     # quote IPv6 literals too
  port: 26417               # public (mapped) port, not the internal one
  uuid: UUID
  network: tcp
  udp: true
  tls: true
  flow: xtls-rprx-vision
  servername: www.amd.com
  client-fingerprint: chrome
  reality-opts:
    public-key: PUBLIC_KEY
    short-id: SHORT_ID
```

Share link: `vless://UUID@HOST:PORT?encryption=none&flow=xtls-rprx-vision&security=reality&sni=SNI&fp=chrome&pbk=PUBLIC_KEY&sid=SHORT_ID&type=tcp#NAME`.

## Where the profile goes (host `everx`)

1. Save `gen-client.sh --profile` output as **`C:\Users\everx\dev\clash\vps-<dial ip>.yaml`**, e.g. `vps-68.164.34.142.yaml`. This is where the user keeps profiles, so tell them the path. Do not use the Desktop.
2. Validate: `& 'C:\Program Files\Clash Verge\verge-mihomo.exe' -t -d "$env:APPDATA\io.github.clash-verge-rev.clash-verge-rev" -f <file>`. Print only pass or fail ([remote-automation.md](remote-automation.md#powershell-secrets-leak-through-error-messages)).
3. Do not touch `dev\clash\vps.yaml` or `blocklist.yaml`. Never import, switch or edit the user's active Verge profile without explicit permission ([verge.md](verge.md#ask-first)).
4. Replacing an old profile on request: send the old file to the Recycle Bin with `[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile(path,'OnlyErrorDialogs','SendToRecycleBin')`, not `Remove-Item`. Files the user deleted themselves are in `C:\$Recycle.Bin\<SID>\$I*` (original path in UTF-16 from byte 28). Leave them there.
5. A "plain file only" request (the link, the snippet) still goes to `dev\clash\`, and creates or modifies no Verge profile.

Other points:

- Node names default to `VPS-<sni-label>-v4`, so nodes with the same SNI collide. For several nodes, install with `--name VPS-<tag>` (e.g. `VPS-US-142`).
- Merging into an existing profile (authorized): use `--proxies-only`, add the names to its own groups, and back up first. With a user-supplied full YAML, keep everything and only replace the node entries.
- Before saying a local profile is current, compare it with the server **by field hash**, never by printing values. Profiles for different hosts look alike (same SNI, flow and port 26417), so check `server` first. Seen 2026-11-10: `vps-68.164.13.128.yaml` was mistaken for the 68.164.34.142 profile.

## IPv6 on the client

Check for a global (`2xxx`/`3xxx`) address on the physical NIC. ULA and the TUN's synthetic range do not count:

```powershell
Get-NetIPAddress -AddressFamily IPv6 | Where-Object { $_.IPAddress -match '^[23]' -and $_.InterfaceAlias -notmatch 'Mihomo|Meta|Wintun' }
```

Without one, keep every IPv6 switch off: profile, `Merge.yaml`, and Verge's switch. Otherwise Happy Eyeballs stalls and fake-AAAA misses read as random hangs.
