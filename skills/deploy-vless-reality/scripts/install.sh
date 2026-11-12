#!/bin/sh
# Idempotent install / re-configure / upgrade of a single-user VLESS + Vision + Reality node.
# POSIX sh (works on Alpine busybox ash, Debian dash, bash). Run as root on the VPS.
#
# Re-running is safe: existing UUID / keys / shortId in the state file are reused unless --rotate-keys.
# Every change is backed up to /usr/local/etc/xray/backup/<timestamp>/ first; see uninstall.sh --rollback.
#
# Options (all optional):
#   --port N             port Xray listens on inside the VPS (default 443)
#   --public-port N      port clients dial (provider NAT mapping), default = --port
#   --public-v4 IP       IPv4 clients dial (default: detected egress v4); "none" disables the v4 entry
#   --ipv6               opt in to an IPv6 entry. DEFAULT IS IPv4 ONLY, even when the VPS has a public IPv6;
#                        with --ipv6 the v6 entry is the global IPv6 ON an interface (nat_v6=no), else none
#   --public-v6 IP       IPv6 clients dial (implies --ipv6); use only when the user asked for IPv6;
#                        "none" disables it. Exception: a box with no usable IPv4 falls back to its own v6
#   --public-port-v6 N   if the provider maps a different external port for IPv6 (default = --public-port)
#   --sni HOST           Reality target/SNI (default www.amd.com); verify first with check-dest.sh
#   --version X.Y.Z      Xray-core version (default 25.12.8, see references/core-and-interop.md)
#   --binary PATH        use an uploaded xray binary or Xray-linux-*.zip instead of downloading
#   --mirror PREFIX      download prefix replacing https://github.com (e.g. a GitHub proxy you trust)
#   --dns64              for the download only, temporarily use public DNS64 resolvers (IPv6-only boxes)
#   --health-interval S  supervisor health-check interval in seconds (default 60)
#   --log-level L        xray loglevel (default warning)
#   --bbr                enable fq+bbr via /etc/sysctl.d when the kernel allows it (skipped in containers)
#   --open-firewall      open the listen port in an active ufw/firewalld/iptables firewall
#   --rotate-keys        generate new UUID / keys / shortId even if state exists
#   --name NAME          node name used in client output (default VPS-<sni-label>)
#   --dry-run            print the plan and the config, change nothing
set -eu

PORT=443; PUBPORT=""; PUBPORT6=""; PUB4=auto; PUB6=auto; SNI=www.amd.com; VER=25.12.8
BINARY=""; MIRROR=https://github.com; DNS64=0; HC=60; LOGLEVEL=warning; BBR=0; OPENFW=0
ROTATE=0; NAME=""; DRY=0; WANT6=0
while [ $# -gt 0 ]; do
  case "$1" in
    --port) PORT=$2; shift ;; --public-port) PUBPORT=$2; shift ;; --public-port-v6) PUBPORT6=$2; shift ;;
    --public-v4) PUB4=$2; shift ;; --public-v6) PUB6=$2; WANT6=1; shift ;; --ipv6) WANT6=1 ;; --sni) SNI=$2; shift ;;
    --version) VER=${2#v}; shift ;; --binary) BINARY=$2; shift ;; --mirror) MIRROR=${2%/}; shift ;;
    --dns64) DNS64=1 ;; --health-interval) HC=$2; shift ;; --log-level) LOGLEVEL=$2; shift ;;
    --bbr) BBR=1 ;; --open-firewall) OPENFW=1 ;; --rotate-keys) ROTATE=1 ;; --name) NAME=$2; shift ;;
    --dry-run) DRY=1 ;; -h|--help) sed -n '2,28p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done
[ -n "$PUBPORT" ] || PUBPORT=$PORT
[ -n "$PUBPORT6" ] || PUBPORT6=$PUBPORT
[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }

HERE=$(cd "$(dirname "$0")" && pwd)
BIN=/usr/local/bin/xray
ETC=/usr/local/etc/xray
CFG=$ETC/config.json
STATE=$ETC/vless-reality.env
TS=$(date +%Y%m%d-%H%M%S)
BK=$ETC/backup/$TS
log() { printf '[install] %s\n' "$*"; }
die() { printf '[install] ERROR: %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }
run() { if [ "$DRY" = 1 ]; then log "dry-run: $*"; else "$@"; fi; }

# ---------- 1. detect ----------
DET=$(sh "$HERE/detect.sh")
get() { printf '%s\n' "$DET" | sed -n "s/^$1=//p" | head -n1; }
INIT=$(get init); PKG=$(get pkg); XA=$(get xray_arch); MEMLIM=$(get mem_limit_bytes)
EG4=$(get egress_v4); EG6=$(get egress_v6); V6DIS=$(get ipv6_disabled); CONT=$(get is_container)
FW=$(get firewall)
[ "$XA" != unsupported ] || die "unsupported CPU architecture $(get arch)"
[ "$PUB4" = auto ] && PUB4=${EG4:-none}
# Default: IPv4 only (user rule). IPv6 entry only with --ipv6/--public-v6, or when there is no usable IPv4.
# Even then only a public IPv6 ON an interface (a NATed v6 egress has no inbound mapping => dead node).
if [ "$PUB6" = auto ] && [ "$WANT6" = 0 ] && [ "$PUB4" != none ]; then
  PUB6=none; [ -n "$EG6" ] && log "egress v6 $EG6 present but IPv4-only by default: no IPv6 entry (pass --ipv6 if the user wants one)"
fi
if [ "$PUB6" = auto ]; then
  if [ -n "$EG6" ] && [ "$(get nat_v6)" = no ]; then PUB6=$EG6
  else PUB6=none; [ -n "$EG6" ] && log "egress v6 $EG6 is NATed (not on an interface): no IPv6 entry; pass --public-v6 if the provider gave a v6 mapping"
  fi
fi
[ "$PUB4" = none ] && [ "$PUB6" = none ] && die "no usable public IPv4 or IPv6; pass --public-v4/--public-v6 explicitly"
# listen on :: (dual-stack socket) unless the kernel has IPv6 disabled
if [ "$V6DIS" = 0 ]; then LISTEN="::"; HCHOST=127.0.0.1; [ "$PUB4" = none ] && HCHOST=::1; else LISTEN=0.0.0.0; HCHOST=127.0.0.1; fi
# freedom outbound: avoid AAAA attempts on v4-only egress, avoid A attempts on v6-only egress without DNS64
if [ -n "$EG4" ] && [ -n "$EG6" ]; then DS=AsIs; elif [ -n "$EG4" ]; then DS=UseIPv4; else DS=UseIPv6; fi
log "init=$INIT pkg=$PKG arch=$XA container=$CONT mem_limit=$MEMLIM egress_v4=${EG4:-none} egress_v6=${EG6:-none}"
E4=none; [ "$PUB4" = none ] || E4="$PUB4:$PUBPORT"
E6=none; [ "$PUB6" = none ] || E6="[$PUB6]:$PUBPORT6"
log "client entries: v4=$E4 v6=$E6 ; listen=$LISTEN:$PORT ; freedom domainStrategy=$DS"
[ "$PUB4" != none ] && [ -n "$EG4" ] && [ "$PUB4" != "$EG4" ] && log "note: clients dial $PUB4 but traffic exits from $EG4 (exit-IP checks must expect $EG4)"

# Serving xray processes by /proc/<pid>/exe (BusyBox-safe; same logic as verify-server.sh).
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
# The listen port must be free, or owned by exactly one xray that the service manager supervises.
# Two xray processes, or one outside the supervisor, is an orphan/duplicate: stop and clean up first.
XP=$(xray_pids)
# shellcheck disable=SC2086
set -- $XP
if [ $# -gt 1 ]; then
  die "$# xray processes running (pids: $XP): orphan/duplicate; recover first (references/troubleshooting.md#orphan-or-duplicate-xray)"
elif [ $# -eq 1 ]; then
  pp=$(ppid_of "$1"); pc=$(cat "/proc/$pp/comm" 2>/dev/null)
  case "$INIT" in
    openrc) case "$pc" in supervise-daem*) ;; *) die "xray pid $1 is not under supervise-daemon (parent $pp $pc): orphan; recover first (references/troubleshooting.md#orphan-or-duplicate-xray)" ;; esac ;;  # comm is cut to 15 chars
    systemd) [ "$(systemctl show -p MainPID --value xray 2>/dev/null)" = "$1" ] || die "xray pid $1 is not the xray unit's MainPID: orphan; recover first (references/troubleshooting.md#orphan-or-duplicate-xray)" ;;
    *) ps -o pid,args 2>/dev/null | grep -q "^ *$pp .*xray-supervise" || die "xray pid $1 is not under xray-supervise: orphan; recover first (references/troubleshooting.md#orphan-or-duplicate-xray)" ;;
  esac
fi
if have ss; then owner=$(ss -Htlnp "sport = :$PORT" 2>/dev/null | sed -n 's/.*users:(("\([^"]*\)".*/\1/p' | head -n1); else owner=""; fi
[ -z "$owner" ] || [ "$owner" = xray ] || die "port $PORT is already used by $owner"
if [ "$owner" = xray ] && [ $# -eq 0 ]; then die "port $PORT is held by an xray that is not $BIN; stop it first"; fi

# ---------- 2. credentials (reuse unless rotating) ----------
UUID=""; PRIV=""; PUBK=""; SID=""
if [ -f "$STATE" ] && [ "$ROTATE" = 0 ]; then
  # read only the credentials; command-line options must win over everything else in the state file
  sv() { sed -n "s/^$1='\(.*\)'\$/\1/p" "$STATE" | head -n1; }
  UUID=$(sv UUID); PRIV=$(sv PRIV); PUBK=$(sv PUBK); SID=$(sv SID)
  log "reusing credentials from $STATE"
fi

# ---------- 3. obtain binary ----------
TMPD=$(mktemp -d /tmp/xray-inst.XXXXXX); trap 'rm -rf "$TMPD"' EXIT
NEWBIN=""
need_bin=1
if [ -x "$BIN" ] && [ -z "$BINARY" ] && "$BIN" version 2>/dev/null | head -n1 | grep -q " $VER "; then need_bin=0; log "xray $VER already installed"; fi
pkg_install() {
  case "$PKG" in
    apk) run apk add --no-cache "$@" ;; apt-get) run apt-get install -y -q "$@" ;;
    dnf|yum) run "$PKG" install -y "$@" ;; pacman) run pacman -S --noconfirm "$@" ;; zypper) run zypper -n in "$@" ;;
    *) log "install manually: $*" ;;
  esac
}
if [ "$need_bin" = 1 ]; then
  if [ -n "$BINARY" ]; then
    case "$BINARY" in *.zip) have unzip || pkg_install unzip; unzip -o -q "$BINARY" xray -d "$TMPD" ;; *) cp "$BINARY" "$TMPD/xray" ;; esac
  else
    have curl || pkg_install curl ca-certificates
    have unzip || pkg_install unzip
    URL="$MIRROR/XTLS/Xray-core/releases/download/v$VER/Xray-linux-$XA.zip"
    RESOLV_SAVED=""
    if [ "$DNS64" = 1 ] && [ "$DRY" = 0 ]; then
      RESOLV_SAVED=$TMPD/resolv.conf; cp /etc/resolv.conf "$RESOLV_SAVED"
      # public DNS64 (nat64.net); verify the current list at https://nat64.net before relying on it
      printf 'nameserver 2a00:1098:2b::1\nnameserver 2a00:1098:2c::1\nnameserver 2a01:4f8:c2c:123f::1\n' > /etc/resolv.conf
      log "temporarily using DNS64 resolvers for the download"
    fi
    dl_ok=0
    if [ "$DRY" = 1 ]; then log "dry-run: download $URL"; dl_ok=1
    else
      i=0; while [ $i -lt 3 ]; do
        if curl -fL -sS -m 120 -o "$TMPD/x.zip" "$URL" && curl -fL -sS -m 30 -o "$TMPD/x.dgst" "$URL.dgst"; then dl_ok=1; break; fi
        i=$((i+1)); sleep 3
      done
    fi
    [ -n "$RESOLV_SAVED" ] && cp "$RESOLV_SAVED" /etc/resolv.conf && log "restored /etc/resolv.conf"
    [ "$dl_ok" = 1 ] || die "download failed: $URL (IPv6-only? use --dns64, --mirror, or upload with --binary)"
    if [ "$DRY" = 0 ]; then
      want=$(grep -i 'sha2-256' "$TMPD/x.dgst" | awk '{print $NF}' | head -n1)
      got=$(sha256sum "$TMPD/x.zip" | awk '{print $1}')
      [ -n "$want" ] && [ "$want" = "$got" ] || die "sha256 mismatch for $URL"
      unzip -o -q "$TMPD/x.zip" xray -d "$TMPD"; rm -f "$TMPD/x.zip"   # only the binary: no geo files needed
    fi
  fi
  if [ "$DRY" = 0 ]; then
    chmod 755 "$TMPD/xray"
    "$TMPD/xray" version >/dev/null 2>&1 || die "new binary cannot run on this host"
    NEWBIN=$TMPD/xray
  fi
fi
X=${NEWBIN:-$BIN}

# ---------- 4. generate missing credentials ----------
# 'xray x25519' labels changed across releases: "Public key:", then "Password:", then "Password (PublicKey):"
pubkey_of() { sed -n -e 's/^Password (PublicKey):[[:space:]]*//p' -e 's/^Password:[[:space:]]*//p' -e 's/^Public[ _]*[Kk]ey:[[:space:]]*//p' | head -n1; }
if [ "$DRY" = 0 ]; then
  [ -n "$UUID" ] || UUID=$("$X" uuid)
  if [ -z "$PRIV" ] || [ -z "$PUBK" ]; then
    kp=$("$X" x25519)
    PRIV=$(printf '%s\n' "$kp" | sed -n 's/^Private[ _]*[Kk]ey:[[:space:]]*//p' | head -n1)
    PUBK=$(printf '%s\n' "$kp" | pubkey_of)
    [ -n "$PRIV" ] && [ -n "$PUBK" ] || die "could not parse 'xray x25519' output"
  fi
  # the published public key must derive from the private key
  chk=$("$X" x25519 -i "$PRIV" | pubkey_of)
  [ "$chk" = "$PUBK" ] || die "public key does not match private key"
  [ -n "$SID" ] || SID=$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')
else
  # never print real secrets in a dry run, even when they were loaded from the state file
  UUID='<uuid>'; PRIV='<private-key>'; PUBK='<public-key>'; SID='<short-id>'
fi

# ---------- 5. render config ----------
cat > "$TMPD/config.json" <<JSON
{
  "log": { "loglevel": "$LOGLEVEL", "access": "none" },
  "inbounds": [
    {
      "tag": "vless-reality",
      "listen": "$LISTEN",
      "port": $PORT,
      "protocol": "vless",
      "settings": { "clients": [ { "id": "$UUID", "flow": "xtls-rprx-vision" } ], "decryption": "none" },
      "streamSettings": {
        "network": "tcp",
        "security": "reality",
        "realitySettings": {
          "show": false,
          "dest": "$SNI:443",
          "xver": 0,
          "serverNames": [ "$SNI" ],
          "privateKey": "$PRIV",
          "shortIds": [ "$SID" ]
        }
      }
    }
  ],
  "outbounds": [
    { "tag": "direct", "protocol": "freedom", "settings": { "domainStrategy": "$DS" } },
    { "tag": "block", "protocol": "blackhole" }
  ],
  "routing": {
    "rules": [
      { "type": "field", "outboundTag": "block",
        "ip": [ "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "127.0.0.0/8",
                "169.254.0.0/16", "fc00::/7", "fe80::/10", "::1/128" ] }
    ]
  }
}
JSON
if [ "$DRY" = 1 ]; then
  log "dry-run: config that would be written (secrets shown as placeholders):"; cat "$TMPD/config.json"
else
  "$X" run -test -config "$TMPD/config.json" >/dev/null || die "config test failed"
fi

# ---------- 6. Go memory guard for small budgets ----------
GOENV=""
if [ -n "$MEMLIM" ] && [ "$MEMLIM" -le 536870912 ] 2>/dev/null; then
  gl=$((MEMLIM * 3 / 4 / 1048576))
  GOENV="GOGC=50 GOMEMLIMIT=${gl}MiB"
  log "small memory budget ($((MEMLIM/1048576)) MiB): $GOENV"
fi

[ "$DRY" = 1 ] && { log "dry-run complete; nothing changed"; exit 0; }

# ---------- 7. back up, then install files ----------
mkdir -p "$BK" "$ETC" /var/log/xray
for f in "$CFG" "$STATE" /etc/init.d/xray /etc/systemd/system/xray.service /usr/local/bin/xray-supervise; do
  [ -f "$f" ] && cp -p "$f" "$BK/" || true
done
[ -n "$NEWBIN" ] && [ -x "$BIN" ] && cp -p "$BIN" "$BK/xray.bin" || true
log "backup: $BK"

# service files
HCCMD="nc -z -w 3 $HCHOST $PORT"
if [ "$INIT" = openrc ]; then
  have nc && nc -h 2>&1 | grep -q -- '-z' || pkg_install netcat-openbsd
  {
    echo '#!/sbin/openrc-run'
    echo 'name="xray"'; echo 'description="Xray VLESS Reality"'
    echo 'supervisor=supervise-daemon'
    echo "command=\"$BIN\""; echo "command_args=\"run -c $CFG\""
    echo 'pidfile="/run/xray.pid"'; echo 'retry="TERM/10/KILL/5"'
    for e in $GOENV; do echo "export $e"; done
    echo 'respawn_delay=5'; echo 'respawn_max=3'; echo 'respawn_period=60'
    echo "healthcheck_timer=$HC"
    # any xray running before start or left after stop is an orphan (pidfile names supervise-daemon)
    echo 'kill_strays() {'
    echo '    for d in /proc/[0-9]*; do'
    echo "        case \"\$(readlink \"\$d/exe\" 2>/dev/null)\" in \"$BIN\"|\"$BIN (deleted)\") kill \"\${d#/proc/}\" 2>/dev/null; ewarn \"killed stray xray \${d#/proc/}\" ;; esac"
    echo '    done'
    echo '    return 0'
    echo '}'
    echo 'start_pre() {'; echo "    \"\${command}\" run -test -config $CFG >/dev/null || return 1"; echo '    kill_strays; sleep 1'; echo '}'
    echo 'stop_post() {'; echo '    kill_strays'; echo '}'
    echo 'healthcheck() {'; echo "    $HCCMD"; echo '}'
    echo 'depend() {'; echo '    need net'; echo '    after firewall'; echo '}'
  } > "$TMPD/xray.openrc"
elif [ "$INIT" = systemd ]; then
  {
    echo '[Unit]'; echo 'Description=Xray VLESS Reality'; echo 'After=network-online.target'; echo 'Wants=network-online.target'
    echo 'StartLimitIntervalSec=60'; echo 'StartLimitBurst=3'
    echo '[Service]'
    for e in $GOENV; do echo "Environment=$e"; done
    echo "ExecStartPre=$BIN run -test -config $CFG"
    echo "ExecStart=$BIN run -config $CFG"
    echo 'Restart=on-failure'; echo 'RestartSec=5'; echo 'LimitNOFILE=1048576'
    echo '[Install]'; echo 'WantedBy=multi-user.target'
  } > "$TMPD/xray.service"
  {
    echo '[Unit]'; echo 'Description=Xray listener health check'
    echo '[Service]'; echo 'Type=oneshot'
    echo "ExecStart=/bin/sh -c 'systemctl is-active -q xray || exit 0; for i in 1 2 3; do $HCCMD && exit 0; sleep 2; done; systemctl restart xray'"
  } > "$TMPD/xray-health.service"
  {
    echo '[Unit]'; echo 'Description=Xray health check timer'
    echo '[Timer]'; echo "OnBootSec=$HC"; echo "OnUnitActiveSec=$HC"
    echo '[Install]'; echo 'WantedBy=timers.target'
  } > "$TMPD/xray-health.timer"
else
  {
    echo '#!/bin/sh'
    echo '# fallback supervisor for hosts without an init system'
    for e in $GOENV; do echo "export $e"; done
    echo 'while true; do'
    echo "  $BIN run -test -config $CFG >/dev/null 2>&1 || { sleep 30; continue; }"
    echo "  $BIN run -config $CFG >>/var/log/xray/error.log 2>&1 &"
    echo '  pid=$!; echo $pid > /run/xray.pid'
    echo "  while kill -0 \$pid 2>/dev/null; do sleep $HC; kill -0 \$pid 2>/dev/null || break; $HCCMD 2>/dev/null || { kill \$pid; break; }; done"
    echo '  wait $pid 2>/dev/null; sleep 5'
    echo 'done'
  } > "$TMPD/xray-supervise"
fi

# stop -> replace -> start (never overwrite a running binary)
svc_stop() {
  case "$INIT" in
    openrc) rc-service xray status >/dev/null 2>&1 && rc-service xray stop || true; rc-service xray zap >/dev/null 2>&1 || true ;;
    systemd) systemctl stop xray 2>/dev/null || true ;;
    none) pkill -f /usr/local/bin/xray-supervise 2>/dev/null || true ;;
  esac
  # pidof/pkill -x miss xray on some BusyBox builds; kill by /proc/<pid>/exe
  for p in $(xray_pids); do kill "$p" 2>/dev/null || true; done
  sleep 1
  for p in $(xray_pids); do kill -9 "$p" 2>/dev/null || true; done
}
svc_stop
[ -n "$NEWBIN" ] && cp "$NEWBIN" "$BIN" && chmod 755 "$BIN" && "$BIN" version >/dev/null
cp "$TMPD/config.json" "$CFG"; chmod 600 "$CFG"
case "$INIT" in
  openrc) cp "$TMPD/xray.openrc" /etc/init.d/xray; chmod 755 /etc/init.d/xray
          rc-update add xray default >/dev/null 2>&1 || true; rc-service xray start ;;
  systemd) cp "$TMPD/xray.service" /etc/systemd/system/xray.service
           cp "$TMPD/xray-health.service" "$TMPD/xray-health.timer" /etc/systemd/system/
           systemctl daemon-reload; systemctl enable -q --now xray; systemctl enable -q --now xray-health.timer ;;
  none) cp "$TMPD/xray-supervise" /usr/local/bin/xray-supervise; chmod 755 /usr/local/bin/xray-supervise
        setsid nohup /usr/local/bin/xray-supervise </dev/null >/dev/null 2>&1 &
        if have crontab; then (crontab -l 2>/dev/null | grep -v xray-supervise; echo '@reboot /usr/local/bin/xray-supervise') | crontab -; fi
        log "no init system: started /usr/local/bin/xray-supervise; @reboot entry added only if cron runs here" ;;
esac

# ---------- 8. firewall / sysctl (only when asked) ----------
FWOPEN=""
if [ "$OPENFW" = 1 ]; then
  case "$FW" in
    ufw) ufw allow "$PORT/tcp" >/dev/null && FWOPEN=ufw ;;
    firewalld) firewall-cmd -q --permanent --add-port="$PORT/tcp" && firewall-cmd -q --reload && FWOPEN=firewalld ;;
    iptables) iptables -C INPUT -p tcp --dport "$PORT" -j ACCEPT 2>/dev/null || iptables -I INPUT -p tcp --dport "$PORT" -j ACCEPT
              if have ip6tables; then ip6tables -C INPUT -p tcp --dport "$PORT" -j ACCEPT 2>/dev/null || ip6tables -I INPUT -p tcp --dport "$PORT" -j ACCEPT; fi
              FWOPEN=iptables; log "iptables rules are not persistent; save them with your distro's tool" ;;
    nftables) log "nftables input policy is drop: add 'tcp dport $PORT accept' to your inet filter input chain manually" ;;
    none) log "no active host firewall detected; check the provider security group / panel" ;;
  esac
fi
if [ "$BBR" = 1 ]; then
  if [ "$(get sysctl_writable)" != no ] && [ "$(get bbr_available)" = yes ] && [ "$(get tcp_cc)" != bbr ]; then
    printf 'net.core.default_qdisc=fq\nnet.ipv4.tcp_congestion_control=bbr\n' > /etc/sysctl.d/99-vless-reality-bbr.conf
    sysctl -q -p /etc/sysctl.d/99-vless-reality-bbr.conf && log "bbr enabled" || { rm -f /etc/sysctl.d/99-vless-reality-bbr.conf; log "sysctl write failed; reverted"; }
  else
    log "bbr skipped: sysctl_writable=$(get sysctl_writable) bbr_available=$(get bbr_available) current=$(get tcp_cc)"
  fi
fi

# ---------- 9. state + verification ----------
[ -n "$NAME" ] || NAME="VPS-$(echo "$SNI" | sed 's/^www\.//; s/\..*//')"
umask 077
cat > "$STATE" <<ENV
UUID='$UUID'
PRIV='$PRIV'
PUBK='$PUBK'
SID='$SID'
SNI='$SNI'
PORT='$PORT'
PUBPORT='$PUBPORT'
PUBPORT6='$PUBPORT6'
PUB4='$PUB4'
PUB6='$PUB6'
VER='$VER'
NAME='$NAME'
INIT='$INIT'
FWOPEN='$FWOPEN'
INSTALLED='$TS'
ENV
chmod 600 "$STATE"
sleep 3
if sh "$HERE/verify-server.sh"; then
  log "server-side verification passed"
else
  log "verification FAILED; roll back with: sh $HERE/uninstall.sh --rollback $TS"; exit 1
fi
log "client output: sh $HERE/gen-client.sh   (prints secrets: show it only to the owner)"
