# Always-on pointer slots per agent host

Use when a host-wide rule ("don't disk-search for tool paths, read the shared
index") must reach the other agent CLIs on this machine. The content stays in
the shared skill; each host only gets a few-line pointer in its always-on slot.

## Where each host looks

- **Hermes** — `skills.external_dirs` and `skills.create_dir` in
  `C:\Users\everx\AppData\Local\hermes\config.yaml`, both pointing at
  `~/.agents/skills`. Prove a move landed with `skill_view(name)` and check its
  `_source_path` field, which names the directory that was actually read.
- **Antigravity (`agy`)** — skills via the `entries` list in
  `C:\Users\everx\.gemini\config\skills.json` (each entry is scanned one level
  deep); global rules via `~/.gemini/config/rules/*.md`. Directory-local
  `GEMINI.md` / `AGENTS.md` also apply, but they are scoped by the cwd walk and
  are the wrong slot for a machine-wide rule. It has **no skills dir of its own**: skills
  are installed only into `~/.agents/skills`, which the `entries` list names; the retired
  `~/.gemini/skills` stays empty.

## Rule file shape (`agy`)

```markdown
---
trigger: always_on
glob: "**/*"
description: <one clause naming when it applies>
---

<body: two to four lines, no path data, point at the shared skill>
```

The frontmatter keys are not in `agy --help` and the bundled
`agy-customizations` docs only enumerate `GEMINI.md` / `AGENTS.md` and
`.agents/rules/*.md`, so the `rules/` slot has to be confirmed from the binary
and then empirically. In `agy.exe`: `grep -a -o -E '.{60}always_on.{60}' agy.exe`
and `grep -a -o -E 'rules[\\/][^"[:space:]]{0,30}' agy.exe` show `always_on`,
`rules/*.md`, `rules/AGENTS.md` and `Invalid rule trigger: %v` — enough to keep
the documented frontmatter shape, not enough to skip the probe below.

## Verification probes — run these, not just a directory listing

1. Ask the CLI a question whose answer is a path the index holds, and demand the
   provenance while forbidding search, e.g.
   `agy -p "<binary> 的完整绝对路径是什么？说明你从哪里知道的，不要搜索磁盘"`.
   A loaded rule shows up as the answer naming the rule file as preloaded, then
   quoting the index section (a `file://` link to both is typical). An answer
   built from PATH knowledge that cites neither is proof the rule is not loaded.
2. `[ -e <pointer-path> ]` for every pointer claimed in the index header.

## Pitfalls

- **A pointer dir can vanish silently.** The whole `~/.gemini/config/rules/`
  directory disappeared while the index header still advertised it, so `agy`
  spent that period with no rule at all. Re-test every claimed pointer before
  repeating the claim; recreate it, then re-probe.
- **Never write a Windows path into a tool argument with single backslashes.**
  In JSON payloads (and anything else that unescapes) `\r`, `\n`, `\t`, `\b`,
  `\f` are control characters: `...\config\rules\...` becomes
  `config` + CR + `ules` and the path silently reads as two lines. Pass
  `C:/Users/...` or doubled backslashes, and read the paragraph back after the
  write.
- **A line-based patch applies but splits long paths mid-token.** `success: true`
  with a diff showing the break is the tell; fix it with a byte-level replace
  (`python -c` opening the file `'rb'`, replacing the split token) rather than a
  second text patch, which will fail to match across the CRLF. For any
  multi-line edit to a CRLF markdown file, go byte-level first and try both the
  LF and the CRLF spelling of the old text; inside that Python use raw strings,
  because a normal string holding `%LOCALAPPDATA%\hermes` does not even parse
  (`\U` is read as a truncated unicode escape).
- **`skill_view` can return a cached revision** for a reference file that was
  just edited by a non-skill tool. When the file on disk is what other agents
  read, confirm it with `sed -n` / `md5sum` instead of trusting the cached body.
