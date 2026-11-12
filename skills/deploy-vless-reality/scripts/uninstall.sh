#!/bin/sh
# Roll back or uninstall what install.sh did.
#   sh uninstall.sh --list                 list backups
#   sh uninstall.sh --rollback <timestamp> restore config/state/service/binary from that backup and restart
#   sh uninstall.sh                        stop + remove service, binary, config (a final backup is kept)
#   sh uninstall.sh --purge                same, and also delete state and all backups
set -u
ETC=/usr/local/etc/xray; BIN=/usr/local/bin/xray; STATE=$ETC/vless-reality.env
log() { printf '[uninstall] %s\n' "$*"; }
[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }
if [ -d /run/systemd/system ]; then INIT=systemd; elif command -v rc-service >/dev/null 2>&1; then INIT=openrc; else INIT=none; fi

svc() { # svc stop|start
  case "$INIT:$1" in
    systemd:stop) systemctl stop xray-health.timer xray 2>/dev/null ;;
    systemd:start) systemctl daemon-reload; systemctl start xray; systemctl start xray-health.timer 2>/dev/null ;;
    openrc:stop) rc-service xray stop 2>/dev/null; rc-service xray zap 2>/dev/null ;;
    openrc:start) rc-service xray start ;;
    none:stop) pkill -f /usr/local/bin/xray-supervise 2>/dev/null ;;
    none:start) setsid nohup /usr/local/bin/xray-supervise </dev/null >/dev/null 2>&1 & ;;
  esac
  # stop also clears orphan/duplicate xray (pkill -x misses it on some BusyBox builds)
  if [ "$1" = stop ]; then
    for d in /proc/[0-9]*; do
      case "$(readlink "$d/exe" 2>/dev/null)" in "$BIN"|"$BIN (deleted)") kill "${d#/proc/}" 2>/dev/null ;; esac
    done
  fi
  return 0
}

case "${1:-}" in
  --list) ls -1 "$ETC/backup" 2>/dev/null; exit 0 ;;
  --rollback)
    b=$ETC/backup/${2:?timestamp required, see --list}
    [ -d "$b" ] || { log "no backup $b"; exit 1; }
    svc stop
    [ -f "$b/config.json" ] && cp -p "$b/config.json" "$ETC/config.json"
    [ -f "$b/vless-reality.env" ] && cp -p "$b/vless-reality.env" "$STATE"
    [ -f "$b/xray" ] && cp -p "$b/xray" /etc/init.d/xray
    [ -f "$b/xray.service" ] && cp -p "$b/xray.service" /etc/systemd/system/xray.service
    [ -f "$b/xray-supervise" ] && cp -p "$b/xray-supervise" /usr/local/bin/xray-supervise
    [ -f "$b/xray.bin" ] && cp -p "$b/xray.bin" "$BIN"
    "$BIN" run -test -config "$ETC/config.json" >/dev/null || { log "restored config fails its test; service left stopped"; exit 1; }
    svc start; log "rolled back to $b"; exit 0 ;;
esac

FWOPEN=""; PORT=""
# shellcheck disable=SC1090
[ -r "$STATE" ] && . "$STATE"
TS=$(date +%Y%m%d-%H%M%S); FINAL=$ETC/backup/final-$TS
mkdir -p "$FINAL"
for f in "$ETC/config.json" "$STATE" /etc/init.d/xray /etc/systemd/system/xray.service; do [ -f "$f" ] && cp -p "$f" "$FINAL/"; done
svc stop
case "$INIT" in
  systemd) systemctl disable -q xray xray-health.timer 2>/dev/null
           rm -f /etc/systemd/system/xray.service /etc/systemd/system/xray-health.service /etc/systemd/system/xray-health.timer
           systemctl daemon-reload ;;
  openrc) rc-update del xray default >/dev/null 2>&1; rm -f /etc/init.d/xray ;;
  none) rm -f /usr/local/bin/xray-supervise
        command -v crontab >/dev/null 2>&1 && crontab -l 2>/dev/null | grep -v xray-supervise | crontab - ;;
esac
if [ -n "$PORT" ]; then
  case "$FWOPEN" in
    ufw) ufw delete allow "$PORT/tcp" >/dev/null 2>&1 ;;
    firewalld) firewall-cmd -q --permanent --remove-port="$PORT/tcp" && firewall-cmd -q --reload ;;
    iptables) iptables -D INPUT -p tcp --dport "$PORT" -j ACCEPT 2>/dev/null
              ip6tables -D INPUT -p tcp --dport "$PORT" -j ACCEPT 2>/dev/null ;;
  esac
fi
if [ -f /etc/sysctl.d/99-vless-reality-bbr.conf ]; then
  rm -f /etc/sysctl.d/99-vless-reality-bbr.conf; log "removed bbr drop-in (takes effect on reboot or after sysctl --system)"
fi
rm -f "$BIN" "$ETC/config.json"
if [ "${1:-}" = --purge ]; then rm -rf "$ETC" /var/log/xray; log "purged $ETC"
else rm -f "$STATE"; log "removed; final backup kept in $FINAL (contains secrets, mode 700)"; chmod 700 "$ETC/backup"; fi
