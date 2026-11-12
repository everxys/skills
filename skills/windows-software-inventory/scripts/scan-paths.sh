#!/usr/bin/env bash
# Read-only software/tool path inventory for a Windows host driven from
# git-bash (MSYS). Run this BEFORE any ad-hoc `find /` sweep.
#
#   bash scan-paths.sh             # print report
#   bash scan-paths.sh > out.md    # capture it
#
# Nothing here writes, installs or deletes. `winget list` is the only slow step
# and is opt-in via WITH_WINGET=1.
set -u

CMDS="mise git gh python python3 node npm npx ffmpeg cloudflared fd rg rustc rustup cargo pwsh powershell psql postgres pg_ctl winget chrome syncthing"

echo "=== 1. PATH resolution (shim vs real) ==="
for c in $CMDS; do
  printf '%s|%s\n' "$c" "$(command -v "$c" 2>/dev/null || echo NOTFOUND)"
done

echo
echo "=== 2. PATH entries ==="
printf '%s\n' "$PATH" | tr ':' '\n' | grep -v '^$'

echo
echo "=== 3. mise ==="
mise list 2>&1 | head -60
echo "-- installs"
ls -d "$HOME"/AppData/Local/mise/installs/*/* 2>/dev/null
echo "-- shims"
ls "$HOME"/AppData/Local/mise/shims 2>/dev/null
echo "-- global config"
cat "$HOME"/.config/mise/config.toml 2>/dev/null

echo
echo "=== 4. winget: Links is a symlink farm, Packages holds the real files ==="
for f in "$HOME"/AppData/Local/Microsoft/WinGet/Links/*.exe; do
  [ -e "$f" ] || continue
  printf '%s -> %s\n' "$(basename "$f")" "$(readlink -f "$f")"
done
ls "$HOME"/AppData/Local/Microsoft/WinGet/Packages 2>/dev/null

echo
echo "=== 5. GUI application roots (read exact names, do not guess) ==="
for d in "$HOME/AppData/Local/Programs" "$HOME/AppData/Local" "$HOME/software" "/c/Program Files" "/c/Program Files (x86)"; do
  echo "-- $d"
  ls "$d" 2>/dev/null
  echo
done

echo
echo "=== 6. language package managers ==="
echo '-- npm global'
npm ls -g --depth=0 2>&1 | head -40
echo '-- cargo bin'
ls "$HOME"/.cargo/bin 2>/dev/null
echo '-- rustup toolchains'
rustup toolchain list 2>&1 | head -10
echo '-- python (real one only)'
for py in "$HOME"/AppData/Local/mise/installs/python/*/python.exe; do
  [ -e "$py" ] || continue
  echo "$py"
  "$py" -m pip list 2>/dev/null | head -40
done

echo
echo "=== 7. installs that hide outside PATH ==="
for d in "/c/Program Files/PostgreSQL" "/c/Program Files/PostgreSQL"/*/bin; do
  [ -d "$d" ] && echo "-- $d" && ls "$d" 2>/dev/null | head -40
done

if [ "${WITH_WINGET:-0}" = "1" ]; then
  echo
echo "=== 8. winget inventory (slow, large) ==="
  "$HOME"/AppData/Local/Microsoft/WindowsApps/winget.exe list --accept-source-agreements 2>&1 | tr -d '\r'
fi
