# Lifecycle: re-run, change, upgrade, rollback, uninstall

All state lives under `/usr/local/etc/xray/`:

| Path | Content |
|---|---|
| `config.json` (600) | live config |
| `vless-reality.env` (600) | UUID, keys, shortId, SNI, ports, public addresses, version, name, init, firewall rule added |
| `backup/<YYYYmmdd-HHMMSS>/` | config, state, service file, previous binary (`xray.bin`) taken before each change |

## Re-run safety

`install.sh` can be re-run any time with the same or new options:

- Credentials are read from the state file and reused; command-line options (`--sni`, `--port`, `--public-*`, `--version`, `--health-interval`) always win over the rest of the state file. `--rotate-keys` generates new ones (every client must then be updated).
- The binary is downloaded only when the installed version differs from `--version` (or `--binary` is given).
- The new config is tested before the service is stopped; the running binary is never overwritten in place.
- A change ends with `verify-server.sh`; on failure it prints the rollback command.
- `--dry-run` prints the plan and the config with placeholders instead of secrets and changes nothing.

## Typical changes

| Change | Command | Disconnect |
|---|---|---|
| New Reality target | `install.sh --sni www.cloudflare.com` (+ same other options) | one restart |
| Health-check interval | `install.sh --health-interval 60` | one restart (OpenRC passes it at start) |
| Upgrade/downgrade core | `install.sh --version X.Y.Z` | one restart; re-run target-client test |
| Provider changed the mapping | `install.sh --public-port N [--public-port-v6 M]`, then `gen-client.sh --profile` | one restart (the script always re-applies); only clients need the new port |
| New client material | `gen-client.sh --profile` → `dev\clash\vps-<ip>.yaml` | none |

Keep the other options identical between runs; anything not passed falls back to the defaults, not to the previous run (credentials excepted). The state file shows the previous values.

## Convert an existing install to a single IPv4 node

When the box already has a working VLESS+Reality service and the user only wants to drop the IPv6 entry (or bind IPv4-only) with minimal change:

- Reuse the existing credentials, SNI, keys and shortId. Do **not** re-run `install.sh` and do **not** rotate keys unless the user asked. Edit `config.json` listen addresses if an IPv4-only bind is required (`127.0.0.1` plus the host/internal IPv4; see [stacks.md](stacks.md#ipv4-only)), then `xray run -test` and restart the service.
- Update only the client profile at `dev\clash\vps-<ip>.yaml`: keep the v4 entry, delete the v6 entry and any fallback group. Do not touch `vps.yaml` or `blocklist.yaml`.
- Binding IPv4-only does not remove a provider IPv6 mapping; the user must turn that mapping off in the panel.

## Rollback and uninstall

```sh
sh uninstall.sh --list                  # backups
sh uninstall.sh --rollback <timestamp>  # restore that backup's config/state/service/binary, test, start
sh uninstall.sh                         # stop, remove service/binary/config/firewall rule/bbr drop-in; keep a final backup
sh uninstall.sh --purge                 # also delete state and all backups (secrets)
```

A manual install that predates this skill has no state file: run `detect.sh`, read the existing config, and either keep managing it by hand or re-install with `install.sh` (new credentials unless you write the existing ones into the state file first; tell the user before rotating).
