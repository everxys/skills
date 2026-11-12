# Stack-specific behaviour

`install.sh` derives the plan from `detect.sh`; this page explains the rules so you can override them (`--public-v4`, `--public-v6`, `--public-port`, `--public-port-v6`; disable a family with `--public-v4 none` or `--public-v6 none`).

> **Default is IPv4 only.** Even on a dual-stack VPS, `install.sh` publishes no IPv6 entry and the profile has no `fallback` group unless the user explicitly asked for IPv6 (`--ipv6` or `--public-v6 <addr>`). The dual-stack rows below apply only then. A box with no usable IPv4 still falls back to its IPv6.

| Stack | Listen | Client entries | Freedom `domainStrategy` |
|---|---|---|---|
| IPv4-only | `::` if kernel IPv6 is on, else `0.0.0.0` | v4 only; never emit an IPv6 entry | `UseIPv4` (no AAAA attempts) |
| IPv6-only | `::` | v6 only | `UseIPv6`; IPv4-only websites need NAT64 (below) |
| Dual-stack | `::` (dual-stack socket, `bindv6only=0`) | **v4 only by default**; v6 + v4 + `fallback` group only with `--ipv6`/`--public-v6` | `AsIs` |
| NAT (either family) | internal port (often 443) | **public** address + **mapped** port per family | as above |

## IPv4-only

- Also applies when the only IPv6 is NATed (egress v6 not on any interface, ULA `fd..` inside) and the user gave no v6 mapping: `install.sh` then sets `PUB6=none` itself. The handover is a **single** v4 node.
- Do not bind or publish an IPv6 entry, and on the client keep IPv6 off unless the client network has a global IPv6 (see [client-profiles.md](client-profiles.md#ipv6-on-the-client)).
- `UseIPv4` avoids the Happy-Eyeballs SYN timeouts to AAAA destinations that otherwise show up as `TcpExtTCPSynRetrans`.
- **Xray `listen: "0.0.0.0"` is still a dual-stack socket.** It is not IPv4-only: Xray (Go) still accepts IPv6 on that listener. `listen: "::"` with `bindv6only=0` is explicitly dual-stack as well. `install.sh` still uses `::` when the kernel has IPv6, else `0.0.0.0`. When the goal is an IPv4-only inbound, bind a **specific IPv4 address**. On a NAT box bind the internal IPv4 and `127.0.0.1` (so `verify-server.sh --loopback` still works). Do not use `0.0.0.0` for this.
- **A provider IPv6 port mapping can still reach an IPv4-only listener.** The edge may accept IPv6 on the mapped public port and forward it as internal IPv4 into the container. Deleting the v6 client entry, and even rebinding the inbound to a specific IPv4, does not stop that path. Turn the IPv6 mapping off in the provider panel to fully kill the old IPv6 entry. Seen 2026-11-11 on `23.95.35.74`: after the inbound was bound to the host IPv4 + `127.0.0.1` and the v6 client entry was removed, the provider's IPv6 mapping still forwarded.

## IPv6-only

The common failure is the **download**: `github.com` and its release CDN have no AAAA records, so `curl` fails before anything is installed. Options, most robust first:

1. **Upload from the client**: download `Xray-linux-<arch>.zip` (+ `.dgst`) on the operator machine, check the SHA2-256, `scp` it over, then `install.sh --binary /tmp/Xray-linux-64.zip`.
2. **NAT64/DNS64**: `install.sh --dns64` swaps `/etc/resolv.conf` to public DNS64 resolvers (nat64.net) **only for the download** and restores it. Verify the current resolver list at https://nat64.net first; these services change. `github_has_aaaa=yes` in `detect.sh` means DNS64 is already active.
3. **A mirror you trust**: `--mirror https://<prefix>`. The `.dgst` comes through the same mirror, so this protects only against corruption, not a malicious mirror.

Package managers are usually fine over IPv6: `dl-cdn.alpinelinux.org` and `deb.debian.org` both serve AAAA.

After install, IPv4-only destinations (some sites, some APIs) are unreachable from an IPv6-only node unless DNS64/NAT64 stays configured permanently. Tell the user; if they need full reach, make the DNS64 resolvers permanent (or use the provider's NAT64) and re-test.

Use `api64.ipify.org` (not `api.ipify.org`) for exit-IP assertions on this stack.

## Dual-stack

- One `listen: "::"` socket accepts both families when `bindv6only=0` (connections show as `[::ffff:a.b.c.d]`). If the kernel has `bindv6only=1`, add a second inbound on `0.0.0.0` with the same settings.
- Only when the user asked for IPv6 (`--ipv6`): emit both client entries and a `fallback` group (v6 first when it measured lower latency; reorder otherwise). Measured on the reference host from a China mobile hotspot: v6 208 ms avg vs v4 232 ms avg, both ~2% loss.

## NAT VPS and port mapping

- The service listens on the internal port; clients always dial the **public** port. Get the mapping from the provider panel or the user; `detect.sh` cannot see it. IPv6 may be NATed too (ULA `fd..` on the interface).
- Confirm the mapping is **TCP**. Ask separately for UDP if you ever plan a UDP protocol.
- Mixed NAT is common: IPv4 NATed (`nat_v4=yes`) but a global IPv6 on the interface (`nat_v6=no`). Then v6 clients dial the internal port directly: `--public-port 26417 --public-port-v6 443`, and verify v6 separately ([verify.md](verify.md#external-reachability)).
- **Probe the mapping before installing** (seconds, nothing installed): on the VPS run `timeout 20 nc -l -p <internal-port>` (or note an existing listener), then from outside connect to `<public-ip>:<public-port>` (box, check-host.net, or the user's PC bound to its physical NIC). `Connection refused` while the container's `TcpPassiveOpens`/`TcpOutRsts` (`nstat -az`) stay flat means the provider edge has no such mapping: stop and ask the user to fix it in the panel. Seen on 2026-11-09: SSH's mapped port worked, `26417` was refused from 4 countries and from the client.
- A successful connect is **not** proof: terminating forwarders accept TCP on a mapped port even with no backend listener. Prove the target with a marker: `timeout 30 nc -l -p <internal-port> > /tmp/probe` on the VPS, send `printf MARK<port>` to `<public-ip>:<public-port>` from outside, then read `/tmp/probe`. Also try a near-miss/transposed port (user wrote `26471`; `26417` was the real mapping on 2026-11-09). If the user's port is refused but another port delivers the marker, stop and ask; do not pick one yourself.
- Client entry family is not egress family: with `AsIs` on a dual-stack egress, a client on the v4 entry still leaves over v6 for AAAA destinations (seen 2026-11-09: `api64.ipify.org`/Cloudflare trace showed the v6 address via the v4 entry). If the v6 egress geolocates badly (iplocate put one in Poland while Cloudflare said JP), tell the user; preferring v4 in the profile does not fix it, only freedom `domainStrategy: UseIPv4v6` (v4 first) on the server does.
- **Ingress and egress can be different IPs.** Seen 2026-11-10 (AS402898, LA, Alpine LXC): SSH and the 26417 mapping on `68.164.34.142`, while `detect.sh` reported `egress_v4=140.235.229.19`. Install with `--public-v4 <the address the user gave>` (otherwise the client entry dials the egress IP, which has no mapping) and expect the egress IP from `api.ipify.org` through the node.
- **Dial IP can also equal egress IP on the same NAT pattern.** Seen 2026-11-11 (AS209604, Bursa, Alpine 3.24 LXC, same private `10.91.0.0/20` + mapped 26417): `nat_v4=yes` and `egress_v4` was exactly the address the user SSHed to. Still pass `--public-v4 <dial IP>` and still probe the mapping with a marker; equality is not a reason to skip NAT handling. Public `:443` may accept TCP at the provider edge even then; only the marker decides.
- Marker probe without `nc` on the operator box: `timeout 8 bash -c "exec 3<>/dev/tcp/IP/PORT; printf MARK >&3; sleep 2"`. On the VPS, BusyBox `nc -l -p 443` works; to stop it use `kill` by PID, not `pkill -f "nc -l"` inside the same `ssh '…'` string (it matches the remote shell's own command line and kills the session, exit 255).
- An open port is not your mapping: on the 2026-11-10 host the dial IP answered on `:443` with nothing listening inside (provider edge), while `26417` was refused until the marker listener ran, i.e. that forwarder does **not** terminate TCP. Only the marker decides.
- From inside the box, connecting to `<public-ip>:<public-port>` usually fails (no hairpin); that confirms the mapping lives outside, it is not an error. Verify externally ([verify.md](verify.md#external-reachability)).
- A provider forwarder that terminates TCP (peer = gateway, sub-ms RTT) hides client IPs and adds a hop; expect `TcpEstabResets` you cannot fix from inside.
- `$SSH_CLIENT` shows the gateway, not the operator's address.

## Firewall

- Open the **internal** listen port for both families only if a host firewall is active: `install.sh --open-firewall` handles ufw (covers v4+v6 when `IPV6=yes`), firewalld, and iptables+ip6tables (not persistent; tell the user). nftables with a drop policy is left to a manual rule.
- Cloud security groups and provider panels are outside the box: name them to the user.
- `uninstall.sh` removes only the rule `install.sh` added (recorded as `FWOPEN` in the state file).
