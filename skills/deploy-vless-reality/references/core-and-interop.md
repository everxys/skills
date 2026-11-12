# Core version, interoperability, download, upgrade

## Core/client interoperability

Reality is not a wire standard; each implementation negotiates its own handshake. A server that works with its own client can still reject the client you ship. Confirm the pair before installing and after any upgrade on either side.

| Server core | Client | Result |
|---|---|---|
| Xray v26.10.21 | mihomo 1.19.32 (Clash Verge) | ✗ client `REALITY authentication failed`; server `authentication failed or validation criteria not met` |
| Xray v26.10.21 | Xray v26.10.21 | ✓ |
| Xray v25.12.8 | mihomo 1.19.32 | ✓ (also the long-running reference host) |

Symptom signature: the server logs `REALITY: processed invalid connection ... authentication failed or validation criteria not met` for every attempt, the client reports `REALITY authentication failed`, changing `client-fingerprint` does not help, and the same keys/SNI/shortId work with an Xray client.

- `install.sh` defaults to **25.12.8** for Clash/mihomo clients. Move to a newer line only after an end-to-end test with the target client; add the new row here.
- Do not diagnose this as a key, UUID, SNI or network problem. Isolate it with the A/B in [verify.md](verify.md#local-l4-relay): same relay, Xray client vs target client. Xray works and the target client does not → change the server core version, not the config.

## Download and integrity

- URL: `https://github.com/XTLS/Xray-core/releases/download/v<ver>/Xray-linux-<arch>.zip`; arch map: `x86_64→64`, `aarch64→arm64-v8a`, `armv7→arm32-v7a`, `i686→32`, `riscv64`, `s390x`.
- `install.sh` checks the `SHA2-256=` line of the matching `.dgst` file and extracts **only** the `xray` binary (no geo files are needed by this config). On a 128 MiB cgroup, `unzip` and `apk add` alone can increment `oom_kill`; record the baseline first.
- IPv6-only boxes: see [stacks.md](stacks.md#ipv6-only).
- `xray x25519` output labels changed across releases: `Private key:`/`Public key:` → `PrivateKey:`/`Password:` (25.x) → `PrivateKey:`/`Password (PublicKey):` (+ `Hash32:`). Parse by label, never by line number. `install.sh` re-derives the public key with `xray x25519 -i <private>` and refuses to continue on a mismatch.

## Replacing or upgrading the core

Never overwrite a running binary, and never trust a version until it has executed on the target host. Overwriting the live `xray` once produced a binary that segfaulted on `version`, taking the service down; the same file had run from `/tmp` moments earlier.

`install.sh --version X.Y.Z` (credentials are reused) does this in order:

1. Download to a temp dir, run `<tmp>/xray version`; stop if it cannot run.
2. Test the new config with the new binary (`run -test`).
3. Back up the old binary to `backup/<ts>/xray.bin`, stop the service, copy the new binary, start.
4. Run `verify-server.sh`.

Then re-run the **target-client** verification: a core change invalidates every earlier client test. Roll back with `uninstall.sh --rollback <ts>`.
