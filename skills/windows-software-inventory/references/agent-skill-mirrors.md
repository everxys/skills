# Per-host skill mirrors — who copies skills where, and how to trace a stray copy

Use when a skills directory turns up under an agent host that is (or should be)
uninstalled, or before changing any rule that "also syncs skills to the other
agents". The bus is `~/.agents/skills`; every other per-host skills dir is a
mirror of it, written by some script or CLI — that writer is the thing to
identify, not the files.

## The locations

- `~/.agents/skills` — the shared bus. `agy` reads it via `entries` in
  `~/.gemini/config/skills.json`, and the OpenCode harness loads it directly.
- `~/.gemini/skills`, `~/.claude/skills` — retired per-host
  target dirs, **emptied 2026-10-28** (contents quarantined to
  `%LOCALAPPDATA%/hermes/cache/trash-2026-10-28-skill-mirrors/`). Nothing installs into
  them any more: a skill is written to `~/.agents/skills` and nowhere else, so no host
  needs a copy of its own.
- `~/.codex/skills` — Codex-shaped mirror. Two of its subdirectories are **not**
  mirrors: `skills/.system/` and `.tmp/` are Codex's own bootstrap output. The whole dot-dir is
  gone since 2026-10-28 (contents quarantined to `hermes/cache/trash-2026-10-28-codex`, empty dir
  removed by the user), so the existence-guarded copier skips this host again.
- `~/.skills-manager/skills` — a 98-dir library that outlived its app; most
  symlinks inside `~/.agents/skills` point at it. Never sweep it as residue.

## Who writes copies, and how

- `C:/Users/everx/dev/common/SKILL/AGENTS.md` + `scripts/sync-skill.ps1` — **deleted
  2026-10-28**, when that project was emptied; no copy of the script survives on this host, so
  nothing is armed from it any more. While it existed it targeted `~/.agents/skills`,
  `~/.gemini/skills`, `~/.codex/skills`; **copied** (never links, by rule), skipped a target whose
  directory was absent, and hash-checked `SKILL.md` afterwards. That existence guard is what copied
  the two `nas-movie-*` skills into `~/.codex/skills` on 2026-10-27, right after a one-off Codex
  bootstrap re-created `~/.codex`: the guard tests the destination directory, so it protects nothing
  once the retired tool writes its home again.
- `dbs-install-skill/scripts/install-skill.sh` — opposite policy: installs into
  `~/.agents/skills` as the bus and keeps `~/.codex`, `~/.gemini`, `~/.copilot`,
  `~/.cursor` and ~20 more in `REDUNDANT_TARGET_DIRS` to *clean up*, using
  junctions/symlinks not copies.
- `manage-skills` (skills-manager-cli) — `skills deploy <skill> --agent <key>`
  writes a real deployment per agent key, codex included.
- `magpie library skill` — pushes the Magpie library into agents; `magpie library`
  prints `Skills: none yet` when it is not the writer.

Say which of these is actually armed before touching anything: the repo rule and
`dbs-install-skill` contradict each other on purpose, and a change that is
correct under one is wrong under the other.

## Tracing "why does the uninstalled agent's dir have skills"

1. **Timestamp the whole tree**, not just the skills subdir:
   `ls -la --time-style=full-iso <home>`. Every file stamped in the same second
   (plus `installation_id`, a state sqlite, a `tmp/arg0/...` shim) means the
   agent's own bootstrap re-created its home — the copier arrived later.
2. **Copy or link?** `stat -c '%h %i %s %n'` on both copies: same inode = link or
   junction; different inodes + `diff -rq` clean = a real copy with preserved
   mtime, i.e. a copy-based script. mtime equality alone proves nothing.
3. **Find the armed writer**: `grep -rn '\.codex/skills' ~/dev ~/.agents/skills
   ~/.skills-manager/skills` and read the rule file it hits. An existence-guarded
   script is armed the moment the directory exists again.
4. **Prove the tool is really gone**: `winget list | grep -i <tool>`,
   `Get-AppxPackage`, `find` in the Program Files / `LocalAppData/Programs` /
   mise / `.local/bin` roots, the npx cache, and `reg query` for MuiCache plus the
   Uninstall keys. All empty = an ephemeral run, and the binary that ran is gone.
5. Report the count and the size split (bus copy vs host's own state), name the
   writer, then offer the scopes below.

## Removal scopes to offer (ask, don't act)

- Only the mirrored skills — leaves the host's own `skills/.system` and state DBs.
- The whole dot-dir, quarantined to `%LOCALAPPDATA%/hermes/cache/trash-<date>-<topic>/`
  so it moves back with one `mv`.
- Drop the retired host from the sync target list so it cannot fill again.

## Pitfalls

- **An existence guard protects nothing once the tool re-creates its home.** The
  guard tests the destination directory; the retired tool recreates it on its
  next run and every later sync silently resumes copying. Guard the executable
  (`command -v <tool>`) or remove the host from the target list.
- **Byte-identical is not evidence of authorship.** Two copies can agree exactly
  and still come from a junction, a copy script, or a deploy CLI — the link count
  and inode are the discriminator.
- **A host's `.system`/built-in skills are not mirror content.** Deleting them
  changes that tool's behaviour if it ever runs again; delete only the names that
  also exist on the bus.
- **A mirror that reappeared changes what the index must say.** When the dot-dir
  comes back, the index entry calling it "swept clean" is wrong — correct it in
  the same pass, per the pointer-slot rule in SKILL.md.
