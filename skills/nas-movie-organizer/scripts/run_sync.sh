#!/usr/bin/env bash
# NAS 定时回填报表：只更新 Excel 状态，不移动文件、不下字幕
set -u

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

exec /usr/bin/flock -n "$BASE_DIR/.sync.lock" \
    /usr/bin/python3 "$BASE_DIR/nas_organize.py" sync "$@"
