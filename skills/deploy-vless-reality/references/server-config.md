# Server configuration

## What install.sh writes

- One VLESS inbound, `flow: xtls-rprx-vision`, `decryption: none`, Reality with one `serverNames` entry equal to the target, one random 8-byte `shortId`.
- `listen` is `::` when kernel IPv6 is enabled (serves both families), else `0.0.0.0`. **Caveat:** in Xray, `0.0.0.0` is still a dual-stack socket. For a true IPv4-only inbound, bind a specific IPv4 (on NAT: internal IP + `127.0.0.1`); `install.sh` does not do this yet. A provider IPv6 mapping can still forward into an IPv4 listener — turn it off in the panel. Details in [stacks.md](stacks.md#ipv4-only).
- `log.loglevel: warning`, `access: none` (debug emits high-volume Vision padding records; unsuitable for tiny cgroups).
- Outbounds: `freedom` with a stack-specific `domainStrategy` ([stacks.md](stacks.md)) and a `blackhole`; a routing rule blocks private/link-local/ULA destinations so the node cannot be used to reach the provider's internal network. No geo files are needed.
- Credentials live in `/usr/local/etc/xray/vless-reality.env` (mode 600) and are reused on every re-run unless `--rotate-keys`. The private key never leaves the server.

## Choosing and validating the Reality target

A reachable destination is not automatically a usable one. `www.microsoft.com` once answered `curl --tlsv1.3` with `200` in 26 ms, yet every client handshake failed with `REALITY: processed invalid connection ... handshake did not complete successfully`; `www.cloudflare.com`, `www.apple.com` or `www.bing.com` fixed it with no other change. On the reference host `www.microsoft.com` is also unreachable over IPv6.

Note on `www.amd.com` (Akamai): plain `curl` gets a perfect TLS 1.3 + h2 handshake and then `HTTP/2 stream 1 reset by server (INTERNAL_ERROR)`, `code=000` (bot filter on the curl UA). That is fine for Reality, which only borrows the handshake. `check-dest.sh` therefore sends a browser UA and judges on the handshake (`appconnect>0` + TLS1.3 + h2), not on the HTTP code; with a browser UA the site answers `301`. Measured 2026-11-10 from LA: ~19 ms handshake.

1. Run `scripts/check-dest.sh -4 -6 host1 host2 host3` on the VPS, passing only the families the box has. It requires **TLS 1.3 + ALPN h2** per family and prints handshake time.
2. Prefer a target that is also normal to reach from the client's country. Default `www.amd.com` (`serverNames: ["www.amd.com"]`, `dest: "www.amd.com:443"`). If it fails `check-dest.sh` or the loopback handshake, report it to the user and let them pick the replacement; do not switch silently.
3. Install with `--sni <host>`, then confirm a real handshake: `verify-server.sh --loopback`, then the target client.
4. If every attempt logs `handshake did not complete successfully`, switch the target and retest before touching keys or the network path.

## Low-memory operation

Use for budgets ≤ 256–512 MiB, or when Xray disappears under load, SSH resets, or clients see `EOF`/timeouts after a healthy period. The cgroup limit, not `free`, is the budget:

```sh
cat /sys/fs/cgroup/memory.max /sys/fs/cgroup/memory.current
grep -E '^(anon|file|slab|sock) ' /sys/fs/cgroup/memory.stat
cat /sys/fs/cgroup/memory.events      # "max" = ceiling hits; oom_kill 0 does NOT mean no pressure
```

- `memory.current` includes reclaimable page cache: `anon` in the low tens of MB with `file` in the tens of MB is normal.
- **Go runtime guard**: Go sizes GC against host memory, not the cgroup. `install.sh` sets `GOGC=50` and `GOMEMLIMIT` = 75% of the budget when it is ≤ 512 MiB (128 MiB → 96 MiB) in the service definition. Too low a limit causes continuous GC, which on 1 vCPU looks exactly like network stutter.
- Verify the guard reached the **serving** process: `verify-server.sh` prints `GOGC/GOMEMLIMIT` from `/proc/<xray pid>/environ`. Under `supervise-daemon` the pidfile names the supervisor (a few hundred KB, 1 thread), not Xray.
- Then sample `memory.events` over ~30 s of real traffic; `max` should stop climbing.
- Record `oom_kill` **before** installing; installs alone can increment it. Install packages in small steps.

### Logs on a tiny box

If you enable file logs for diagnosis, bound them with logrotate and remove them afterwards:

```conf
/var/log/xray/*.log {
    size 5M
    rotate 3
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
    create 0600 root root
}
```

On Alpine run it from `/etc/periodic/15min/xray-logrotate` and make sure a cron daemon actually runs (`apk add dcron; rc-update add dcron default; rc-service dcron start`). The periodic script can also reclaim file cache under pressure:

```sh
#!/bin/sh
/usr/sbin/logrotate -s /var/lib/logrotate/xray.status /etc/logrotate.d/xray
limit=$(cat /sys/fs/cgroup/memory.max); current=$(cat /sys/fs/cgroup/memory.current)
if [ "$limit" != max ] && [ "$current" -ge $((limit * 75 / 100)) ] && [ -w /sys/fs/cgroup/memory.reclaim ]; then
    echo '64M swappiness=0' > /sys/fs/cgroup/memory.reclaim 2>/dev/null || true
fi
```

`copytruncate` needs free disk for a full copy of each active log; check `du`/`df` before forcing a rotation. Deleting or truncating diagnostic logs needs the user's authorization.

## Kernel tuning (bbr and friends)

Only on hosts proven writable ([detect.md](detect.md#privilege-level-before-any-kernel-tuning)). `install.sh --bbr` writes `/etc/sysctl.d/99-vless-reality-bbr.conf` (`fq` + `bbr`) only when `sysctl_writable` is not `no`, bbr is available and not already active, and reverts the file if `sysctl -p` fails. In containers bbr is often already set host-side; report it instead of changing anything.
