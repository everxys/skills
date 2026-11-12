# Remote automation over flaky SSH

- Pipe scripts instead of long inline commands: `ssh -p P root@H 'sh -s -- --args' < scripts/detect.sh`. For multi-step changes upload the `scripts/` folder (`scp -P P -r scripts root@H:/root/vless-reality/`) and run from there.
- Scripts must have LF endings; CRLF fails with `$'\r': command not found`. Convert on upload from Windows.
- Do not trust inline one-liners through a Windows shell: PowerShell expands `$` in double quotes, mangles here-strings, and `cmd.exe` has no `;` chaining. If output looks short, assume the command was mangled and run it as a file.
- Retry `ssh`/`scp` with a delay; provider NATs reset sessions. A dropped session is "unknown state": re-read `xray version`, service status and the listener before re-running. `install.sh` is idempotent, so re-running after reading the state is safe.
- `$SSH_CLIENT` under provider NAT shows the gateway (e.g. `10.91.0.1`), not the operator.

## Password authentication

Prefer keys: use the password once to append a dedicated operator key to `~/.ssh/authorized_keys`, then switch to `-i <key> -o IdentitiesOnly=yes -o BatchMode=yes`. With a password, in this order:

1. **`SSH_ASKPASS`** (first choice; needs only OpenSSH ≥ 8.4): a helper that prints an environment variable, so nothing else has to be installed.
   ```sh
   printf '#!/bin/sh\nprintf "%%s\\n" "$VPS_PW"\n' > "$TMP/ap.sh"; chmod 700 "$TMP/ap.sh"
   VPS_PW=... SSH_ASKPASS="$TMP/ap.sh" SSH_ASKPASS_REQUIRE=force DISPLAY=:0 \
     setsid ssh -o PubkeyAuthentication=no -p PORT root@HOST '...'
   rm -f "$TMP/ap.sh"; unset VPS_PW
   ```
2. **`sshpass -e`** with `SSHPASS` in the environment, only if it is already installed; operator machines often cannot install it (no package, broken repos, no root).
3. **Python `paramiko`**, if installed (see the Windows notes below).

- Windows operator: OpenSSH cannot take a password non-interactively. Use Python `paramiko` (`connect(..., password=..., look_for_keys=False, allow_agent=False, timeout=25, banner_timeout=30)`, `open_sftp()` for uploads), reading the password from an environment variable or a throwaway file in the session scratchpad that you delete afterwards. Shell escaping eats `$`, `^` and quotes, so never put the password on a command line.
- Never echo the password, write it into logs or reports, or store it in the skill folder.

## PowerShell: secrets leak through error messages

Seen 2026-11-10: a helper named `H` (meant to hash a field) collided with the built-in alias `H` = `Get-History`. PowerShell called `Get-History` instead, and every call failed with `Cannot convert value "<the UUID/public key/shortId>" to type "System.Int64"`: the error message printed each secret in clear text into the tool output.

- Never give helpers short or common names. Avoid every built-in alias (`h`, `r`, `gc`, `gi`, `ls`, `cat`, `diff`, `sort`, `select`, `where`, `group`, `measure`, `sc`, `iex`, …); use a `Verb-Noun` name such as `Get-Sha16Str`. Check first: `Get-Command <name> -ErrorAction SilentlyContinue` must return nothing.
- Any script that touches secrets: `$ErrorActionPreference = 'Stop'` and wrap the work in `try { … } catch { 'ERROR (details suppressed)'; exit 1 }`. Never print `$_`, `$Error`, or the exception message, since they echo the parameter values.
- **Dry-run every new secret-handling script on a dummy file with fake values first.** Check that the output holds only hashes or field names, and that a forced error (a missing file) prints only the suppressed message. Then run it on the real file.
- Do not show `verge-mihomo -t` or parser output raw for files with secrets. Match `test is successful` and print only pass or fail, because parse errors quote the offending line.
- Compare a client profile with the server **by hash only**: on each side print `field=sha256(value)[:16]` for server, port, uuid, public-key, short-id, servername and flow. Take the public key from `xray x25519 -i <PRIV>` on the server, and the uuid/shortId from `config.json`, not only the state file. Diff the two lists on the operator box and report only field names that differ.
- If a secret did leak into a transcript, say so to the user. List which nodes and fields were affected, and offer `install.sh --rotate-keys` (all clients must be updated afterwards). Never quote the values again.
