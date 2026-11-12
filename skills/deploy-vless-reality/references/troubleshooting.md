# Troubleshooting rules

- A listening socket proves nothing; only a target-client request with the right exit IP does.
- A loopback pass exonerates the parameters, not the implementation. Target client fails but the Xray client works against the same relay → core/client interop: change the core version ([core-and-interop.md](core-and-interop.md)). Rotating keys cannot fix this.
- Every attempt logs `handshake did not complete successfully` → switch the Reality target and retest before touching keys or the path.
- Download fails on a fresh box → check `egress_stack`; IPv6-only cannot reach GitHub without DNS64 or an upload ([stacks.md](stacks.md#ipv6-only)).
- IPv6-only node works for some sites only → those sites are IPv4-only; needs permanent DNS64/NAT64.
- Externally reachable port but the service listens on another one → provider DNAT/forwarder. A failed connect from the VPS to its own public address:port confirms the mapping lives outside.
- On a TUN host, a ~1 ms connect, an `OPEN` on a port that must be closed, or a one-hop traceroute means the proxy answered. Retract conclusions drawn from it.
- `sysctl` writes on a container fail with `Read-only file system`; `test -w` lies as root. Read the mount flags and report the limitation instead of leaving a misleading `sysctl.conf`.
- `memory.events max` climbing on a small cgroup needs the Go guard; `oom_kill 0` does not mean no pressure. Installers increment `oom_kill` by themselves, so take the baseline first.
- An OpenRC pidfile under `supervise-daemon` names the supervisor, not Xray; find Xray by `/proc/<pid>/exe` ([service.md](service.md#which-pid-is-xray)).
- `crashed` with no process and no listener: keep logs, `run -test`, `zap`, `start`; prefer `supervise-daemon` to manual restarts.
- `Service '<x>' needs non existent service '<y>'` during `rc-service` on LXC/Podman Alpine (seen: `machine-id`/`watchdog` → `dev`, `networking` → `hostname`): harmless, the container lacks those boot services; ignore it.
- Health-check probes log `REALITY: processed invalid connection from 127.0.0.1 ... failed to read client hello`; expected.
- Many `TcpExtTCPSynRetrans` on the server: list `ss -tn state syn-sent`. On the reference host they were client devices retrying stale Google FCM addresses on port 5228 (`mtalk.google.com:5228` itself worked); noise, not a node fault.
- "Unstable" with a healthy server: measure the client uplink first (hotspot/cellular jitter, cross-border loss). A ~1 s outlier in TCP connect time is a SYN retransmit.
- Clash Verge "works sometimes" while the server is healthy: run `scripts/verge-check.ps1 -Watch 75` and read [verge.md](verge.md). Usual causes: IPv6 or fake AAAA on a v4-only setup, the sniffer off, the fake-ip pool flushed every 30 s (Verge service mode, not the proxy guard), an invalid `tun.stack`, or a dead loopback rule-provider. `fake DNS record … missing` means the fake-IP mapping was gone. Report effective values from `clash-verge.yaml`; profile edits need a regenerate or reload.
- Restarting the node that carries your session: run detached with verify-and-self-revert; treat a drop as unknown state.
- Before blaming the server for slow throughput, measure its own egress; a 70–100× gap points to the line. Egress ≈ end-to-end speed (seen 2026-11-09: ~0.6 MB/s both ways) means the provider caps the port; only the provider or a plan change helps.
- Leave no artifacts: relays, temp clients, temp SSH policy, helper files with secrets.
- PowerShell output shows a UUID/key inside `Cannot convert value "…"` or `Cannot bind parameter`: a helper name collided with a built-in alias (`H` = `Get-History`). Treat it as a leak and follow [remote-automation.md](remote-automation.md#powershell-secrets-leak-through-error-messages).

## Orphan or duplicate xray

Symptom: `verify-server.sh` reports `N xray processes running` or `... not supervise-daemon: orphan` / `not the unit's MainPID`; `rc-service xray status` shows `unsupervised`; `install.sh` stops with `orphan; recover first`. Cause seen on 2026-11-09: a respawn test killed the pidfile PID (the supervisor), the orphan kept `:443`, and `zap` + `start` then ran a second Xray beside it.

Recovery (one short disconnect):

```sh
rc-service xray stop; rc-service xray zap               # systemd: systemctl stop xray
for d in /proc/[0-9]*; do case "$(readlink $d/exe)" in /usr/local/bin/xray*) kill "${d#/proc/}" ;; esac; done
sleep 2; ss -tlnp | grep ':443 ' || echo port-free       # must be free before starting
rc-service xray start                                   # systemd: systemctl start xray
sh verify-server.sh                                     # exactly one xray, supervised
```

Hosts installed with the current `install.sh` do the kill in `start_pre`/`stop_post`, so `stop`/`zap`/`start` alone is enough.
