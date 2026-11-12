# Verification

A node counts as working only after a real request through the **target client** exits from the VPS. Verify per stack: a dual-stack node needs the v4 and the v6 entry checked separately.

## Server side

`scripts/verify-server.sh` (read-only; never prints secrets): binary version, `run -test`, serving process + RSS + Go guard env, listener on the port, local TCP connect on `127.0.0.1` and `::1`, service state (systemd/OpenRC) and the active health-check interval, cgroup `memory.events`.

`verify-server.sh --loopback` additionally starts a temporary Xray client on `127.0.0.1` and fetches `generate_204` through the node, then kills it. A pass proves keys, SNI, target and schema agree **for an Xray client**. It does not clear the core version for another client ([core-and-interop.md](core-and-interop.md)).

## External reachability

The mapping can differ from what the VPS sees, and a local TUN on the operator machine can fake connects, so check from outside, per family and per public port:

```sh
curl -s -H 'Accept: application/json' 'https://check-host.net/check-tcp?host=IP:PUBLIC_PORT&max_nodes=3'
curl -s -H 'Accept: application/json' 'https://check-host.net/check-result/<request_id>'
```

check-host.net rejects IPv6 targets (`invalid_url`). For IPv6 use Globalping's TCP ping (no account; do not pass `ipVersion` for an IP target), plus a closed port as control:

```sh
curl -s -X POST https://api.globalping.io/v1/measurements -H 'Content-Type: application/json' \
  -d '{"type":"ping","target":"2001:db8::1","measurementOptions":{"protocol":"TCP","port":443,"packets":3},"limit":4}'
curl -s https://api.globalping.io/v1/measurements/<id>    # stats.loss 0 = reachable; a probe without IPv6 shows 100%
``` A plain TCP connect from any non-proxied machine you control is also fine. On the reference host: box → `23.95.35.74:26417` 66–68 ms, 0 loss; `:443` closed externally (only the mapped port exists).

## Client side (target client)

- In a temporary mihomo config use `mode: rule` with `MATCH,<node>`; `mode: global` selects `DIRECT` and gives false passes.
- Assert the exit address: `curl -x http://127.0.0.1:<effective-port> https://api.ipify.org` (v4) / `https://api64.ipify.org` (v6) must print the VPS address of that entry.
- Prove the traffic traversed the node: compare mihomo `/connections` totals before/after, or the server access log during a diagnosis window.

### Hosts with Clash/Verge TUN enabled

- TUN fabricates TCP handshakes. A `connect()` in ~1 ms, an `OPEN` followed by a TLS failure, or a `tracert` that shows a single hop at full RTT means the proxy answered, not the network. On the reference client, `tracert` to the VPS showed exactly one hop.
- Before trusting any probe, connect to a port that must be closed (`:9999`, `:12345`). If it reports `OPEN`, discard every reachability result from that host, including earlier conclusions.
- Measure the real path by binding the socket to the **currently UP physical NIC** that owns the default IPv4 route (PowerShell: `Socket.Bind(<that NIC's IPv4>)`, then `BeginConnect`). Do not assume the alias is `Wi-Fi`. A genuine connect to a US VPS costs about one RTT; ~1.2 s outliers are a SYN retransmit, i.e. loss.
- Route under TUN: `tracert` cannot pick an IPv4 source, so it shows the TUN. Walk TTLs with ping bound to the NIC instead: `for ($t=1;$t -le 30;$t++){ ping -n 1 -w 1500 -i $t -S <Wi-Fi IP> <vps> }` and look up each `TTL expired` address (e.g. `iplocate.io/api/lookup/<ip>`). Chinese backbones often hide every hop; CN2 shows `59.43.*`, CMI `223.120.*`.
- `Find-NetRoute -RemoteIPAddress <ip>` shows whether a destination goes to `Mihomo` or the physical NIC.
- `interface-name` in a mihomo proxy entry is unreliable on Windows; adding host routes needs elevation.
- ICMP and DF-bit MTU probes over TUN prove nothing.

### Scripted test (Windows + Verge TUN)

**Pick the NIC first. Do not assume it is called `Wi-Fi`.** Take the adapter that owns the default IPv4 route and is Up, excluding TUN (`Mihomo` / Meta / Wintun):

```powershell
Get-NetAdapter | Where-Object Status -eq 'Up'
Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' |
  Select-Object InterfaceAlias, NextHop, RouteMetric, InterfaceMetric
```

Pass that `InterfaceAlias` as `-Iface`. The alias changes with the access network: the reference laptop's home Wi-Fi is `Wi-Fi` (SSID `everxys-wifi`, profile `everxys-wifi 2`), but USB tethering shows up as `Ethernet N`. Binding `Wi-Fi` while the default route is on another NIC (or while Wi-Fi is down) tests the wrong path or fails. Always report which NIC was used with the results. `client-test.ps1` auto-detects this when `-Iface` is omitted; an explicit `-Iface` still wins.

`scripts/client-test.ps1 -Profile C:\Users\everx\dev\clash\vps-<ip>.yaml -Node <name> -Server <dial ip> -Port <public port>` copies only that node into a temporary mihomo (Verge's `verge-mihomo.exe`, ports 17897/19097) with `interface-name` on that NIC, runs exit-IP, delay, 20× `generate_204`, two downloads, TCP ping bound to the NIC (+ `:9999` control) and ICMP, then kills mihomo and deletes the temp dir. `interface-name` worked on Windows here: exit IP correct, `:9999` refused, `/connections` delta matched the bytes downloaded.

**Bypassing TUN is not enough.** `client-test.ps1` avoids Verge's TUN, so it proves the node and the line, not the user's real path. Seen 2026-11-10: 600/600 clean bypassing TUN, while Google through TUN failed intermittently because of fake-ip flushes. Always add a TUN-path round of at least 65 s, crossing two 30 s ticks: `scripts/verge-check.ps1 -Watch 75` (marker domain + `generate_204`, read-only, no secrets). Details in [verge.md](verge.md).

Reference 2026-11-10, home Wi-Fi (Shanghai) → `68.164.34.142:26417` (LA, AS402898, Xray 25.12.8, SNI www.amd.com): TCP connect 137/145/157 ms min/avg/max, 0/30 lost; ICMP 150/151/154 ms, 0/20 lost; mihomo delay ~597–673 ms; `generate_204` 20/20, median 0.63 s; download 81.5 Mbps (Cloudflare 50 MB) and 93.6 Mbps (CacheFly 100 MiB); server egress ~27 MB/s; domestic uplink 6 ms. 128 MiB cgroup: `oom_kill 0`, `max 0`, RSS ~33 MB after the test.

Reference 2026-11-11, same home Wi-Fi (Shanghai) → `93.114.183.172:26417` (Bursa, TR, AS209604, Alpine 3.24 LXC, 128 MiB, Xray 25.12.8, SNI www.amd.com): NAT v4 (internal `10.91.0.6`, mapping 443→26417) with dial IP equal to egress IP. TCP connect 203.5/388.5/2231.8 ms min/avg/max, 0/30 lost, 4/30 over 1 s; ICMP 233/234/235 ms, 4/20 lost (20% — ICMP loss here did not show up on TCP, so do not treat ICMP loss as a failed node); mihomo delay ~1.1–2.3 s; `generate_204` 20/20, median 1.89 s, max 7.05 s; download 4.1 Mbps (Cloudflare 50 MB, hit the 40 s cap at 20.3/50 MB) and 9.2 Mbps (CacheFly 50 MB, 40 s cap, 45.9/50 MB). Domestic uplink 5 ms, 0 loss. `oom_kill` 0, RSS ~37 MB after the test. The CN→TR path is much slower and jerkier than the LA reference; that is the line, not the install.

Reference 2026-11-11 evening (Asia/Shanghai), same home Wi-Fi (MediaTek MT7922, default route on `Wi-Fi`, not USB tethering) → `23.95.35.74:26417` (US, node VPS-US-74-v4, SNI www.apple.com): TCP connect 162.2/240/1175.7 ms min/avg/max, 0/30 lost, 2/30 over 1 s; ICMP 172/173/174 ms, 3/20 lost (15% — ICMP loss here did not show up on TCP, so do not treat ICMP loss as a failed node); mihomo delay ~0.9-4.2 s; `generate_204` 20/20, median 1.36 s, max 9.51 s; download 2.9 Mbps (Cloudflare 50 MB, hit the 40 s cap at 14.3/50 MB) and 1.1 Mbps (CacheFly, 40 s cap, 5.7 MB). Exit IP 23.95.35.74 on both api.ipify.org and api64.ipify.org. Closed-port control `:9999` refused. Domestic uplink 5 ms, 0 loss. An earlier pass on USB tethering was also poor; this Wi-Fi retest shows the low throughput and jitter are the CN→this-VPS path, not the tether.

### Local L4 relay

Put a byte-transparent relay in front of the VPS, bind its outbound socket to the physical interface, and point the test client at loopback. The Reality handshake stays end-to-end, and swapping only the client (`xray` vs target client) separates server problems from client-implementation problems.

```python
import socket, struct, selectors, threading
LISTEN, TARGET, IFINDEX = ("127.0.0.1", 26418), ("VPS_IP", PUBLIC_PORT), 12   # ifIndex of Wi-Fi/Ethernet
def handle(c):
    up = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    up.setsockopt(0, 31, struct.pack("!I", IFINDEX))   # IP_UNICAST_IF: network byte order
    # IPv6 target: AF_INET6 socket and up.setsockopt(41, 31, struct.pack("I", IFINDEX))  (IPV6_UNICAST_IF: host order)
    up.connect(TARGET)
    sel = selectors.DefaultSelector()
    sel.register(c, selectors.EVENT_READ, up); sel.register(up, selectors.EVENT_READ, c)
    while True:
        for k, _ in sel.select(timeout=300):
            data = k.fileobj.recv(65536)
            if not data: return
            k.data.sendall(data)
srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(LISTEN); srv.listen(32)
while True:
    c, _ = srv.accept(); threading.Thread(target=handle, args=(c,), daemon=True).start()
```

Stop the relay and free the port afterwards.

## Throughput and stability attribution

Measure both ends before tuning anything:

- **Server egress**: `curl -w '%{speed_download}'` from the VPS to a fast target (reference: 73 MB/s).
- **End-to-end**: the same download through the client proxy port (reference: 0.8–1.1 MB/s). A 70–100× gap localises the fault to the client↔VPS path, where only line selection (CN2 GIA / 9929 / CMIN2, closer region) or a different access network helps.
- **Jitter**: ~20 small requests through the proxy, report min/avg/max of total time. Reference: generate_204 median ~0.9 s on new connections, 3/25 at 2–2.8 s (= loss).
- **Access network**: check the client's own uplink first (`ping` a domestic resolver). A phone hotspot on cellular (18–66 ms to 223.5.5.5, ~2% loss across the border) explained the reference host's "unstable" reports, not the server.
- Server CPU: idle% and steal from `/proc/stat` or `top`; server TCP: `nstat` deltas of `TcpExtTCPSynRetrans`, `TcpEstabResets` over 30 s, and `ss -tn state syn-sent` to see which destinations time out.

## Required checklist

1. `run -test` passes with the binary that serves.
2. Service active, survives one health-check interval, owns the socket; interval visible in `ps`/timer.
3. External TCP to each public address:port succeeds (both families on dual-stack).
4. `verify-server.sh --loopback` returns 204.
5. The target client completes a request per entry, exit IP = that entry's VPS address, traffic proven through the node.
6. `oom_kill` unchanged during that request; `memory.events max` stops climbing with the Go guard set.
7. Google gate passed before install and through the node when the node serves a Google-backed agent ([google-gate.md](google-gate.md)).
8. Client effective config read back (port, `ipv6`, DNS) and the profile actually re-selected ([client-profiles.md](client-profiles.md)).
9. Kernel tuning only if the host was proven writable; otherwise the limitation is reported.
10. No artifacts left: relays and test clients stopped, temporary SSH policy restored, test ports free, temporary files with secrets deleted.
