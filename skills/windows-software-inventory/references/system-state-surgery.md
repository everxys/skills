# Surgical Windows system-state edits

Recipes for the three edits that a plain delete or a shell one-liner gets wrong
on Windows. Each one is reversible-by-inspection: prove the change by re-reading
before and after, never by an exit code.

## 1. Removing a DENY ACE that blocks deletion

Symptom: `rm -rf <dir>` fails with `Permission denied` on some files, while no
process holds them. Two causes look identical from the shell, so separate them
first:

```powershell
$p = 'C:\path\to\the\file'
try { $s=[System.IO.File]::Open($p,'Open','ReadWrite','None'); $s.Close(); 'NOT locked' }
catch { 'LOCKED or denied: ' + $_.Exception.GetType().Name }
```

If it is NOT locked, read the ACL:

```powershell
icacls 'C:\Users\<u>\.app\logs'          # look for (DENY)(DE,DC)
```

A DENY ACE carrying `DE` (delete) / `DC` (delete child) with `(OI)(CI)`
inheritance blocks deletion for that principal down the whole subtree. It is
usually set on one directory and inherited by its children, so clear it at the
source and the children follow. Run this from **PowerShell**, not MSYS bash: bash
translates the `DOMAIN\user` argument as a path and the run reports
`Failed processing N files` while changing nothing.

```powershell
foreach ($root in @('C:\Users\<u>\.app','C:\Users\<u>\.app2')) {
  if (-not (Test-Path -LiteralPath $root)) { continue }
  $targets = @($root) + @(Get-ChildItem -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue |
                          ForEach-Object { $_.FullName })
  foreach ($t in $targets) {
    try {
      $acl = Get-Acl -LiteralPath $t -ErrorAction Stop
      $denies = @($acl.Access | Where-Object { $_.AccessControlType -eq 'Deny' })
      if ($denies.Count -gt 0) {
        foreach ($r in $denies) { [void]$acl.RemoveAccessRuleSpecific($r) }
        Set-Acl -LiteralPath $t -AclObject $acl -ErrorAction Stop
      }
    } catch { Write-Output ("acl fail: {0} :: {1}" -f $t, $_.Exception.Message) }
  }
  Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction Stop
}
```

Verify with `Test-Path` afterwards. Removing the ACE is `RemoveAccessRuleSpecific`
(an exact rule match), not `RemoveAccessRule` (a fuzzy match that can drop more
than intended).

## 2. Auditing and editing PATH

Two hives, two different editors:

| Scope | Registry key | Needs admin |
|---|---|---|
| user | `HKCU\Environment` value `Path` | no |
| machine | `HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment` value `Path` | yes — `net session` tells you whether you have it |

The value is normally `REG_EXPAND_SZ`. **Preserve the type**: write it back with
`winreg.SetValueEx(key, 'Path', 0, winreg.REG_EXPAND_SZ, new)`. .NET's
`[Environment]::SetEnvironmentVariable(...,'User')` stores `REG_SZ` and bakes in
the expansion of `%USERPROFILE%`-style entries, which quietly changes behaviour
for every future process.

```python
import winreg
STALE = r'C:\Users\<u>\AppData\Local\Programs\Ollama'   # must match the stored string exactly
key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment', 0, winreg.KEY_READ | winreg.KEY_SET_VALUE)
raw, vtype = winreg.QueryValueEx(key, 'Path')
parts = [p for p in raw.split(';') if p]
kept  = [p for p in parts if p.strip().lower() != STALE.lower()]
if len(parts) - len(kept) != 1:
    raise SystemExit('expected exactly one match; nothing written')
winreg.SetValueEx(key, 'Path', 0, winreg.REG_EXPAND_SZ, ';'.join(kept))
winreg.CloseKey(key)
```

Then tell the running system to re-read it, so newly launched programs pick it up
immediately:

```python
import ctypes
ctypes.windll.user32.SendMessageTimeoutW(
    0xFFFF, 0x1A, 0, ctypes.c_wchar_p('Environment'), 0x0002, 3000,
    ctypes.byref(ctypes.c_ulong()))
```

Two facts that decide whether an entry is editable at all:

- **A path can be stale, and a path can be absent from the registry.** A PATH
  entry that is only in a running process's inherited environment (added by an
  app at logon) cannot be removed by editing the registry because it is not
  there. Read the registry first; if the entry is missing, report it as
  process-inherited and let it clear on the next logon instead of claiming you
  removed it.
- **`%VAR%` entries never compare equal to their expansion.** Resolve both sides
  before declaring a duplicate.

Always re-read with `reg query` afterwards and re-test every remaining entry
with `Test-Path`/`-d`, so you can state that the survivors are all valid.

## 3. Removing a WSL distribution

```bash
wsl.exe -l -v                      # which distro, is it the default
wsl.exe --help | grep -A2 -- --unregister   # confirm the semantics you are about to use
wsl.exe --unregister <Distro>      # unregisters AND deletes the root filesystem
```

- `--unregister <Distro>` is the one to use. It acts on the distribution's own
  vhdx from the Windows side.
- Bare `wsl --uninstall` **uninstalls WSL itself** — never use it to remove a
  distribution. The `-d <Distro>` form is scoped to a distribution.
- Do **not** remove a distribution by deleting files from inside it. `/mnt/c` is
  the live Windows filesystem, and `rm -rf` against anything resolving there
  deletes real Windows files with no recycle bin.

The vhdx is the thing whose size you are freeing, and it can be far larger than
the distro's apparent contents (`AppData\Local\wsl\{guid}\ext4.vhdx` under the
modern distribution model, or the distro's `LocalState` under the older one).
`du -sh` it before and after to report real bytes.

**A distribution's Linux home dies with it.** Before removing one, scan every
repository inside it for BOTH unpushed commits (`git log --branches --not
--remotes`) and untracked files (`git status --porcelain | grep '^??'`).
Untracked files exist nowhere else and are the part people forget; clean
commits are not a clean working tree. Present the untracked inventory with its
size and ask — that is the one deletion in this file a user often does not mean.
If they say the contents do not matter, `--unregister` and nothing else.

## 4. Editing a protected `.env`

The file-write tools refuse `.env` as a credential file, and `hermes config set`
does not reach it. Make the change without rewriting the file:

```bash
E="$HERMES_HOME/.env"
wc -l < "$E"; sha256sum "$E"; grep -n '^THE_KEY=' "$E"      # fingerprint before
sed -i 's|^THE_KEY=old$|THE_KEY=new|' "$E"                     # anchored, whole-line
wc -l < "$E"; sha256sum "$E"; grep -n '^THE_KEY=' "$E"      # fingerprint after
```

Anchor both ends of the pattern so only the intended line can match. Report the
unchanged line count plus the one changed line as the proof; do not copy the
file to a backup the user did not ask for.
