# Detection: read the box before planning anything

Run `scripts/detect.sh` (read-only, POSIX sh, no installs) and plan from its output. Pipe it over SSH without uploading: `ssh -p PORT root@HOST 'sh -s' < scripts/detect.sh`.

## Fields and the decision each one drives

| Field | Meaning | Decision |
|---|---|---|
| `egress_v4` / `egress_v6` / `egress_stack` | public address seen by api.ipify.org / api64.ipify.org per family | which client entries exist; `dual` → two entries + fallback group |
| `if_v4_public`, `if_v4_private`, `if_v6_global`, `if_v6_ula` | addresses on interfaces | private/ULA only → the box is behind NAT |
| `nat_v4` / `nat_v6` | egress address not on any interface | yes → **ask the user for the provider's port mapping**; never guess it |
| `init` | `systemd` / `openrc` / `none` | which service template `install.sh` writes |
| `virt`, `is_container` | podman / lxc / openvz / docker / vm | containers: no kernel tuning, cgroup is the memory budget |
| `mem_limit_bytes`, `cg_mem_events_max`, `cg_oom_kill` | cgroup budget and ceiling hits | ≤ 512 MiB → Go guard; record `oom_kill` as the baseline **before** installing |
| `sysctl_writable` | `no` if `/proc/sys` is mounted `ro` or not root; `maybe` otherwise | `no` → do not promise bbr/sysctl; `maybe` → only an actual write proves it |
| `tcp_cc`, `bbr_available` | current congestion control | already `bbr` (often host-set in containers) → nothing to do |
| `ipv6_disabled`, `bindv6only` | kernel IPv6 state | `0`/`0` → listen on `::` serves both families |
| `github_reachable`, `github_has_aaaa` | can the box download releases | IPv6-only without DNS64 → see [stacks.md](stacks.md#ipv6-only) |
| `tcp_listening` | ports in use | the listen port must be free or already owned by xray |
| `xray_installed`, `skill_state`, `xray_env`, `healthcheck_timer` | existing install | re-run/upgrade path instead of a fresh install |
| `firewall` | active ufw / firewalld / nftables / iptables | `install.sh --open-firewall` or manual rule; cloud security groups are outside the box |

`detect.sh` cannot see **inbound** reachability or the provider's mapping. Those come from the user (panel) and from an external check (see [verify.md](verify.md#external-reachability)).

On Alpine OpenRC LXC, `cat /sys/fs/cgroup/memory.max` from an SSH session can read `max` because that process is in `/openrc.sshd`. `detect.sh` already falls back to `MemTotal` when the cgroup limit is `max` or larger than RAM (seen 2026-11-11: 128 MiB `MemTotal`, `memory.max=max`, `mem_limit_bytes=134217728`). Trust `detect.sh`, not a raw `memory.max` from the SSH cgroup.

## Privilege level before any kernel tuning

A provider "VPS" is often an unprivileged LXC/Podman container. Kernel tuning is impossible there and fails silently until you try.

```sh
grep -E ' /proc(/sys)? ' /proc/mounts     # "ro" on /proc/sys => cannot write
grep -E 'CapEff' /proc/1/status           # 0x800405fb lacks CAP_SYS_ADMIN (bit 21)
```

`test -w /proc/sys/...` is **not** a valid probe: root passes it even on a read-only mount. Observed on the real host: `/proc/sys` mounted `ro`, `CapEff=00000000800405fb`, every write returns `Read-only file system`, while `tcp_congestion_control` already reads `bbr` (set host-side).

Do not write `/etc/sysctl.conf` and assume it applies. `sysctl -p` fails with `Read-only file system` while the file looks updated. If a write fails, revert the file and report the limitation. On such a host `tcp_slow_start_after_idle`, `tcp_mtu_probing`, `rmem_max`/`wmem_max` and `tcp_congestion_control` are all out of reach; the only routes are asking the provider or moving to KVM.

## Real-world reference case (2026-11)

| Item | Value |
|---|---|
| Platform | Alpine 3.24 in a Podman container, 1 vCPU, cgroup `memory.max` 128 MiB, `/proc/sys` ro |
| Addresses | `10.91.0.25/20` + ULA `fd91:cafe:cafe:10::19/64`; egress v4 and v6 are both public but on no interface → NAT on both families |
| Mapping | external `26417/tcp` (v4 and v6) → internal `443`; every inbound connection appears from `10.91.0.1` with ~0.02 ms RTT, i.e. the provider's forwarder terminates TCP |
| Core | Xray 25.12.8, VLESS + Vision + Reality, target `www.apple.com:443` |
| Service | OpenRC `supervise-daemon`, `healthcheck_timer=60`, `GOGC=50`, `GOMEMLIMIT=96MiB` |
| Kernel | `bbr` already active host-side; not changeable from inside |
