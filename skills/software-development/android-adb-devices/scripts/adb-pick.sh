#!/usr/bin/env bash
# 两台手机都不保证在线：按给定顺序返回第一台真正连得上的，输出 "<model> <serial>"。
# 用法： adb-pick.sh [model...]        默认顺序 PJE110 PKH110
# 例：   read -r MODEL SERIAL <<< "$(bash adb-pick.sh)"
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ $# -eq 0 ]; then set -- PJE110 PKH110; fi

for m in "$@"; do
  if s="$(bash "$HERE/adb-find.sh" "$m" 2>/dev/null)"; then
    [ -n "$s" ] || continue
    printf '%s %s\n' "$m" "$s"
    exit 0
  fi
done

echo "没有在线设备（试过：$*）。" >&2
echo "让用户确认至少一台手机在同一 Wi-Fi、开着「无线调试」且没被带走；别假设某台一定在。" >&2
exit 1
