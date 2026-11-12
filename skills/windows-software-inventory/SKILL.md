---
name: windows-software-inventory
description: Use when finding or uninstalling Windows software.
version: 0.1.0
author: everxys, Hermes Agent
license: MIT
platforms: [windows]
metadata:
  hermes:
    tags: [windows, paths, inventory, uninstall, mise, winget]
    related_skills: [hermes-agent]
---

The user runs a Windows host and does not want the agent sweeping the disk for
paths on every request. The work is: locate -> record -> (sometimes) uninstall.
This skill is deliberately host-specific: the index below is the one place path
facts live, so the machine-local path in it is the point, not an oversight.

## When to Use

- The user asks where a tool, CLI or application is installed on this machine.
- The user wants something uninstalled, or asks what to back up before it is.
- A path is needed and the index does not already name it.
- Don't use for: choosing between tools (that is the tool's own skill), or for
  any non-Windows host.

## The index is the deliverable

- One markdown index, shipped inside this skill at `references/software-paths.md`
  and read with `skill_view(name='windows-software-inventory',
  file_path='references/software-paths.md')` (a memory entry only points here;
  the host path such an entry names can be stale after a reinstall or move —
  always load the index through `skill_view`, not by path).
  Read it FIRST. Scan the disk only for what it does not cover, then add what you
  found.
- The index lives and dies with this skill — it is not a file elsewhere on the
  host, so update it by editing this skill's reference file, not a host path.
- Propose additions and let the user approve before writing them in. They review
  path facts before those facts become the agent's basis.
- **HARD RULE — a tool the index mentions that gets uninstalled is erased from the
  skill in the same pass, not annotated.** Delete its numbered section, its lines in the
  shared lists (`global packages`, `global bin`, "Other CLIs on PATH", "notable installed
  pkgs"), the host/pointer lines that name it, the cross-references pointing at its
  section, and any other section that exists only because of it. Renumber the sections
  that follow. An "uninstalled 2026-..-.." tombstone left in place is still a stale entry:
  the index lists what exists on the host now. Only if the user explicitly asks for the
  history does a single line in the Removed section survive.
  This applies to every uninstall, including one the user did outside this session —
  when they say "X is gone", check the skill for X and remove it before anything else.
- Record the shim AND the real binary, and mark which directories are on PATH.
- Record the commands the user will ask for again, not just paths. "Where is it"
  is often only the first half of the request; the other half is a query the
  tool answers (quota, status, backup, what to back up). The CLI's `--help` is
  the  fastest source, and a long help listing often names a local HTTP endpoint
  as well as the subcommands.
- **Adding one entry invalidates the aggregates around it.** A new tool shifts
  more than its own section: package counts, "notable installed packages"
  lists, and the version stamped on anything you happened to check on the way.
  Re-derive each count from the source that owns it (`ls ...\WinGet\Packages`,
  `winget list`) rather than editing the previous number, then read the
  neighbouring sections back — that pass is what surfaces an install nobody
  recorded or a version several releases past what the index claims.
- **A winget app can be several packages.** Record the companions that change
  behaviour (`yt-dlp.yt-dlp` plus `yt-dlp.FFmpeg` for format merging) with their
  own paths and their own upgrade command; `winget upgrade <one id>` leaves them
  on different versions.
- **A multi-account switcher is recorded by its switch commands, not its
  binary.** For a tool that flips which account an agent CLI runs as, record the
  exact invocations, which profile is active plus the read-only query that says
  so, and the caveat that the switch rewrites live credentials in place — a
  session that already started keeps the account it started with. Its data
  directory holds those credentials: name it, never print it.

## One index, every agent host

The index is also what the other agent CLIs on this host should read, so keep
exactly one copy and point each host at it rather than pasting path data into
their own memory files.

- **The shared skill root is `~/.agents/skills`, and the hosts on this machine scan it**
  (verify, don't assume): Antigravity via the `entries` list in
  `~/.gemini/config/skills.json`, and the OpenCode harness itself. A skill that lives
  only in a host's own `skills/` dir is invisible to the others — that is the test that a
  move actually landed, so grep the listing for the skill name instead of trusting the
  directory listing.
- **Exactly one install target: `~/.agents/skills`.** No host keeps its own skills
  dir. `~/.gemini/skills` and `~/.claude/skills` were emptied 2026-10-28 and
  `.gemini\config\skills.json` now names that one path; a second copy is a drifting
  revision, never a backup.
- **A skill is on-demand; an always-on rule is not.** The agent sees only a
  skill's name and description until it decides to load it, so a skill alone
  will not stop a blind disk scan. Keep the index in the shared skill and each
  host's always-on slot down to three lines: don't filesystem-search for tools,
  load skill `<name>`.
- **A pointer file dies with its directory and nothing warns you.** Test the
  path exists (`[ -e <pointer> ]`, or read it) before repeating any claim that a
  host reads the index, and correct
  the index header in the same pass: a header saying "two hosts point here"
  records how it was set up, not that it still exists.
- **Move the skill, do not copy it.** `external_dirs` is read-only and a local
  copy of the same skill name shadows the shared one, leaving two revisions
  that drift. Move the directory, then confirm with `skill_view` plus one
  `agy -p` probe before reporting it done.
- Per-host slot paths, the `agy` rule frontmatter and the two verification
  probes: `references/agent-pointer-slots.md`.
- **An existence guard protects nothing once the tool re-creates its home.** A
  mirror script that copies only into directories that already exist stops
  guarding the moment the retired agent runs once and rebuilds its home: every
  later sync quietly fills it again. Guard the executable (`command -v <tool>`)
  or drop the retired host from the target list.
- Who writes copies into each host's skills dir, and how to trace skills that
  reappear in an uninstalled agent's home: `references/agent-skill-mirrors.md`.

## Scan procedure: cheapest and most authoritative first

1. PATH resolution: loop `command -v` over the tool names. This answers most
   questions by itself and separates shims from real binaries.
2. `scripts/scan-paths.sh` runs the whole read-only batch (PATH, mise, winget
   links, GUI app dirs, npm global, cargo bin). Run it instead of retyping.
   `scripts/audit-path-entries.ps1` then audits what it found: every PATH entry
   in both registry hives, whether its directory still exists, duplicates, and
   any DENY ACE that will block a later `rm -rf`.
3. Package managers own their inventories: `mise list`, `npm ls -g --depth=0`,
   `ls ~/.cargo/bin`, `winget list`, and `pip list` from the *specific*
   interpreter you are asking about, never from a bare `pip`.
4. GUI apps: list the parent directories (`C:\Program Files`, `Program Files
   (x86)`, `%LOCALAPPDATA%\Programs`, `%LOCALAPPDATA%`) and read the exact names
   off the listing. Do not guess exe filenames at those roots: the guess costs a
   round trip and the listing costs one.
5. Resolve symlink farms to real paths: `...\Microsoft\WinGet\Links\*.exe` are
   symlinks into `...\WinGet\Packages\<pkg>\...`; mise `shims\` are wrapper
   scripts into `...\mise\installs\<tool>\<version>\`. Report both, but the
   real path is the one to use.
6. When a tool shows its data in a GUI, check for the same data over a local
   HTTP endpoint before scraping its JSON cache. A running instance usually
   binds a loopback port - the port is in its settings file or `--help`, or
   `netstat -ano | grep <port>` shows it listening - and
   `curl http://127.0.0.1:<port>/<path>` returns live structure, where the cache
   file may be stale or hold a whole history to sift.

## Pitfalls

- A directory named after a tool is often config, not program: the Syncthing
  directory under `%LOCALAPPDATA%` holds `config.xml` and certs while the exe
  lives under the user's own software folder. Check that an `.exe` is in it
  before calling a directory the install location.
- Do not build candidate paths like `"$dir/$name"` from guessed filenames: with
  a name that does not exist the command prints nothing at all, which reads
  identically to "not installed". List the parent instead.
- `python3` under `%LOCALAPPDATA%\Microsoft\WindowsApps\` is a Store stub, not
  an interpreter. Confirm a python is real (`--version`, and that
  `Lib/site-packages` exists) before presenting it as the user's python. mise
  shims and the host's own bundled tooling usually resolve to the real one.
- Some installs are absent from PATH even though they are installed: a
  `PostgreSQL\<ver>\bin` is not added to PATH by the winget package. Say
  "installed but not on PATH" rather than "not installed".
- MSYS bash mangles `//` flags: `tasklist //FI "IMAGENAME eq x.exe"` fails with
  `Invalid argument/option`. Pipe instead: `tasklist | grep -i x`. `taskkill
  //F //PID <n>` fails the same way, and `cmd //c "taskkill /F /PID <n>"` can
  print only the cmd banner and return success while the process survives. Kill
  with `powershell -NoProfile -Command "Get-Process <name> | Stop-Process
  -Force"` and confirm with a fresh `Get-Process`/`tasklist` — never with the
  call's exit code. A live process is also the usual reason a whole config
  directory refuses to `mv` right after the app was "uninstalled".
- A shim you do not recognize may belong to a different tool than the one being
  removed: `install_tools.bat` lives in the Node install, not in the tool being
  uninstalled. Find the shim's owner in the installs tree before deleting it,
  instead of assuming every unfamiliar name under `shims\` belongs to the tool
  going away.
- MSYS paths are not translated for native tools: `uv pip uninstall --python
  /c/Users/...` fails with `No virtual environment or system Python installation
  found`. Pass the Windows form (`C:/Users/...`) to any native binary. This is a
  different failure from the `//` flag mangling above, with the same cause.
- An application's own uninstall or purge can refuse because installed files no
  longer hash-match its install receipt. That refusal is a safety check doing
  its job: do NOT force the purge, and never rewrite files so they match the
  recorded hashes. Confirm the data store is genuinely empty of user content,
  run the non-purge path, then delete the files the tool itself reports as
  retained.
- **A leftover directory is usually a stub or a download cache, not the
  program.** After an uninstall, `Programs\<Name>` can survive holding a single
  `version` file, and a `<app>-updater` tree can hold hundreds of megabytes of
  installer cache. Size every leftover (`du -sh`) and say which is program,
  which is cache, which is user data. "I already removed it" is a belief, not
  evidence — both directions are common: an app that is gone with gigabytes of
  residue, and a PATH entry pointing at a directory that no longer exists.
- **`Permission denied` on `rm -rf` is not proof of a lock.** An application can
  leave an explicit DENY ACE (`icacls <dir>` showing `(DENY)(DE,DC)` for the
  owning user, inheriting down the tree) that blocks deletion while the file
  still opens exclusively for reading. Tell the two apart before reporting a
  lock: an exclusive `[System.IO.File]::Open(path,'Open','ReadWrite','None')`
  that SUCCEEDS under a refusal means ACL, not handle.  Recipe:
  `references/system-state-surgery.md`.
- **Windows keeps its own record of an app long after the uninstaller is done,
  and that record is also an ownership oracle.** `reg query "HKCU\Software" /s
  /f "<app>"` finds what no uninstaller touches: MuiCache values (exe path ->
  FriendlyAppName + ApplicationCompany), AppListBackup app/tile entries,
  CloudStore `...$appmetadata$<name>` keys, and Compatibility Assistant Store
  records. When a leftover's own name proves nothing - `%TEMP%\~nsu2.tmp\Un.exe`
  - the MuiCache value naming that exact path is what attributes it. All of
  these are caches Windows rebuilds, so say the visible effect is nil, then
  delete; the `Uninstall` key is only one of several stores, so a hive-wide
  search is the only reliable sweep.
- **Non-standard files under `.git/` are another tool's state, not git's.** Git
  cannot see them, they never travel with clone or push, and `git status` stays
  clean — which is exactly why tools park per-repo state there. Claim ownership
  before deleting any: `.git/gitbutler` and `.git/gk` are GitButler's and
  GitKraken's own ledgers, not litter. A 40-hex file is usually a commit marker;
  `git cat-file -t <sha>` says whether that object still exists.
- **Never call a leftover an orphan from its directory name.** Deriving an app
  name from `<app>-updater` mis-attributes every app whose install directory has
  a space or a vendor prefix (`@somevendordesktop-updater` belongs to
  `Programs\Vendor App`). Treat a name-derived list as candidates only, and
  confirm each against the uninstall registry (HKCU, HKLM and WOW6432Node),
  `winget list`, and the app roots together before proposing a deletion.
- **Remove a WSL distribution with `wsl --unregister <Distro>`, never by
  deleting its files.** WSL mounts the Windows drives at `/mnt/c`, so an `rm -rf`
  run inside a distribution against anything resolving under `/mnt/c` destroys
  real Windows files with no recycle bin — a directory symlink is enough to make
  a plausible-looking `~/...` path do it. `--unregister` acts on the
  distribution's own vhdx from the Windows side and cannot reach `/mnt/c`. Bare
  `wsl --uninstall` removes WSL itself; only the `-d <Distro>` form is scoped to
  a distribution. A distro's Linux home dies with it, so check for **untracked**
  files as well as unpushed commits before removing one — untracked files exist
  nowhere else.
- **A shim resolving is not the tool existing.** `npm uninstall -g <pkg>` takes
  the package out but mise keeps `shims\<tool>` AND `shims\<tool>.cmd`, so
  `which <tool>` still answers and only `--version` reveals the breakage. Move
  both shim files, then re-check `which` instead of trusting the uninstall's
  summary line.
- **One `~/.<vendor>` directory rarely holds one product.** Enumerate its
  subdirectories and attribute each to a product before moving or deleting the
  parent — a single vendor dir commonly carries a CLI's config, an IDE's models
  and a sibling CLI's data at once. Removing the parent is often still the right
  call; say which products travel with it before you do.
- **A cloud-placeholder leftover can refuse every delete path while holding no
  files.** Count first (`find <dir> -type f | wc -l`); a zero-file OneDrive
  placeholder is not worth fighting — name it for manual removal with sync
  paused and move on.
- **Never size and delete in the same call.** `du -sh` over a multi-gigabyte
  tree of many small files can burn the entire foreground timeout (exit 124)
  and swallow the destructive command queued behind it, so nothing is deleted
  but the transcript reads as a completed step. Sum the per-item sizes the move
  helper already printed, and give a purge its own call with a raised timeout.
- **Recording a path is itself a place to corrupt it.** In a JSON tool argument
  `\r`, `\n`, `\t`, `\b`, `\f` inside `C:\...\rules\...` decode to control
  characters, so the path lands split mid-token while the write reports success.
  Write `C:/...` or doubled backslashes, and read the paragraph back after any
  edit that adds a long path — then check that path with `[ -e ]` before
  believing it. Details: `references/agent-pointer-slots.md`.

## Uninstalling

0. **HARD RULE — find the installer first, then uninstall with it.** Never begin by
   deleting files or folders. Establish how the program got onto this host, then run
   that owner's own uninstall command; the files it leaves behind are cleanup, not the
   uninstall itself. Deleting an install dir by hand is a bug, not a shortcut.
   - Check, in this order: `winget list` + the Uninstall registry keys (HKCU, HKLM and
     WOW6432Node) → `mise list` → npm (`npm ls -g --depth=0` **for every prefix**, see
     below) → `pip list` from the owning interpreter → `cargo install --list` →
     `Get-AppxPackage` for MSIX/Store apps → the vendor's own uninstaller if none of
     those own it.
   - **A package manager can have more than one prefix.** `npm ls -g` only reports the
     prefix the current `.npmrc` points at; a copy installed before `prefix=` changed
     sits under the old prefix (here: the mise node dir). List that tree directly and,
     when it holds the package, uninstall with
     `npm uninstall -g <pkg> --prefix <old-prefix>` — that is still the owner's own
     uninstaller, unlike deleting `node_modules/<pkg>`.
   - Say out loud which installer was found and which command removes it before running
     anything destructive. If no owner exists, only then propose deleting paths.
1. After the owner's uninstall, identify what is left: a mise-managed tool has a shim,
   an install dir and a `config.toml` entry; a winget-installed one has a Links
   symlink and a Packages dir. Leftovers are removed once the owner is done.
2. mise: `mise unuse -g -y "<tool>"` removes the config request AND prunes the
   installation and shim. `mise uninstall` alone leaves the config entry behind;
   only `mise uninstall` has `--dry-run`, `mise unuse` has none. Back up the
   global config before the call.
3. Hermes plugin: `hermes plugins uninstall <name>` removes the wrapper dir and
   clears `plugins.enabled`. When the plugin was also the external memory
   provider, run `hermes memory off` as well - the uninstall leaves
   `memory.provider` set. Then take the package out of the host's own runtime
   venv: `uv pip uninstall --python <venv>/Scripts/python.exe <dist-name>`. Do
   the host-level removal FIRST: a plugin's own uninstall command run afterwards
   reports `files_removed: []` because the wrapper files are already gone, which
   is expected, not a failure.
4. Check every leftover once the package manager is done: the installs dir, its
   download cache, the shims, and the tool's own dot-directory in the home dir.
   The package manager never removes the last one. For a plugin, that set also
   includes its data dir, its `.<name>-install-receipt.json` under the instance
   root, and the skills it installed - including the copies it mirrored into
   every other host's own skills dir.
5. Separate program from user data and size both (`du -sh`). Confirm no process
   is holding the tool, and ASK before deleting user data (session DBs, logs,
   caches) - that deletion is irreversible and removing the program is usually
   the whole request. Read the app's own state store first (open its sqlite DB
   read-only and count rows, or read its JSON) so the question you ask is backed
   by an inventory: "it held no user content" is a fact, "it probably held
   none" is a guess. Note that a stale lock file names a pid and the operation
   it died in - check the pid is gone, then delete the lock rather than treating
   it as a live process.
6. Verify by re-reading, never by the exit code: the command resolves to
   nothing, no shims remain, the config no longer names the tool, a bounded
   `search_files (target='files')` sweep for its name returns nothing, and every
   old path answers `[ -e <path> ]` false. Where a meta-tool enumerated the apps
   in the first place, re-run it: its own list shrinking to the expected set is
   independent confirmation that its registry pointed at the configs you
   removed.
7. Report bytes freed, split program vs data, and name any backup file you
   created - a rollback backup of a removed tool is dead weight the user may
   want gone too. Measure it rather than inferring it from the tree
   (`powershell -NoProfile -Command "[math]::Round((Get-PSDrive C).Free/1GB,1)"`
   before and after). Quarantine-then-purge usually releases far less than the
   quarantine's size because the uninstaller already freed the bulk, so state
   the measured delta and say why the two numbers differ - never present the
   moved directory size as the space reclaimed.

## Sweeping several apps at once: quarantine, not delete

When the request names several products in one breath ("remove all the
leftovers of X, Y and Z"), the unit of decision is scope, not the file. Two
questions, both plain language, each with its visible consequence attached:

1. **Scope.** List every path found with `du -sh`, split into program / cache /
   config-and-user-data, then state what stops working if the still-installed
   CLIs go too: the shell command disappears, and any skill or agent registry
   pointing at that config path goes silent with it. Ask whether they want
   everything including the working CLIs, only the genuinely dead residue, or
   their own list.
2. **Deletion mode.** Default to the quarantine move: `mv` into
   `%LOCALAPPDATA%\hermes\cache\trash-<date>-<topic>\` is instant on the same
   volume, fully revertible, and its restore command is one line. Report the
   total and say plainly that the bytes are only really freed when the
   quarantine is purged, then offer the purge as a separate follow-up.

Order of operations, the `mvx` helper, the full verification battery and the
restore-command shape: `references/app-residue-sweep.md`.

## Reporting

- Group the answer by the user's own list, in their order.
- Bullets, never tables.
- Give a full path for anything they will run, and flag what is not on PATH.
- State the version you actually read, and say plainly when something is
  installed-but-unmapped rather than implying it works.
- A monitoring or quota tool prints cached numbers as readily as live ones.
  Surface its own timestamp or staleness marker, and confirm it can still reach
  the source: a signed-out account keeps serving its last cached value, which
  reads as a fresh answer unless you look for the marker.
- Do not create backup copies unless the user asks for one. Prove a surgical
  edit with a fingerprint instead — line or byte count plus the one changed
  line, before and after — so they can see nothing else moved.
- When a later check shows an earlier claim was too broad, correct it explicitly
  in the same message as the new finding: retract the specific sentence rather
  than quietly dropping it.
