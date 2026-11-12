#!/bin/sh
# Server-side verification. Read-only by default; never prints secrets.
# Usage: sh verify-server.sh [--loopback]
#   --loopback  also start a temporary xray client on 127.0.0.1 and fetch through the node
#               (needs the state file written by install.sh; the temp process is always killed)
# Fails unless exactly one xray process runs, it is the one the service manager supervises,
# and the service reports started/active (orphans and duplicates: references/troubleshooting.md).
LOOPBACK=0; [ "${1:-}" = "--loopback" ] && LOOPBACK=1   # read before any "set --" below
BIN=${XRAY_BIN:-/usr/local/bin/xray}; CFG=/usr/local/etc/xray/config.json; STATE=/usr/local/etc/xray/vless-reality.env
fail=0
ok() { printf 'OK   %s\n' "$*"; }
bad() { printf 'FAIL %s\n' "$*"; fail=1; }
info() { printf 'INFO %s\n' "$*"; }

PORT=""
# shellcheck disable=SC1090
[ -r "$STATE" ] && . "$STATE"
[ -n "$PORT" ] || PORT=$(sed -n 's/.*"port"[[:space:]]*:[[:space:]]*\([0-9]*\).*/\1/p' "$CFG" 2>/dev/null | head -n1)

[ -x "$BIN" ] && ok "binary $($BIN version | awk 'NR==1{print $2}')" || bad "no $BIN"
"$BIN" run -test -config "$CFG" >/dev/null 2>&1 && ok "config test" || bad "config test"

# Serving xray processes, found by /proc/<pid>/exe (works on BusyBox; pidof/pgrep -x can miss
# them, and the OpenRC pidfile names supervise-daemon, not xray).
xray_pids() {
  found=""
  for d in /proc/[0-9]*; do
    e=$(readlink "$d/exe" 2>/dev/null) || continue
    case "$e" in "$BIN"|"$BIN (deleted)") found="$found ${d#/proc/}" ;; esac
  done
  [ -n "$found" ] || found=$(pgrep -f "^$BIN run" 2>/dev/null | tr '\n' ' ')
  # shellcheck disable=SC2086
  echo $found
}
ppid_of() { awk '/^PPid:/{print $2}' "/proc/$1/status" 2>/dev/null; }
comm_of() { cat "/proc/$1/comm" 2>/dev/null; }

pids=$(xray_pids)
# shellcheck disable=SC2086
set -- $pids
pid=""
if [ $# -eq 1 ]; then
  pid=$1
  ok "xray running pid=$pid rss=$(awk '/VmRSS/{print $2" "$3}' /proc/"$pid"/status)"
  envs=$(tr '\0' '\n' </proc/"$pid"/environ 2>/dev/null | grep -E '^(GOGC|GOMEMLIMIT)=' | tr '\n' ' ')
  [ -n "$envs" ] && info "go guard in serving process: $envs"
elif [ $# -eq 0 ]; then
  bad "xray not running"
else
  bad "$# xray processes running (pids: $pids): orphan/duplicate, see troubleshooting.md#orphan-or-duplicate-xray"
fi

if command -v ss >/dev/null 2>&1; then l=$(ss -Htln "sport = :$PORT" 2>/dev/null)
else l=$(netstat -tln 2>/dev/null | grep -E "[:.]${PORT}[[:space:]]"); fi
[ -n "$l" ] && ok "listening on :$PORT ($(echo "$l" | awk '{print $4}' | tr '\n' ' '))" || bad "nothing listening on :$PORT"

for h in 127.0.0.1 ::1; do
  if command -v nc >/dev/null 2>&1; then nc -z -w 3 "$h" "$PORT" 2>/dev/null && ok "tcp connect $h:$PORT" || info "tcp connect $h:$PORT failed (fine if that family is disabled)"; fi
done

if [ -d /run/systemd/system ] && [ -f /etc/systemd/system/xray.service ]; then
  if systemctl is-active -q xray; then ok "systemd xray active"; else bad "systemd xray not active ($(systemctl is-active xray 2>&1))"; fi
  main=$(systemctl show -p MainPID --value xray 2>/dev/null)
  if [ -n "$pid" ]; then
    if [ "$main" = "$pid" ]; then ok "xray pid $pid is the unit's MainPID"; else bad "xray pid $pid is not the unit's MainPID ($main): orphan"; fi
  fi
  if systemctl is-active -q xray-health.timer; then info "health timer active"; else info "health timer inactive"; fi
elif command -v rc-service >/dev/null 2>&1 && [ -f /etc/init.d/xray ]; then
  st=$(rc-service xray status 2>&1)
  # exactly "started"; "unsupervised", "crashed", "stopped" all fail
  if echo "$st" | grep -q 'status: started$'; then ok "openrc: $st"; else bad "openrc: $st"; fi
  if [ -n "$pid" ]; then
    pp=$(ppid_of "$pid")
    # /proc/<pid>/comm is cut to 15 characters: "supervise-daemo"
    if case "$(comm_of "$pp")" in supervise-daem*) true ;; *) false ;; esac; then ok "xray pid $pid supervised by supervise-daemon pid $pp"
    else bad "xray pid $pid has parent $pp ($(comm_of "$pp")), not supervise-daemon: orphan"; fi
  fi
  hc=$(ps -o args 2>/dev/null | sed -n 's/.*supervise-daemon xray .*--healthcheck-timer \([0-9]*\).*/\1/p' | head -n1)
  info "supervise-daemon healthcheck interval: ${hc:-none}s"
elif [ -x /usr/local/bin/xray-supervise ]; then
  if [ -n "$pid" ] && ps -o pid,args 2>/dev/null | grep -q "^ *$(ppid_of "$pid") .*xray-supervise"; then ok "xray pid $pid supervised by xray-supervise"
  else bad "xray is not a child of xray-supervise"; fi
else
  bad "no xray service definition found (openrc/systemd/xray-supervise)"
fi

if [ -r /sys/fs/cgroup/memory.events ]; then
  info "cgroup memory.events: $(tr '\n' ' ' </sys/fs/cgroup/memory.events)"
fi

if [ "$LOOPBACK" = 1 ]; then
  [ -n "${UUID:-}" ] && [ -n "${PUBK:-}" ] || { bad "loopback needs $STATE"; exit 1; }
  T=$(mktemp -d /tmp/xray-lb.XXXXXX)
  lport=$(( 20000 + $(od -An -N2 -tu2 /dev/urandom | tr -d ' ') % 20000 ))
  cat > "$T/c.json" <<JSON
{"log":{"loglevel":"warning"},
 "inbounds":[{"listen":"127.0.0.1","port":$lport,"protocol":"socks","settings":{"udp":false}}],
 "outbounds":[{"protocol":"vless","settings":{"vnext":[{"address":"127.0.0.1","port":$PORT,"users":[{"id":"$UUID","flow":"xtls-rprx-vision","encryption":"none"}]}]},
  "streamSettings":{"network":"tcp","security":"reality","realitySettings":{"serverName":"$SNI","fingerprint":"chrome","publicKey":"$PUBK","shortId":"$SID"}}}]}
JSON
  "$BIN" run -c "$T/c.json" >"$T/c.log" 2>&1 &
  cpid=$!
  sleep 3
  code=$(curl -s -o /dev/null -m 15 -w '%{http_code}' -x "socks5h://127.0.0.1:$lport" https://www.gstatic.com/generate_204)
  [ "$code" = 204 ] && ok "loopback request through the node (204)" || bad "loopback request returned $code"
  kill "$cpid" 2>/dev/null; wait "$cpid" 2>/dev/null
  rm -rf "$T"
  info "loopback proves keys/SNI/schema for an Xray client only; still verify the target client (references/verify.md)"
fi
exit $fail
