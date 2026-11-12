#!/usr/bin/env bash
# NAS 死种巡检：停止占用下载槽的死任务，并尝试用 Jackett 搜索替代资源
set -u

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

exec /usr/bin/flock -n "$BASE_DIR/.heal.lock" \
    /usr/bin/python3 "$BASE_DIR/nas_movie.py" heal --repair --max-repairs 3 "$@"
