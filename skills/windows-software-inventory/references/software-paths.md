# Windows software & tool path index — host `everx` (C:\Users\everx)

Verified 2026-10-16. **Check here before running any global path search.**
`$H` = `C:\Users\everx` = `/c/Users/everx`

> **Pointers, kept in each agent host's always-on slot** (they store **no path data**,
> only the pointer — everything else stays in this file):
> - Antigravity — `C:\Users\everx\.gemini\config
ules\software-paths.md`, recreated
>   (frontmatter `trigger: always_on`) and verified: an `agy -p` probe answered citing that
>   rule and this index, with no disk search.
> This file is the shared skill `~/.agents/skills/windows-software-inventory/references/software-paths.md`,
> and the hosts on this machine (`agy` via `~/.gemini/config/skills.json`, and the
> OpenCode harness itself) discover skills from `~/.agents/skills`. One copy, no drift.

## 1. mise
- binary (real): `C:\Users\everx\AppData\Local\Microsoft\WinGet\Packages\jdx.mise_Microsoft.Winget.Source_8wekyb3d8bbwe\mise\bin\mise.exe`
- winget shim: `C:\Users\everx\AppData\Local\Microsoft\WinGet\Links\mise.exe`
- shims dir (on PATH): `C:\Users\everx\AppData\Local\mise\shims`
- installs root: `C:\Users\everx\AppData\Local\mise\installs`
- config: `C:\Users\everx\.config\mise\config.toml`

## 2. mise-managed tools
| tool | version | path |
|---|---|---|
| node | 26.7.0 | `C:\Users\everx\AppData\Local\mise\installs\node\26.7.0` (bin = same dir) |
| python | 3.14.7 (global) | `...\mise\installs\python\3.14.7` (python.exe, python3.exe, pythonw.exe) |
| python | 3.12.14 | `...\mise\installs\python\3.12.14` |
| python | 3.13.15 | `...\mise\installs\python\3.13.15` |
| java (Temurin 17.0.2) | 17.0.2 | `...\mise\installs\java\17.0.2` — `JAVA_HOME` set to this |
| bitwarden CLI (`bw`) | 2026.9.1 | `...\mise\installs\bitwarden\2026.9.1` |

mise shims available: `node npm npx corepack pnpm pnpx yarn yarnpkg python python3 pythonw pip pip3 java javac jar jshell keytool jaccess* jabswitch mobiunpack pymupdf pypandoc git-filter-repo normalizer bw gemini install_tools` (no `codex`, `codex-auth` or `opencode` shims as of 2026-10-20)

## 3. git / gh
- git (PATH, bash): `/mingw64/bin/git` (git-bash bundled, real `C:\Program Files\Git\mingw64\bin`)
- git (winget Git.Git 2.55.0.5, PATH for cmd/PowerShell): `C:\Users\everx\software\Git\cmd\git.exe`
- gh (GitHub CLI 2.102.0): `C:\Program Files\GitHub CLI\gh.exe`

## 4. Clash Verge Rev (2.5.8)
- app: `C:\Program Files\Clash Verge\clash-verge.exe`
- core: `C:\Program Files\Clash Verge\verge-mihomo.exe` (+ `verge-mihomo-alpha.exe`)
- service: `C:\Program Files\Clash Verge\resources\clash-verge-service.exe`
- data: `C:\Users\everx\AppData\Roaming\io.github.clash-verge-rev.clash-verge-rev`

## 5. Python & python-installed tools
**mise python 3.14.7** (the `python`/`python3` on PATH via shims):
- exe: `C:\Users\everx\AppData\Local\mise\installs\python\3.14.7\python.exe`
- site-packages: `...\python\3.14.7\Lib\site-packages`
- scripts: `...\python\3.14.7\Scripts\` → `git-filter-repo.exe mobiunpack.exe normalizer.exe pymupdf.exe pypandoc.exe`
- packages: charset-normalizer 3.5.1, colorama 0.4.6, EbookLib 0.20, git-filter-repo 2.47.0, loguru 0.7.3, lxml 6.1.3, mobi 0.4.1, pillow 12.3.0, pip 26.2.1, pymupdf 1.28.2, pypandoc 1.17, reportlab 5.0.1, six 1.17.0, standard-imghdr 3.13.0, win32_setctime 1.2.0

Other pythons (not the PATH one):
- Hermes bundled & venv: uninstalled 2026-11-06
- uv-managed: `C:\Users\everx\.local\bin\python3.11.exe`; uv: `C:\Users\everx\.local\bin\uv.exe`, `uvx.exe`
- Windows Store stub: `C:\Users\everx\AppData\Local\Microsoft\WindowsApps\python3.exe` (NOT a real python)

## 6. Node / npm / npx + global packages
- node: `C:\Users\everx\AppData\Local\mise\installs\node\26.7.0\node.exe`
- npm/npx: `...\node\26.7.0\npm.cmd`, `npx.cmd` (npm prefix = `C:\Users\everx\AppData\Local\mise\installs\node\26.7.0`)
- global packages: `@google/gemini-cli@0.64.0`, `corepack@0.36.0`, `npm@12.2.1` (`@loongphy/codex-auth` and `opencode-ai` were removed before 2026-10-20)
- global bin: `...\node\26.7.0\{gemini,corepack,npm,npx,pnpm,pnpx,yarn,yarnpkg}.cmd` (`codex-auth` and `opencode` shims are gone as of 2026-10-20)
- module dir: `...\node\26.7.0\node_modules\{@google,@loongphy,@earendil-works,opencode-ai,npm,corepack}`
- caches: `C:\Users\everx\AppData\Local\{npm-cache,pnpm,pnpm-cache,pnpm-state,Yarn}`

## 7. Chrome
- `C:\Program Files\Google\Chrome\Application\chrome.exe` (156.0.8078.12, versioned dir `...\Application\156.0.8078.12`)

## 8. Syncthing
- `C:\Users\everx\software\syncthing\syncthing.exe` (running instance was v2.1.6 windows-amd64)
- config/state: `C:\Users\everx\AppData\Local\Syncthing\` (config.xml, cert.pem, key.pem, syncthing.log, index-v2)
- **live API**: `http://127.0.0.1:8384`, `tls=false`; the key is `<apikey>` in config.xml. Always
  `curl --noproxy '*'` — the Clash/Mihomo TUN otherwise swallows loopback calls.
- fleet: `everxys-pc` = this host, LAN `192.168.0.241` (Wi-Fi; the Ethernet adapter is disconnected),
  `everxys-nas` `192.168.0.2`, `everxys-fold` `192.168.0.3`, `everxys-ace` = Android phone (PJE110)
  `192.168.0.9`. Folders: `~/important` and `~/media`, both send&receive.
- Sync-state surgery (whichever device "shows N%", slow transfers, conflict storms, peer resets) is a
  different job from path lookup: follow the `syncthing-sync-diagnosis` skill.

## 9. Hermes Agent — uninstalled and swept clean 2026-11-06
- Was at %LOCALAPPDATA%\hermes (5.3 GB); uninstalled via hermes uninstall --full and swept clean on 2026-11-06.
- No hermes binary on PATH; ~/.hermes junction, ~/.basic-memory and ~/hermes-memory removed. See §Removed.

## 10. Antigravity (Google) — GUI gone, `agy` CLI remains
- CLI `agy`: `C:\Users\everx\AppData\Local\agy\bin\agy.exe` — 1.5.4, on PATH (version read 2026-11-12).
  ⚠️ the older `C:\Users\everx\.gemini\bin\agy.exe` no longer exists; do not use it.
- its login is a single shared Windows Credential Manager generic credential `gemini:antigravity`
  (`cmdkey /list` shows the target; it is the same slot for every account, so only one Google account
  can be live at a time). `~/.gemini/antigravity` holds only skills; `~/.gemini/antigravity-cli` holds logs,
  presence locks and the updater; `%LOCALAPPDATA%\agy` holds only `agy.exe` — **no auth file anywhere**,
  the credential store is the sole identity store.
- live account **2026-11-12: `everxys00@gmail.com`**, verified by decoding the `gemini:antigravity` blob
  (560 B, JWT/plain `email` claim) — do NOT infer the account from aisw-era status text.
  The running `agy` process (started 2026-11-10 15:45:57) logged `authenticated successfully as
  everxys00@gmail.com` at 15:45:58, consistent with that blob.
- GUI **not installed** (verified 2026-10-26): no Uninstall registry entry, nothing under
  `AppData\Local\Programs`, no Start Menu shortcut, and no `antigravity` command on PATH.
  The old `...\AppData\Local\Programs\antigravity\Antigravity.exe` and `...\AppData\Local\antigravity-updater` are both gone.
- orphaned state left behind, nothing on this host reads it while the GUI is uninstalled:
  `C:\Users\everx\AppData\Roaming\Antigravity IDE` (~35 MB Electron cache/logs/preferences),
  `C:\Users\everx\AppData\Local\antigravity\staging` (no payload).
- `.gemini\bin` is gone. `.gemini\skills` was emptied 2026-10-28: skills install only
  into `~/.agents/skills`, which `agy` reads through the single `entries` path in
  `.gemini\config\skills.json`. Do not recreate a per-host skills dir.

## 11. ffmpeg (Gyan.FFmpeg 9.0.2)
- real: `C:\Users\everx\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\{ffmpeg,ffplay,ffprobe}.exe`
- shim: `C:\Users\everx\AppData\Local\Microsoft\WinGet\Links\{ffmpeg,ffplay,ffprobe}.exe`
- also bundled: Hermes copy uninstalled 2026-11-06

## 12. cloudflared (2026.10.1)
- `C:\Program Files (x86)\cloudflared\cloudflared.exe` (on PATH)

## 13. fd (sharkdp.fd 10.5.0)
- real: `C:\Users\everx\AppData\Local\Microsoft\WinGet\Packages\sharkdp.fd_Microsoft.Winget.Source_8wekyb3d8bbwe\fd-v10.5.0-x86_64-pc-windows-msvc\fd.exe`
- shim: `C:\Users\everx\AppData\Local\Microsoft\WinGet\Links\fd.exe` (no `fdfind`)

## 14. Rust / rustup / cargo
- toolchain: `stable-x86_64-pc-windows-msvc` (active/default), `CARGO_HOME`=`C:\Users\everx\.cargo`, `RUSTUP_HOME`=`C:\Users\everx\.rustup`
- `C:\Users\everx\.cargo\bin\` → cargo.exe, rustc.exe, rustup.exe, rustdoc, rustfmt, cargo-clippy, clippy-driver, rust-analyzer, rls, cargo-miri, cargo-fmt, **cargo-binstall**, **cargo-install-update** (+ cargo-install-update-config), rust-gdb, rust-gdbgui, rust-lldb
- extra targets in rustup: rust-std for aarch64-linux-android, armv7-linux-androideabi, i686-linux-android, x86_64-linux-android
- no user-installed binaries beyond the toolchain; registry: `C:\Users\everx\.cargo\registry` (`cache/src/index`); binstall state: `C:\Users\everx\.cargo\binstall`

## 15. ripgrep (BurntSushi.ripgrep.MSVC 15.2.0)
- real: `C:\Users\everx\AppData\Local\Microsoft\WinGet\Packages\BurntSushi.ripgrep.MSVC_Microsoft.Winget.Source_8wekyb3d8bbwe\ripgrep-15.2.0-x86_64-pc-windows-msvc\rg.exe`
- shim: `C:\Users\everx\AppData\Local\Microsoft\WinGet\Links\rg.exe`
- also bundled: Hermes copy uninstalled 2026-11-06
- bundled in Antigravity: `C:\Users\everx\AppData\Local\antigravity\bin\rg_embedded-*.exe`

## 16. winget
- exe: `C:\Users\everx\AppData\Local\Microsoft\WindowsApps\winget.exe`
- links dir: `C:\Users\everx\AppData\Local\Microsoft\WinGet\Links`
- packages dir: `C:\Users\everx\AppData\Local\Microsoft\WinGet\Packages` (8 winget-native installs: Gyan.FFmpeg, sharkdp.fd, BurntSushi.ripgrep.MSVC, jdx.mise, Gitleaks.Gitleaks,
  DenoLand.Deno, yt-dlp.yt-dlp, yt-dlp.FFmpeg)
- GUI: UniGetUI `C:\Users\everx\AppData\Local\Programs\...` / `C:\Users\everx\software\UniGetUI`
- notable installed pkgs: Antigravity, Bandizip, calibre, Clash Verge, cloudflared, Ditto, EmEditor, Everything, fd, FFmpeg, FluxDown, Git, GitHub CLI, Gitleaks, HandBrake, ManicTime, MobaXterm, mpv.net, Obsidian, OBS Studio, Pandoc, PostgreSQL 18, PowerShell 7.6.7, Readest, Recordly, ripgrep, Rustup, Steam, Telegram, UniGetUI, VLC, VS Code, Windows Terminal, WSL, 剪映, 夸克网盘, 百度网盘, 网易云音乐, 腾讯会议, etc.

## 17. PostgreSQL 18 (18.6-5)
- root: `C:\Program Files\PostgreSQL\18`
- bin: `C:\Program Files\PostgreSQL\18\bin\` → `psql.exe postgres.exe pg_ctl.exe initdb.exe createdb.exe createuser.exe dropdb.exe dropuser.exe pg_dump.exe pg_dumpall.exe pg_restore.exe pg_basebackup.exe pg_isready.exe pg_amcheck.exe pg_checksums.exe pg_config.exe pg_controldata.exe pg_createsubscriber.exe pg_receivewal.exe pg_recvlogical.exe pg_resetwal.exe pg_rewind.exe pg_upgrade.exe pg_verifybackup.exe pg_waldump.exe pg_walsummary.exe pgbench.exe reindexdb.exe vacuumdb.exe vacuumlo.exe clusterdb.exe ecpg.exe oid2name.exe stackbuilder.exe`
- data dir: `C:\Program Files\PostgreSQL\18\data`
- **`bin` is NOT on PATH** — call by full path or add it.
- lib: `C:\Program Files\PostgreSQL\18\lib`; include: `...\18\include`

## 18. PowerShell 7
- `C:\Program Files\PowerShell\7\pwsh.exe` (7.6.7, Microsoft.PowerShell winget pkg)
- Windows PowerShell 5.1 stays at `C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe`

## 19. Magpie — one place to pick every agent's model + see every quota
- **binary** (not on PATH; has a space-free name winner): `C:\Users\everx\software\Magpie\magpie-windows-amd64.exe`
  (v0.1.3814, read 2026-11-12)
  - stray copy also at `C:\Users\everx\AppData\Roaming\magpie-windows-amd64.exe`
- **config/data**: `C:\Users\everx\.config\magpie\`
  - `quotas.json` + `quota-history.json` (last asked values), `logins.json` (sign-ins), `providers.json`, `settings.json`, `usage.jsonl`
  - app data: `C:\Users\everx\AppData\Local\Magpie\config`
- **gateway**: listens on `127.0.0.1:3425`

### Quota / usage commands (this is what "看额度" means)
```bash
M="/c/Users/everx/software/Magpie/magpie-windows-amd64.exe"   # or C:\Users\everx\software\Magpie\magpie-windows-amd64.exe
"$M" quota                  # ← MAIN: every subscription/plan/key, % used + when it resets, asked of the vendors now
"$M" quota --json           # machine-readable (scripts/agents)
"$M" quota codex            # one provider only
"$M" quota history --days 7 # history
"$M" quota wait <provider>  # block until it resets
"$M" accounts               # accounts magpie knows: plan + allowance used + reset
"$M" accounts --json        # structured
"$M" accounts antigravity   # one agent
"$M" ls                     # every detected agent + its current model/effort + which file it edits
```
- HTTP equivalent (no CLI needed): `curl http://127.0.0.1:3425/v1/magpie/quotas` → `{"data":[{provider,plan,user,windows:[{name,used,remaining,resetsAt}]}]}`
  (another machine only while magpie is shared on the LAN, key as `Authorization: Bearer *** x-api-key`)
- Output legend: `%` = how much of that window is **used**; `↻` = when it starts again.
- Agents tracked here: `codex`, `commandcode-plan`, `antigravity`, `gemini`, `opencode-zen-free` (also Claude Code,
  Antigravity CLI, OpenCode, Zed, VS Code, DeepSeek Harness, Hermes Agent, WorkBuddy, Codex/OpenCode in WSL).

### Other magpie entry points
- `magpie` (window + menu-bar icon) · `magpie tray` · `magpie panel` · `magpie tui` · `magpie web [--addr]`
- `magpie providers` / `presets` / `provider add <preset> <key>` · `magpie models [agent]` · `magpie groups`
- `magpie save|use|profiles|rm <name>` (profiles) · `magpie backup` / `restore` / `webdav` / `s3` / `github` (sync)
- `magpie library [sync|instructions|mcp|skill]` · `magpie search` · `magpie visible`
- `magpie <agent> <model>` sets an agent's model; `magpie <agent> <field> <value>` another field

## 20. Development projects — `C:\Users\everx\dev`
Every project of the user's lives under this one root. Check here before asking where a project is.
`~/dev\README.md` is a 14-byte placeholder, not a real index.

| path | what it is | git |
|---|---|---|
| `~\dev\clash\vps.yaml` | **Clash Verge Rev config source** for the user's own VPS. 913 lines: `mixed-port: 7890`, `proxies`, `proxy-groups`, `rules`. This is the file the user edits; Clash Verge's imported working copy is `~\AppData\Roaming\io.github.clash-verge-rev.clash-verge-rev\profiles\*.yaml` (its active one had `fake-ip-range: 198.18.0.1/16`). ⚠️ **Holds proxy credentials — never print, paste or echo its contents.** | no |
| `~\dev\common` | Scratch space for un-launched work: testing scripts and one-off operations before something becomes a project. Was the `project_root` in the Scope Recall install receipt (that plugin is uninstalled). Empty as of 2026-10-28 (cleared by the user); previously held `AGENTS.md`, `TikTokDownloader`, `zen-free-models`, and `SKILL/` + `scripts/sync-skill.ps1` | no |
| `~\dev\content-creator` | Planned 自媒体 / self-media project; content-publishing scripts will land here. Earliest stage (only `README.md`) | main |
| `~\dev\healthy` | Health-management web app — pnpm monorepo (`apps/` + `packages/`, `biome.json`, `CONTEXT.md`) | master |
| `~\dev\healthy-landing` | Marketing site / 官网 for `healthy` — Next.js + pnpm + ESLint | main |
| `~\dev\navvo` | Item-management app — **docs stage only** (`navvo-docs/`, `project-guide/`, `IDEAS.md`, `TODO.md`, `UPDATE.md`, `AGENTS.md`) | main |
| `~\dev\toolbox` | Personal vibe-coding small tools, many single-file scripts (`_*.py`) | main |

`~\dev` also contains `README.md` (placeholder). No other project directories exist there.

## 21. Android / Android Studio — verified 2026-10-17
Env vars already set: `ANDROID_HOME` = `ANDROID_SDK_ROOT` = `C:\Users\everx\AppData\Local\Android\Sdk`,
`NDK_HOME` = `...\Sdk\ndk\30.0.16248370`, `JAVA_HOME` = mise Temurin 17.0.2 (§2). Studio itself needs
Java 25 and ships its own `jbr`, so both JDKs exist for different consumers.
⚠️ **Nothing Android is on PATH** — `adb`, `fastboot`, `emulator`, `sdkmanager`, `avdmanager` all
resolve to nothing. Use the full paths below (or add the dirs).

### Studio itself
- app / launcher: `C:\Program Files\Android\Android Studio\bin\studio64.exe` (AI-262.9437.185.2621.16467767 = 2026.2.1, see `build.txt`)
- bundled JDK (Java 25, also the `keytool` to reach for): `C:\Program Files\Android\Android Studio\jbr\bin\{java,javac,keytool,jarsigner}.exe`
- uninstaller: `C:\Program Files\Android\Android Studio\uninstall.exe` (install tree is 3.4G)
- user data (only when a Studio-side problem needs it): `C:\Users\everx\AppData\Local\Google\AndroidStudio2026.2.1` (log/, caches, projects), config `...\AppData\Roaming\Google\AndroidStudio2026.2.1`

### SDK command-line entry points
- adb: `C:\Users\everx\AppData\Local\Android\Sdk\platform-tools\adb.exe` → 1.0.41 (37.0.1-15733141); `devices`, `install -r`, `logcat`, `shell`, `push/pull`
- fastboot, sqlite3, etc1tool, hprof-conv: same `platform-tools\` dir
- emulator: `...\Sdk\emulator\emulator.exe` → 37.2.12.0; `-list-avds`, `-avd Medium_Phone_API_37.0`
- **no `cmdline-tools`** → `sdkmanager` / `avdmanager` do not exist yet; add "Android SDK Command-line Tools" in Studio's SDK Manager before managing SDK packages from a shell

### Installed SDK packages (6.5G total)
- platforms (compile targets): `...\Sdk\platforms\android-36` (API 36, ext 17), `...\platforms\android-37.0` (API 37.0, ext 22)
- build-tools: `...\Sdk\build-tools\36.0.0\` → `aapt2.exe aapt.exe apksigner.bat zipalign.exe d8.bat dexdump.exe`
- sources: `...\Sdk\sources\android-37.0` (only 37.0)
- ndk: `...\Sdk\ndk\30.0.16248370`; system-image: only `...\Sdk\system-images\android-37.0\google_apis_playstore\x86_64`
- licenses: `...\Sdk\licenses\android-sdk-license`

### Emulator instance (AVD)
- `C:\Users\everx\.android\avd\Medium_Phone.avd` + `Medium_Phone_API_37.0.ini` (target android-37.0)
- x86_64, `google_apis_playstore`, PlayStore enabled, data partition 10G, `hw.device.name=medium_phone`, 513M on disk
- `C:\Users\everx\.android\debug.keystore` = default debug signing key; `.android\adbkey(.pub)` = adb auth

### Gradle (Android builds go through this, not through PATH)
- downloaded dist (run it directly for a one-off build; projects use their own `gradlew`):
  `C:\Users\everx\.gradle\wrapper\dists\gradle-9.6.1-bin\4ticwg1pgcbps2hj28r8so764\gradle-9.6.1\bin\gradle.bat`
- dependency/artifact cache read by offline builds: `C:\Users\everx\.gradle\caches` (1.3G); total `~/.gradle` 1.5G
- there is no gradle on PATH and no mise shim for it
- Rust android targets for NDK-style builds: see §14.

## 22. yt-dlp (2026.10.26) — winget, with its own ffmpeg
- real: `C:\Users\everx\AppData\Local\Microsoft\WinGet\Packages\yt-dlp.yt-dlp_Microsoft.Winget.Source_8wekyb3d8bbwe\yt-dlp.exe`
- shim (on PATH): `C:\Users\everx\AppData\Local\Microsoft\WinGet\Links\yt-dlp.exe` -> the file above;
  `yt-dlp --version` -> 2026.10.26
- companion package `yt-dlp.FFmpeg` (N-127043-g5a54fcf75e-20260930) ->
  `...\Packages\yt-dlp.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-N-127043-g5a54fcf75e-win64-gpl\bin\{ffmpeg,ffplay,ffprobe}.exe`
  (so format merging works even if the main ffmpeg on PATH is a different build — see §11)
- update: `winget upgrade yt-dlp.yt-dlp` (and `yt-dlp.FFmpeg` separately)

## 23. Firefox (155.0.1) — MSI/ARP install, NOT on PATH
- exe: `C:\Program Files\Mozilla Firefox\firefox.exe` (155.0.1, BuildID `20260903215306`; Sep 2026 build).
  `firefox` does **not** resolve on PATH - call the full path.
- install kind: **MSI + ARP entry**, not a winget-native package. `winget list` shows it as
  `ARP\Machine\X64\Mozilla Firefox`, so `winget upgrade` will not manage it; Firefox updates itself
  through the Mozilla Maintenance Service (`MozillaMaintenance`, StartType Manual, usually Stopped)
  at `C:\Program Files (x86)\Mozilla Maintenance Service\maintenanceservice.exe`.
- same directory: `private_browsing.exe`, `updater.exe`, `crashhelper.exe`, `crashreporter.exe`,
  `default-browser-agent.exe`, and the uninstaller `uninstall\helper.exe`.
- profile & user data: `C:\Users\everx\AppData\Roaming\Mozilla\Firefox\` - `profiles.ini`
  (`default` = `Profiles\jf2nglkc.default`, `default-release` = `Profiles\zsqrrr5r.default-release`,
  the latter is the install default); cache/startupCache under `C:\Users\everx\AppData\Local\Mozilla\Firefox\`.
- driving it from a shell: `firefox.exe --version` prints and exits; for automation use
  `-headless -profile <path>` and note that a normal launch just opens the GUI.
- uninstall: `C:\Program Files\Mozilla Firefox\uninstall\helper.exe` (or Settings > Apps).

## 24. aisw (0.3.11) — reinstalled 2026-11-12, adding accounts for `agy`
- binary: `C:\Users\everx\.cargo\bin\aisw.exe` (2.26 MB, 2026-11-12 10:25; `cargo install aisw`, still
  `aisw 0.3.11` — same build as the copy removed that morning, so every verb below is unchanged).
  `~/.cargo/bin` is on the **user** PATH, so `aisw` resolves in a *newly started* terminal; a shell that
  was already running (or a parent process that predates the install) still says "not recognized" — call
  `C:\Users\everx\.cargo\bin\aisw.exe` there. Do not conclude "not installed" from `Get-Command`.
- data: `C:\Users\everx\.aisw\` — recreated empty on first command: `config.json` (schema v2, every
  `active` and `profiles` entry null), `config.json.lock`. `profiles\`, `backups\`, `switch.lock` appear
  only once something is added/switched. `settings.antigravity.backup_on_switch` defaults to `true` with
  `max_backups: 10`.
- **state as of 2026-11-12 10:30: one stored profile, `antigravity/everxys00`, captured with
  `--from-live`** (file backend, `profiles\antigravity\everxys00\keyring-secret.json` 558→560 B, email claim
  verified as `everxys00@gmail.com`), marked active; `backups\` still empty. The live `agy` login is the same
  account (§10). A second account (`turkey`) was to be added by the user through the OAuth flow — that login
  overwrites the live shared-keyring slot, which is why the `--from-live` snapshot had to come first.
- adding a *new* account is **two steps on this host**, because `agy` 1.5.4 has no `login`/`logout`
  subcommand — those are TUI slash commands, and antigravity auth is 100% the shared live keyring:
  1. `aisw add antigravity <name>` (or just run `agy`) → aisw has no OAuth of its own here; it opens the
     normal `agy` TUI and prints "Complete login in the agy session, then retry 'aisw add antigravity
     <name> --from-live'". Inside that TUI: `/logout` → then `/login` → browser → pick the other Google
     account → `/quit`.
  2. `aisw add antigravity <name> --from-live --set-active` → captures whoever is live now as the profile.
  (`aisw add` without `--from-live` does NOT create a profile for antigravity; it only launches the tool.)
  Useful flags: `--set-active` (switch right after adding), `--from-live` (capture whoever is live now),
  `--yes` (overwrite an existing profile, only with `--from-live`), `--label`, `--api-key`/`--from-env`
  (key-based, not for a Google account), `--credential-backend file|system-keyring`, `--json`.
- other verbs: `aisw list` · `aisw status` · `aisw use antigravity <name>` · `aisw remove antigravity <name>`
  (`--force` needed for the active one) · `aisw backup` · `aisw verify` / `doctor` / `repair` ·
  `aisw uninstall [--remove-data]`.
- ⚠️ never read the current account out of `aisw verify`'s "live tool credentials do not match the recorded
  active profile" — that is a byte compare against a frozen copy and fires on every token refresh; decode
  the `gemini:antigravity` blob or read `agy`'s log instead (§10).

## Other CLIs on PATH (bonus)
- `uv`/`uvx` → `C:\Users\everx\.local\bin\uv.exe`
- cua-driver → `C:\Users\everx\AppData\Local\Programs\Cua\cua-driver\bin`
- VS Code → `C:\Users\everx\software\Microsoft VS Code\bin`
- EmEditor → `C:\Users\everx\AppData\Local\Programs\EmEditor`
- Pandoc → `C:\Program Files\Pandoc`; MobaXterm, Bandizip, Calibre2 also on PATH

## Removed — uninstalled and swept clean, do not hunt for these
- **aisw 0.3.11 — uninstalled 2026-11-12 morning, and its last profile `antigravity/everxys00` deleted with it;
  REINSTALLED the same day at 10:25 — see §24, that is the live entry now.**
  `aisw remove antigravity everxys00 --force` first (everxys00 was the only stored profile; the `everxys`
  profile was already gone before that), then `aisw uninstall --remove-data` deleted `~/.aisw` (config,
  profile credential copies, 10 switch backups), then `cargo uninstall aisw` removed
  `C:\Users\everx\.cargo\bin\aisw.exe`. No shell hook existed, no `AISW_HOME` variable, no `aisw` on either
  PATH. ⚠️ **correction (2026-11-12): the live `agy` login was `everxys00@gmail.com`, not `everxys`.**
  The first report here claimed `everxys` survived as the live login because `aisw verify` said
  "live tool credentials do not match the recorded active profile". That inference was wrong: aisw compares
  its frozen 2026-10-28 blob with the keyring byte-for-byte, so any token refresh reads as a mismatch and
  says nothing about which account it is. The live account was confirmed two other ways — `agy`'s own log
  (`authenticated successfully as everxys00@gmail.com`, matching the running process start time) and by
  decoding the Credential Manager blob. So deleting the aisw profile removed only aisw's copy; the
  `everxys00` sign-in itself was still live in `gemini:antigravity` and needed `cmdkey /delete` to clear.
  **The user chose to keep that sign-in on 2026-11-12**, so as of this writing `agy` is still logged in as
  `everxys00@gmail.com`; deleting the credential later is a one-liner and no aisw copy exists to restore
  from (`everxys` would need a fresh OAuth login).
  Lesson: never read an account identity out of aisw's mismatch flag — decode the blob or read `agy`'s log.
- **Codex (OpenAI) — desktop app + CLI, both gone 2026-10-20.** The desktop app was a **Microsoft
  Store / MSIX package** `OpenAI.Codex_2p2nqsd0c76g0` (`…\Program Files\WindowsApps\OpenAI.Codex_<ver>_x64__2p2nqsd0c76g0\app\ChatGPT.exe`)
  and was uninstalled by the user earlier; no `Get-AppxPackage *Codex*` entry and no Uninstall key remained.
  The CLI was **not** a separate npm/mise install — it shipped as a bundled "plugin app server" inside the
  app's own data dir: `~\.codex\plugins\.plugin-appserver\codex.exe` (codex-cli 0.163.0-alpha.10.2, 341 MB,
  plus codex-code-mode-host / codex-command-runner / codex-windows-sandbox-setup), and **that directory was
  the thing on user PATH**. Swept: `~\.codex` (1.3 G — sessions, thread_history_1.sqlite, logs_2.sqlite,
  auth.json, skills, plugins/cache), `%LOCALAPPDATA%\OpenAI\Codex` (672 M — runtimes/bin),
  `%LOCALAPPDATA%\Codex`, `%APPDATA%\Codex`, `%TEMP%\codex-clipboard-*.png`, the user-PATH entry
  `C:\Users\everx\.codex\plugins\.plugin-appserver`, and `HKCU\…\Shell\Associations\UrlAssociations\codex`
  plus the BackgroundAccessApplications / Notifications\Settings / Start\TileProperties AppX echoes (MuiCache,
  CloudStore, AppCompatFlag and FeatureUsage echoes were left — Windows rebuilds them).
  Untouched on purpose: `%APPDATA%\orca\codex-*` (~17 KB) is **Orca's** state pointing at the old binary, and
  `~/.config/magpie/providers.json` still lists a `codex` provider. Both are other tools' data.
  ⚠️ `~/.codex` was **cleared 2026-10-28**: its whole contents (2.8 M from a one-off bootstrap run
  stamped 2026-10-26 22:41:19 — `state_5.sqlite`, `installation_id`, `.system` skills, `tmp/arg0/...`)
  were quarantined to `%LOCALAPPDATA%\hermes\cache\trash-2026-10-28-codex\`. The user then deleted the empty `~/.codex` directory on the same day, so the existence guard in any
  skill mirror skips it again; still no `codex*.exe`, winget/Appx package or registry entry exists. The writer behind the earlier
  `~/.codex/skills` copies (`C:\Users\everx\dev\common\SKILL\AGENTS.md` + `scripts/sync-skill.ps1`)
  was deleted with that project the same day — see `references/agent-skill-mirrors.md`.
- **skills-manager 1.42.1** (github.com/xingkongliang/skills-manager, publisher
  `agentskills`, Tauri app, id `com.agentskills.desktop`) — uninstalled 2026-10-18.
  Removed: install dir `%LOCALAPPDATA%\skills-manager` (by its own uninstaller),
  data `~\.skills-manager` (db + `bin\skills-manager-cli.exe`), `%APPDATA%\skills-manager`,
  `Downloads\skills-manager_1.42.1_x64-setup.exe`, the 1.42.2 updater cache in
  `%TEMP%`, its NSIS temp dir `%TEMP%\~nsu2.tmp`, and the MuiCache / AppListBackup /
  CloudStore / Compatibility-Assistant registry echoes. Its CLI was never on PATH.
  It had managed **no** skills (DB: 0 rows in `skills`, `skill_targets`,
  `discovered_skills`, `projects`, `audit_log`; only settings named `~\.agents\skills`).
  ⚠️ `~\.skills-manager\skills` **survived** (98 skill dirs) and is still the target of most
  symlinks inside `~\.agents\skills`. Since 2026-10-28 it is library storage only — it is **no
  longer** an `entries` path in `.gemini\config\skills.json`, so skills reach every agent
  through the bus alone. Those symlinks are live, not dangling — never sweep that directory as
  residue without asking; `manage-skills` is the one skill that exists only there.
- **SkillBuddy** (`%LOCALAPPDATA%\@skillbuddydesktop-updater`, 72 MB installer cache)
  — orphaned cache removed 2026-10-18; no install dir or uninstall entry remained.
- **Hermes Agent — uninstalled and swept clean 2026-11-06.** Official `hermes uninstall --full` was run to clear User PATH and gateway registrations. Swept: `%LOCALAPPDATA%\hermes` (~5.3 GB — tools, hermes-agent, cache, installs, plugins, sessions, logs), `~/.hermes` (NTFS Junction), `~/.basic-memory` (68.8 MB — fastembed cache, memory.db), `~/basic-memory`, `~/hermes-memory` (210 KB — session notes), and `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Hermes.lnk`. Command and User PATH entry are both gone.

