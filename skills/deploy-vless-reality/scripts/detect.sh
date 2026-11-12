#!/bin/sh
# Read-only environment detection for a VLESS+Reality deployment.
# Prints key=value lines (safe to `eval` after filtering with grep '^[a-z0-9_]*=').
# Never installs, writes, or restarts anything. Safe to run on a production node.
# Usage: sh detect.sh [--no-net]    (--no-net skips outbound HTTP probes)

NO_NET=0
[ "$1" = "--no-net" ] && NO_NET=1

kv() { printf '%s=%s\n' "$1" "$2"; }
have() { command -v "$1" >/dev/null 2>&1; }

fetch() { # fetch FAMILY URL  -> body on stdout, empty on failure
  fam=$1; url=$2
  if have curl; then curl "-$fam" -fsS -m 8 "$url" 2>/dev/null
  elif have wget; then wget "-$fam" -q -T 8 -O - "$url" 2>/dev/null
  fi
}

is_private_v4() {
  case "$1" in
    10.*|127.*|169.254.*|192.168.*) return 0 ;;
    172.1[6-9].*|172.2[0-9].*|172.3[01].*) return 0 ;;
    100.6[4-9].*|100.[7-9][0-9].*|100.1[01][0-9].*|100.12[0-7].*) return 0 ;;
  esac
  return 1
}

# ---------- OS / arch / package manager ----------
os_id=unknown; os_ver=unknown
if [ -r /etc/os-release ]; then
  os_id=$(. /etc/os-release; echo "${ID:-unknown}")
  os_ver=$(. /etc/os-release; echo "${VERSION_ID:-unknown}")
fi
kv os_id "$os_id"; kv os_version "$os_ver"
for p in apk apt-get dnf yum pacman zypper; do have "$p" && { kv pkg "$p"; break; }; done
arch=$(uname -m); kv arch "$arch"
case "$arch" in
  x86_64|amd64) xa=64 ;; aarch64|arm64) xa=arm64-v8a ;; armv7*|armv8l) xa=arm32-v7a ;;
  i386|i686) xa=32 ;; riscv64) xa=riscv64 ;; s390x) xa=s390x ;; *) xa=unsupported ;;
esac
kv xray_arch "$xa"
kv kernel "$(uname -r)"

# ---------- init system ----------
if [ -d /run/systemd/system ]; then init=systemd
elif have openrc-run || [ -d /run/openrc ]; then init=openrc
else init=none; fi
kv init "$init"

# ---------- virtualization / container ----------
virt=unknown
if have systemd-detect-virt; then virt=$(systemd-detect-virt 2>/dev/null || echo none); fi
if [ "$virt" = unknown ] || [ "$virt" = none ]; then
  c=$(tr '\0' '\n' </proc/1/environ 2>/dev/null | sed -n 's/^container=//p' | head -n1)
  if [ -n "$c" ]; then virt=$c
  elif [ -f /run/.containerenv ]; then virt=podman
  elif [ -f /.dockerenv ]; then virt=docker
  elif [ -e /proc/vz ] && [ ! -e /proc/bc ]; then virt=openvz
  elif grep -qa 'lxc' /proc/1/cgroup 2>/dev/null; then virt=lxc
  elif grep -q '^flags.* hypervisor' /proc/cpuinfo 2>/dev/null; then virt=vm
  fi
fi
kv virt "$virt"
case "$virt" in podman|docker|lxc|lxc-libvirt|openvz|systemd-nspawn|container-other|wsl) kv is_container yes ;; *) kv is_container no ;; esac

# ---------- CPU / memory budget ----------
kv cpus "$(grep -c '^processor' /proc/cpuinfo 2>/dev/null || echo 1)"
mem_total=$(awk '/^MemTotal:/{print $2*1024}' /proc/meminfo 2>/dev/null)
kv mem_total_bytes "${mem_total:-0}"
lim=""
if [ -r /sys/fs/cgroup/memory.max ]; then lim=$(cat /sys/fs/cgroup/memory.max)
elif [ -r /sys/fs/cgroup/memory/memory.limit_in_bytes ]; then lim=$(cat /sys/fs/cgroup/memory/memory.limit_in_bytes); fi
case "$lim" in ''|max) lim=$mem_total ;; esac
# cgroup v1 reports a huge number when unlimited
if [ -n "$lim" ] && [ -n "$mem_total" ] && [ "$lim" -gt "$mem_total" ] 2>/dev/null; then lim=$mem_total; fi
kv mem_limit_bytes "${lim:-0}"
if [ -r /sys/fs/cgroup/memory.events ]; then
  kv cg_mem_events_max "$(awk '$1=="max"{print $2}' /sys/fs/cgroup/memory.events)"
  kv cg_oom_kill "$(awk '$1=="oom_kill"{print $2}' /sys/fs/cgroup/memory.events)"
fi

# ---------- kernel tuning privilege ----------
cc=$(cat /proc/sys/net/ipv4/tcp_congestion_control 2>/dev/null); kv tcp_cc "${cc:-unknown}"
avail=$(cat /proc/sys/net/ipv4/tcp_available_congestion_control 2>/dev/null)
case " $avail " in *" bbr "*) kv bbr_available yes ;; *) kv bbr_available no ;; esac
# `test -w` is not reliable here (root passes it even on a read-only /proc/sys), so read the mount flags.
if awk '$2=="/proc/sys" && $4 ~ /(^|,)ro(,|$)/ {f=1} END {exit !f}' /proc/mounts 2>/dev/null; then sw=no
elif [ "$(id -u)" != 0 ]; then sw=no
else sw=maybe; fi   # "maybe": only an actual write proves it; install.sh --bbr reverts on failure
kv sysctl_writable "$sw"
kv cap_eff "$(awk '/^CapEff:/{print $2}' /proc/1/status 2>/dev/null)"
kv ipv6_disabled "$(cat /proc/sys/net/ipv6/conf/all/disable_ipv6 2>/dev/null || echo 1)"
kv bindv6only "$(cat /proc/sys/net/ipv6/bindv6only 2>/dev/null || echo unknown)"

# ---------- addresses on interfaces ----------
v4_pub_if=""; v4_priv_if=""; v6_glob_if=""; v6_ula_if=""
if have ip; then
  for a in $(ip -o -4 addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1); do
    if is_private_v4 "$a"; then v4_priv_if="$v4_priv_if $a"; else v4_pub_if="$v4_pub_if $a"; fi
  done
  for a in $(ip -o -6 addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1); do
    case "$a" in [23]*) v6_glob_if="$v6_glob_if $a" ;; f[cd]*) v6_ula_if="$v6_ula_if $a" ;; esac
  done
  ip -4 route show default 2>/dev/null | grep -q . && kv v4_default_route yes || kv v4_default_route no
  ip -6 route show default 2>/dev/null | grep -q . && kv v6_default_route yes || kv v6_default_route no
fi
kv if_v4_public "$(echo $v4_pub_if)"; kv if_v4_private "$(echo $v4_priv_if)"
kv if_v6_global "$(echo $v6_glob_if)"; kv if_v6_ula "$(echo $v6_ula_if)"

# ---------- DNS ----------
kv nameservers "$(awk '/^nameserver/{printf "%s ", $2}' /etc/resolv.conf 2>/dev/null)"
gh6=no
if have getent; then getent ahostsv6 github.com 2>/dev/null | awk '{print $1}' | grep -v '^::ffff:' | grep -q ':' && gh6=yes
elif have nslookup; then nslookup -type=AAAA github.com 2>/dev/null | grep -qi 'has AAAA\|AAAA address\|Address: .*:' && gh6=yes; fi
kv github_has_aaaa "$gh6"   # yes on an IPv6-only box usually means DNS64 is active

# ---------- outbound reachability / public IPs ----------
if [ "$NO_NET" = 0 ]; then
  pub4=$(fetch 4 https://api.ipify.org | tr -dc '0-9.')
  pub6=$(fetch 6 https://api64.ipify.org | tr -dc '0-9a-fA-F:')
  case "$pub6" in *:*) ;; *) pub6="" ;; esac
  kv egress_v4 "$pub4"; kv egress_v6 "$pub6"
  if [ -n "$pub4" ] && [ -n "$pub6" ]; then kv egress_stack dual
  elif [ -n "$pub4" ]; then kv egress_stack v4
  elif [ -n "$pub6" ]; then kv egress_stack v6
  else kv egress_stack none; fi
  # NAT: egress address not present on any interface
  if [ -n "$pub4" ]; then case " $v4_pub_if " in *" $pub4 "*) kv nat_v4 no ;; *) kv nat_v4 yes ;; esac; fi
  if [ -n "$pub6" ]; then case " $v6_glob_if " in *" $pub6 "*) kv nat_v6 no ;; *) kv nat_v6 yes ;; esac; fi
  if have curl; then
    curl -fsSI -m 8 -o /dev/null https://github.com 2>/dev/null && kv github_reachable yes || kv github_reachable no
  fi
fi

# ---------- tools ----------
t=""; for x in curl wget unzip openssl nc ss netstat crontab logrotate; do have "$x" && t="$t $x"; done
kv tools "$(echo $t)"

# ---------- listeners / existing install ----------
if have ss; then l=$(ss -Htln 2>/dev/null | awk '{print $4}' | sed 's/.*://' | sort -un | tr '\n' ' ')
elif have netstat; then l=$(netstat -tln 2>/dev/null | awk 'NR>2{print $4}' | sed 's/.*://' | sort -un | tr '\n' ' '); fi
kv tcp_listening "$l"
if [ -x /usr/local/bin/xray ]; then kv xray_installed "$(/usr/local/bin/xray version 2>/dev/null | awk 'NR==1{print $2}')"; else kv xray_installed no; fi
[ -f /usr/local/etc/xray/config.json ] && kv xray_config present || kv xray_config absent
[ -f /usr/local/etc/xray/vless-reality.env ] && kv skill_state present || kv skill_state absent
pid=$(pidof xray 2>/dev/null | awk '{print $1}')
kv xray_running "${pid:+yes}"
if [ -n "$pid" ]; then
  kv xray_env "$(tr '\0' '\n' </proc/"$pid"/environ 2>/dev/null | grep -E '^(GOGC|GOMEMLIMIT)=' | tr '\n' ' ')"
fi
hc=$(ps -o args 2>/dev/null | sed -n 's/.*--healthcheck-timer \([0-9]*\).*/\1/p' | head -n1)
kv healthcheck_timer "$hc"

# ---------- firewall ----------
fw=none
if have ufw && ufw status 2>/dev/null | grep -q '^Status: active'; then fw=ufw
elif have firewall-cmd && firewall-cmd --state 2>/dev/null | grep -q running; then fw=firewalld
elif have nft && nft list ruleset 2>/dev/null | grep -q 'hook input.*policy drop'; then fw=nftables
elif have iptables && iptables -S INPUT 2>/dev/null | grep -Eq '^-P INPUT (DROP|REJECT)'; then fw=iptables
fi
kv firewall "$fw"
