#!/usr/bin/env bash
# 按型号（可选：硬件序列号）解析出当前可用的 adb transport serial。
# 手机 IP 由 DHCP 分配，会变；mDNS 名字和 ro.product.model 不会。
# 用法： adb-find.sh <model> [hw-serial]        -> stdout 打印 serial，失败 exit 1
# 例：   adb-find.sh PJE110
#        adb-find.sh PKH110 e919fca2
set -uo pipefail

ADB="${ADB:-C:/Users/everx/AppData/Local/Android/Sdk/platform-tools/adb.exe}"
MODEL="${1:?用法: adb-find.sh <model> [hw-serial]}"
WANT_SERIAL="${2:-}"

log() { printf '%s\n' "$*" >&2; }

devices() {  # 只输出处于 device 状态的 transport serial
  "$ADB" devices 2>/dev/null | awk 'NR>1 && $2=="device" {print $1}'
}

describe() {
  "$ADB" -s "$1" shell 'printf "%s\t%s\n" "$(getprop ro.product.model)" "$(getprop ro.serialno)"' 2>/dev/null \
    | tr -d '\r' | head -1
}

matches() {  # $1=serial
  local info model hw
  info="$(describe "$1")"
  [ -n "$info" ] || return 1
  model="${info%%$'\t'*}"
  hw="${info##*$'\t'}"
  [ "$model" = "$MODEL" ] || return 1
  if [ -n "$WANT_SERIAL" ] && [ "$hw" != "$WANT_SERIAL" ]; then return 1; fi
  return 0
}

# 1) 已经连着（USB 或此前 connect 过的网络设备）
while read -r serial; do
  [ -n "$serial" ] || continue
  if matches "$serial"; then echo "$serial"; exit 0; fi
done < <(devices)

# 2) 走 mDNS 探测：_adb._tcp 才能 adb connect（_adb-tls-connect 需要先配对）
endpoints="$("$ADB" mdns services 2>/dev/null | awk '$2=="_adb._tcp" {print $3}')"
probed=()
for ep in $endpoints; do
  # 想指定硬件序列号时，名字里带它的先试
  if [ -n "$WANT_SERIAL" ] && [ -z "${_sorted:-}" ]; then
    _sorted=1
    pref="$("$ADB" mdns services 2>/dev/null | awk -v s="adb-$WANT_SERIAL" '$2=="_adb._tcp" && index($1,s)==1 {print $3}')"
    [ -n "$pref" ] && endpoints="$pref $(echo "$endpoints" | grep -vxF "$pref" | tr '\n' ' ')"
  fi
  devices | grep -qxF "$ep" && continue
  log "[probe] adb connect $ep"
  "$ADB" connect "$ep" >/dev/null 2>&1 || { log "[probe] 连不上 $ep"; continue; }
  probed+=("$ep")
  for _ in 1 2 3 4 5; do
    if matches "$ep"; then echo "$ep"; exit 0; fi
    sleep 0.8
  done
done

# 探测过的端点若不对，断开，别留一堆僵尸 transport
for ep in "${probed[@]:-}"; do
  [ -n "$ep" ] || continue
  matches "$ep" || { log "[probe] 断开不匹配的 $ep"; "$ADB" disconnect "$ep" >/dev/null 2>&1; }
done

log "没找到型号 $MODEL${WANT_SERIAL:+（硬件序列号 $WANT_SERIAL）} 的设备。"
log "检查：手机和电脑同一 Wi-Fi、手机开着「无线调试」、PKH110 这类主力机可能根本不在家。"
log "当前 adb 设备："
"$ADB" devices -l >&2
exit 1
