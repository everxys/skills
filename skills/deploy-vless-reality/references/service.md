# Service supervision and health checks

`install.sh` picks the template from `detect.sh`'s `init` field. Default health-check interval is **60 s** (`--health-interval`); 30 s gave no benefit on the reference host and doubles the `REALITY: processed invalid connection from 127.0.0.1 ... failed to read client hello` lines each probe produces (expected, not a client failure).

## OpenRC (Alpine)

Use `supervise-daemon`, not `command_background=yes` alone: after an exit OpenRC can keep a `crashed` state and refuse `rc-service xray start`.

```sh
#!/sbin/openrc-run
name="xray"
supervisor=supervise-daemon
command="/usr/local/bin/xray"
command_args="run -c /usr/local/etc/xray/config.json"
pidfile="/run/xray.pid"
retry="TERM/10/KILL/5"
export GOGC=50              # only on small budgets
export GOMEMLIMIT=96MiB     # 75% of the cgroup limit
respawn_delay=5
respawn_max=3
respawn_period=60
healthcheck_timer=60
kill_strays() { # any xray outside the supervisor is an orphan; match by /proc/<pid>/exe
    for d in /proc/[0-9]*; do
        case "$(readlink "$d/exe" 2>/dev/null)" in /usr/local/bin/xray|"/usr/local/bin/xray (deleted)") kill "${d#/proc/}" ;; esac
    done; return 0
}
start_pre() { "${command}" run -test -config /usr/local/etc/xray/config.json >/dev/null || return 1; kill_strays; sleep 1; }
stop_post() { kill_strays; }
healthcheck() { nc -z -w 3 127.0.0.1 443; }
depend() { need net; after firewall; }
```

- The health check needs an `nc` with `-z`; `install.sh` installs `netcat-openbsd` when missing, otherwise the supervisor flaps.
- `healthcheck_timer` is passed to `supervise-daemon` at start (`--healthcheck-timer N` in `ps`). Changing it requires `rc-service xray restart`, i.e. one short disconnect (~3 s on the reference host). There is no separate loop to restart.
- `start_pre`/`stop_post` kill every `/usr/local/bin/xray` process, so `zap` + `start` heals an orphan. Side effect: they also end a running `verify-server.sh --loopback` client. Hosts installed before 2026-11-09 lack these hooks until `install.sh` is re-run.
- `crashed` with no process and no listener: preserve logs, check `run -test`, then `rc-service xray zap && rc-service xray start`. Do not loop restarts; fix the logged error.

## Which PID is Xray

Under `supervise-daemon`, `/run/xray.pid` holds the **supervisor's** PID. `kill $(cat /run/xray.pid)` kills the supervisor and leaves Xray running unsupervised (status `unsupervised`, no respawn, no health check). BusyBox `pidof`/`pgrep -x xray` can also miss Xray. Find it by executable:

```sh
for d in /proc/[0-9]*; do [ "$(readlink $d/exe)" = /usr/local/bin/xray ] && echo "${d#/proc/} parent=$(awk '/^PPid/{print $2}' $d/status)"; done
cat /proc/<parent>/comm        # "supervise-daemo" (comm is cut to 15 chars) = supervised; anything else = orphan
```

On systemd compare with `systemctl show -p MainPID --value xray`. `verify-server.sh` fails unless exactly one Xray runs and it is the supervised one; `install.sh` refuses to start in that state. Recovery: [troubleshooting.md](troubleshooting.md#orphan-or-duplicate-xray).

To test respawn, kill the **Xray** PID found above, never the pidfile PID.

## systemd

`xray.service` with `ExecStartPre=xray run -test`, `Restart=on-failure`, `RestartSec=5`, `StartLimitBurst=3` per 60 s, `LimitNOFILE=1048576`, and `Environment=GOGC/GOMEMLIMIT` on small budgets. systemd has no TCP health check, so `xray-health.timer` (every `--health-interval` seconds) runs a oneshot that restarts `xray` after three failed `nc -z` probes. Without `nc` the probe fails, so install it (`netcat-openbsd`) or drop the timer.

## No init system

Some containers run without an init. `install.sh` installs `/usr/local/bin/xray-supervise` (a loop that tests the config, runs Xray, probes the port every interval, and restarts on exit or failed probe), starts it with `setsid nohup`, and adds an `@reboot` crontab entry. That entry only works if a cron daemon runs; otherwise tell the user the node will not survive a container restart and ask how the provider starts processes.

## Restarting the node that carries your own session

When your SSH or agent traffic routes through the node you are restarting, assume the session dies mid-command:

- Run the change detached: `setsid nohup sh /root/step.sh </dev/null >/root/step.log 2>&1 &`.
- Make the script verify and self-revert: back up, `run -test`, restart, poll the listener for a bounded window, restore the backup and restart again if it never comes back. `install.sh` + `uninstall.sh --rollback <ts>` give you both halves.
- Reconnect and read the log; a dropped connection is "unknown state", not failure.
