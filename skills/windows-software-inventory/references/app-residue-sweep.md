# Sweeping several apps' residue at once

The request: "delete every leftover of A, B, C and D." The failure modes are
assuming the app is gone when it is running, deleting the wrong sibling that
shares a vendor directory, leaving shims that keep the command alive, and
reporting success from exit codes instead of from the filesystem.

## 1. Inventory before deciding anything (read-only)

One bounded pass, no disk sweep:

```bash
echo "=== PATH ==="; for c in agy gemini opencode dsh; do printf "%-18s %s\n" "$c" "$(which $c 2>/dev/null || echo -)"; done
echo "=== candidate dirs ==="
for p in ~/.<vendor> "$LOCALAPPDATA/Programs/<Name>" "$LOCALAPPDATA/<name>" \
         "$LOCALAPPDATA/<name>-updater" "$APPDATA/<Name>" \
         ~/.config/<name> ~/.local/share/<name>; do
  [ -e "$p" ] && echo "$(du -sh "$p" 2>/dev/null | cut -f1)  $p"
done
echo "=== package managers ==="; npm ls -g --depth=0 | grep -iE '<a>|<b>'; mise ls | grep -iE '<a>|<b>'
echo "=== uninstall registry ==="
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall" /s 2>/dev/null \
  | grep -iE 'DisplayName|InstallLocation' | grep -iE '<a>|<b>'
echo "=== processes ==="; tasklist | grep -iE '<a>|<b>'
echo "=== start menu ==="; ls "$APPDATA/Microsoft/Windows/Start Menu/Programs" | grep -iE '<a>|<b>'
```

Sizes come from the same pass you use to decide — never ask the user to choose
scope from a list of names alone.

## 2. Quarantine layout

```bash
Q="$LOCALAPPDATA/hermes/cache/trash-$(date +%Y%m%d)-agents"
mkdir -p "$Q"/{<a>,<b>,<c>}
```

One subdirectory per product, source path encoded in the moved name
(`Programs-<Name>`, `LocalAppData-<name>-updater`, `Roaming-<Name>`,
`dot-<vendor>`, `config-<name>`) so the restore path is readable without a
manifest.

## 3. The move helper — keep going past failures

```bash
mvx() { src="$1"; dest="$2"
  if [ -e "$src" ]; then sz=$(du -sh "$src" 2>/dev/null|cut -f1); mkdir -p "$dest"
    if mv "$src" "$dest/" 2>/tmp/mverr; then echo "OK   $sz  $src"
    else echo "FAIL $src : $(cat /tmp/mverr)"; fi
  else echo "skip (absent) $src"; fi; }
```

A partial failure must not abort the sweep: report the survivors and handle them
one by one. `FAIL ... Permission denied` on a directory that a running process
owns is the common first-pass failure — kill the process, then re-run just that
move.

## 4. Order of operations

1. Kill the running process (PowerShell `Stop-Process -Force`), confirm it is
   gone, then move.
2. Owner-level uninstall first: `npm uninstall -g <pkg>`, `mise unuse -g -y
   <tool>`, `winget uninstall <id>`.
3. Then the move set: install dir, `<dir>-updater` cache, `%APPDATA%` data dir,
   Start Menu folder, and the vendor dot-directory last (it is the one holding
   locks).
4. Then the shims the package manager left: `shims/<tool>` and
   `shims/<tool>.cmd` for each removed command.
5. Then re-`which` every command name.

## 5. Verification battery

```bash
for c in <a> <b> <c>; do printf "%-10s %s\n" "$c" "$(which $c 2>/dev/null || echo 'gone ✓')"; done
npm ls -g --depth=0 | grep -iE '<a>|<b>' || echo 'no packages ✓'
for p in <all removed paths>; do [ -e "$p" ] && echo "still there $p" || echo "gone ✓ $p"; done
# no `du -sh` on $Q here: sizes already came out of mvx, and re-walking a
# multi-GB tree can eat the whole call's timeout — see "Purging" below
```

Also re-run the meta-tool that listed the apps: entries whose config path
vanished drop out of its own list, which is independent confirmation you did
not remove a path it still needs.

## 6. What the report says

- One bullet block per product, in the user's order, each with the paths and the
  total it accounted for.
- The quarantine root, its total, and one copy-pasteable restore line:
  `mv "<quarantine>/<product>/<moved-name>" <original path>`.
- Note that the disk is not actually free until the quarantine is purged, and
  offer that purge as the next explicit step.
- Anything that refused deletion, with the reason in one clause (locked by a
  running app, cloud placeholder) and who can remove it.

## 7. Purging the quarantine — one call, raised timeout

Purge is irreversible, so it gets a call of its own: nothing else in the batch
can strand it half-done, and the timeout can be raised.

```bash
before=$(powershell -NoProfile -Command "[math]::Round((Get-PSDrive C).Free/1GB,1)")
rm -rf "$Q"; echo "rm exit=$?"
[ -e "$Q" ] && echo 'still exists' || echo 'purged ✓'
after=$(powershell -NoProfile -Command "[math]::Round((Get-PSDrive C).Free/1GB,1)")
echo "freed ≈ $(echo "$after - $before" | bc 2>/dev/null || echo "$after GB now vs $before GB before")"
for c in <a> <b> <c>; do printf "%-10s %s\n" "$c" "$(which $c 2>/dev/null || echo 'gone ✓')"; done
```

Report the measured `after - before` as the space reclaimed. It is routinely far
below the quarantine's size (the uninstaller had already released most of it),
so give the measured number and one clause of why — repeating the directory size
as "freed" is a claim the drive contradicts.
