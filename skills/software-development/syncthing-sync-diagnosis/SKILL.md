---
name: syncthing-sync-diagnosis
description: Use when Syncthing peers disagree on sync state.
version: 0.1.0
author: everxys, Hermes Agent
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [syncthing, sync, network, diagnostics, rest-api]
    related_skills: [windows-software-inventory]
---

# Syncthing sync diagnosis

"A says 100%, B says 8%" is almost never what it looks like. The percentage a
node shows next to a device is **that peer's completion as last reported**, not
this node's progress, and it is stale whenever the peer's connection churns. Read
the local REST API before forming any theory, and never quote a deficit from a
single sample.

## When to use

- Two devices disagree about whether a folder is synced.
- Sync "is slow", stalls, or never settles.
- A folder was removed/re-added, an app reinstalled, or an index reset and the
  numbers stopped making sense.
- Don't use for: installing/uninstalling Syncthing or locating its binary (that
  is `windows-software-inventory`, which also records the config-dir split
  between exe and `%LOCALAPPDATA%\Syncthing`).

## Step 1 — the local truth first, never the GUI

Config dir holds `config.xml` (with `<apikey>`), `syncthing.log`, `index-v2`.
GUI/API default `127.0.0.1:8384`. Probe recipes: `references/rest-api-probes.md`.

- `/rest/db/status?folder=X` with `needBytes=0` and `state=idle` is a fact: this
  node holds everything. A device percentage is an estimate.
- `/rest/config/options`: `maxSendKbps`/`maxRecvKbps` of `0` means unlimited.
  Read this before blaming a rate cap.

## Step 2 — whose progress is that number?

Completion comes from the last index the peer sent us; the UI does not show its
age. So:

- Compute per-device per-folder completion in one pass
  (`/rest/db/completion?folder=&device=`); do not eyeball several rows.
- Confirm freshness from `/rest/events`: collect `FolderCompletion` for that
  device and diff `needBytes` between samples. A need that collapses from GB to
  KB in seconds is **index catch-up, not a transfer** — the peer had the data all
  along and the earlier reading was stale.
- Never tell the user "the peer is missing N GB" from one sample. If an earlier
  answer already did, retract that specific sentence in the same message as the
  corrected finding.

## Step 3 — measure real throughput before calling it slow

Take two `/rest/system/connections` snapshots 10–30 s apart and diff
`inBytesTotal`/`outBytesTotal` per device.

- Zero on every device while a UI claims syncing = nothing is moving on this
  node's links. The data is probably flowing between two *other* peers (e.g. the
  phone pulls from the NAS, not from this PC). Say that instead of tuning this
  node.
- `type=tcp-client|tcp-server` with `isLocal=true` is LAN. `relay-client` is a
  WAN relay: orders of magnitude slower, and a reason to pin static addresses.

## Step 4 — log forensics (`syncthing.log` in the config dir)

- `Peer has a new index ID (device=… folder.id=…)` — that peer reset or re-added
  the folder. Its completion reads wrong until it resends a full index; expect
  the big jump from Step 2.
- Repeated `forcibly closed by the remote host` / `Failed to exchange Hello
  messages` — the peer drops every connection. Each reconnect redoes handshake
  and index exchange, so sustained transfer is impossible. On Android that is
  the app being frozen (battery optimisation), not a Syncthing bug.
- `relay-client … connection.local=198.18.0.1` on a Clash/TUN host — P2P traffic
  is being routed through the proxy.

## Step 5 — speed, in order of magnitude

1. **Physical link first.** `netsh wlan show interfaces` (PHY rate, signal) and
   `netsh interface show interface` (is Ethernet *disconnected* while Wi-Fi
   carries the transfer?). Wi-Fi-to-Wi-Fi halves throughput; hundreds of GB over
   Wi-Fi is hours, and no config change fixes that. Two commands settle most
   "why is it slow" questions.
2. LAN vs relay: pin `tcp://<lan-ip>:22000` on both sides; relays off if the
   fleet is LAN-only.
3. TUN proxy (Clash/Mihomo): DIRECT rules for the Syncthing process and the LAN
   ranges, or the P2P link is at the proxy's mercy.
4. Peer power management: battery optimisation off, foreground service on for a
   large transfer.
5. Content churn (below).
6. Only now the knobs (`maxSendKbps`, `maxRecvKbps`, concurrency).

## Content that keeps a folder from ever settling

A live SQLite DB inside a synced folder writes new blocks continuously and
spawns a `.sync-conflict-*` copy per collision, so the folder never reaches idle
and the user reads that as "slow sync". Same for git worktrees and build output.

- Count before proposing: `find . -name '*sync-conflict*' -printf '%s %p\n'`.
- Fix by excluding `*.db`, `*.db-wal`, `*.db-shm`, `*.sync-conflict-*` in
  `.stignore`, or by moving the DB out of the synced tree.

## Version skew is usually not the cause

v1.x peers sync fine with a v2.x node (same BEP protocol). Say so once and move
on; do not let "update the app" become the first hypothesis.

## Acting on this host (consent and revert)

- Probe read-only first; report findings before touching config.
- Config edits (static device address, `relaysEnabled`, `.stignore`, deleting
  conflict copies) get explained in plain language with the visible effect and
  the revert path, then applied only when the user picks. No silent changes.
- Answer in Chinese, bullets, no tables.

## Pitfalls

- `curl` on a proxy host needs `--noproxy '*'`, or loopback calls get hijacked.
- Native tools get no MSYS path translation: write temp JSON under
  `$LOCALAPPDATA/Temp/...` and pass `cygpath -w` output to python, never `/tmp`.
- `/rest/db/status` and `/rest/db/completion` on a six-figure-file folder can
  take 30–60 s each; give `curl -m` a generous budget, keep probe sleeps short,
  and expect a batched loop to blow a 180 s shell timeout. Query once and compute
  in Python instead of re-querying per row.
- The `events=` query filter is unreliable; fetch `since`/`limit` and filter in
  code.
- Two `syncthing.exe` processes on Windows is normal (wrapper plus child); do not
  read it as a stuck instance.
