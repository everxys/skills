#!/usr/bin/env bash
# NAS 常驻批量下载启动器
# 用法: bash run_batch.sh [csv路径] [额外的 nas_movie.py batch 参数...]
# 默认行为: 读取同目录的愿望单 CSV，跳过剧集与续集，全量推入 qBittorrent 队列。
set -u

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CSV_FILE="${1:-$BASE_DIR/db-movie-wishlist-20261025.csv}"
if [ "$#" -gt 0 ]; then
    shift
fi

if pgrep -f "nas_movie.py batch" > /dev/null 2>&1; then
    echo "[!] 已有 batch 任务在运行，跳过本次启动。"
    exit 0
fi

exec python3 "$BASE_DIR/nas_movie.py" batch "$CSV_FILE" --skip-tv --skip-sequels "$@"
