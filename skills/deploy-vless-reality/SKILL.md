---
name: deploy-vless-reality
description: Deploy, re-configure, upgrade, verify, diagnose or remove a single-user VLESS + XTLS Vision + Reality node on a newly bought VPS of any shape (IPv4-only, IPv6-only, dual-stack, NAT with provider port mapping, LXC/OpenVZ/Podman containers, systemd/OpenRC/no init, tiny cgroups), including stack detection, core/client interoperability, Reality target validation, Google egress eligibility, low-memory Xray operation, TUN-safe client verification, and Clash Verge Rev/mihomo profiles plus vless:// links.
---

# Deploy VLESS Reality

Deploy a minimally scoped VLESS + Vision + Reality service with the scripts in `scripts/`, and hand over client material only after a real request through the **target client** exits from the VPS on every stack you publish.

## Hard rules

- **Detect before planning.** Run `scripts/detect.sh` first; plan stacks, ports, service type and memory guard from its output, not from the provider's marketing.
- **Never guess a NAT mapping.** If `nat_v4`/`nat_v6` is `yes`, get the public port per family from the user/panel. Clients dial the public address and port; Xray listens on the internal port.
- **Dial address ≠ egress address is common on NAT VPS.** Clients dial the address the user gave (the one SSH works on); `egress_v4` from `detect.sh` can be another IP. Pass `--public-v4 <dial IP>` and expect the *egress* IP in exit-IP checks.
- **One IPv4 node by default.** No IPv6 node and no fallback group, even when the VPS has a public IPv6 (user rule, 2026-11-10). IPv6 only on explicit request: `install.sh --ipv6`, or `--public-v6 <addr>`. Exception: a box with no usable IPv4. Every published stack is verified separately ([stacks.md](references/stacks.md)).
- **Default Reality target is `www.amd.com`** (`serverNames: [www.amd.com]`, `dest: www.amd.com:443`). Check it from the VPS first; if it fails, report to the user instead of silently switching to another SNI.
- **Google gate before installing** when the node serves a Google-backed agent; a rejected egress IP means no deployment.
- **Pin the core for the client.** Default Xray 25.12.8 for Clash/mihomo; anything newer needs an end-to-end test with the target client first.
- **Validate the Reality target from the VPS** (TLS 1.3 + h2, per stack) and with a real handshake; reachable is not the same as usable.
- **No kernel tuning on unproven hosts.** Containers usually have a read-only `/proc/sys`; report the limitation instead of writing ineffective sysctl files.
- **Back up before every change; keep it re-runnable.** Use `install.sh` (idempotent, reuses credentials) and `uninstall.sh --rollback`. Never overwrite a running binary.
- **Secrets stay with the owner.** Client output contains UUID/keys in clear text for the owner's own config only; never write passwords, UUIDs, keys or shortIds to shared logs, reports or the skill folder.
- **Secret-handling scripts never print their inputs, not even in errors.** Use `Verb-Noun` helper names (PowerShell's `H` alias is `Get-History` and leaked keys through its errors), suppress exception details, dry-run on a dummy file first, and compare configs by field hash ([remote-automation.md](references/remote-automation.md#powershell-secrets-leak-through-error-messages)).
- **Hand over a complete profile from `gen-client.sh --profile`**, saved as `C:\Users\everx\dev\clash\vps-<ip>.yaml` (not the Desktop) and checked with `verge-mihomo -t`. It sets `ipv6: false` and `dns.ipv6: false`, turns the sniffer on, and uses the user's rule set (`GEOSITE cn` plus a single `GEOIP,CN,DIRECT,no-resolve`; add no more CN rules). It leaves out the keys Verge overrides. Never touch `vps.yaml`; old profiles go to the Recycle Bin ([client-profiles.md](references/client-profiles.md)).
- **Verge settings belong to the user.** Diagnose read-only (`scripts/verge-check.ps1`). Change `Merge.yaml`, `config.yaml`, `verge.yaml`, the active profile, or restart Verge only after the user agrees, with a backup and a rollback ([verge.md](references/verge.md)).
- **Stable means stable through TUN.** A TUN-bypassing test (`client-test.ps1`) is not enough. Add a TUN-path round of at least 65 s (`verge-check.ps1 -Watch 75`), because the fake-ip pool can be flushed every 30 s.

## Flow

1. **Access**: SSH host/port/user/auth from the user; establish a retryable channel ([remote-automation.md](references/remote-automation.md)).
2. **Detect**: `ssh … 'sh -s' < scripts/detect.sh` → stacks, NAT, init, container, arch, RAM, privilege, existing install ([detect.md](references/detect.md)).
3. **Decide per stack**: listen address, public ports, download route for IPv6-only, firewall ([stacks.md](references/stacks.md)).
4. **Gate**: Google eligibility if applicable ([google-gate.md](references/google-gate.md)); record `oom_kill` baseline on small cgroups.
5. **Pick target and core**: `scripts/check-dest.sh` on the VPS; core version from the interop table ([server-config.md](references/server-config.md), [core-and-interop.md](references/core-and-interop.md)).
6. **Install**: upload `scripts/`, run `install.sh --dry-run …`, then `install.sh …` (e.g. `--port 443 --public-port 26417 --sni www.amd.com`; `www.amd.com` is the default target). Service and health check per init system ([service.md](references/service.md)).
7. **Verify**: `verify-server.sh --loopback`, external TCP per public address, a target-client request per entry with exit-IP assertion (Windows: `scripts/client-test.ps1`), then a TUN-path round with `scripts/verge-check.ps1 -Watch 75`, then the Google gate through the node ([verify.md](references/verify.md)).
8. **Hand over**: run `gen-client.sh --profile`, save the result to `dev\clash\vps-<ip>.yaml`, run `-t`, and tell the user the path. Import or switch it in Verge only when they ask ([client-profiles.md](references/client-profiles.md)). For Verge problems, see [verge.md](references/verge.md).
9. **Later**: change, upgrade, rollback, uninstall via the same scripts ([lifecycle.md](references/lifecycle.md)); diagnose with [troubleshooting.md](references/troubleshooting.md).

## Files

| Path | Purpose |
|---|---|
| `scripts/detect.sh` | read-only detection, `key=value` output; safe on production nodes |
| `scripts/check-dest.sh` | read-only Reality target check (TLS 1.3 + h2) per stack |
| `scripts/install.sh` | idempotent install / re-configure / upgrade with backup, `--dry-run` |
| `scripts/verify-server.sh` | server-side checks (fails unless exactly one supervised xray), optional loopback request; prints no secrets |
| `scripts/gen-client.sh` | `--profile`: full Clash Verge Rev profile with the user defaults; also snippets and vless:// links (contains secrets) |
| `scripts/uninstall.sh` | `--list`, `--rollback <ts>`, uninstall, `--purge` |
| `scripts/client-test.ps1` | Windows/Verge-TUN host: temp mihomo bound to the current default-route NIC (auto-detected; do not assume `Wi-Fi`) → exit IP, delay, download, TCP/ICMP ping with closed-port control; no secrets printed |
| `scripts/verge-check.ps1` | read-only Verge check: config layers, ipv6/sniffer/tun.stack/rules/rule-providers, `-File` for a profile, `-Watch N` for the TUN path and fake-ip flushes; no secrets |
| `references/*.md` | details per topic, linked above |

All scripts are POSIX `sh` (busybox ash, dash, bash) and must be uploaded with LF line endings.
