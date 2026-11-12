# Google eligibility gate

Applies whenever the node will serve a Google-backed agent. If the user says the node is for general browsing only, note that and skip it.

**Unknown use, or no agent client available:** do not block the deployment and do not guess. Run only the lookup pre-signal (below), record the result as `google gate: skipped (lookup only: <country>, <ASN>, flags)`, and say in the report that the real gate was not run and why. Run the real gate later if the node turns out to serve such an agent.

Google evaluates the egress IP and can reject a healthy, fast node with `FAILED_PRECONDITION (code 400): User location is not supported for the API use`, while `loadCodeAssist` succeeds and browsing works. The gate runs **before installation** and decides whether the deployment happens. On a dual-stack box, test the family the agent will actually use (usually both: run the gate once per egress family).

```sh
ssh -N -D 1080 -p SSH_PORT root@VPS_HOST       # keep open
HTTPS_PROXY=socks5://127.0.0.1:1080 agy -p "reply with exactly: PING_OK"
```

Confirm the request really went through the tunnel: log the tunnel's accepted connections and check that the API host (`daily-cloudcode-pa.googleapis.com` for Antigravity) appears. `PING_OK` alone is not proof.

## If SSH TCP forwarding is disabled

`/usr/sbin/sshd -T | grep -i '^allowtcpforwarding'`. If it reads `no`, enable it temporarily through a drop-in (the first value wins and `Include` sits at the top of `sshd_config`), then restore:

```sh
printf 'AllowTcpForwarding yes\n' > /etc/ssh/sshd_config.d/50-tmp-fwd.conf
/usr/sbin/sshd -t && rc-service sshd reload        # systemctl reload sshd on systemd
/usr/sbin/sshd -T | grep -i '^allowtcpforwarding'  # yes
# ... gate ...
rm -f /etc/ssh/sshd_config.d/50-tmp-fwd.conf
/usr/sbin/sshd -t && rc-service sshd reload
/usr/sbin/sshd -T | grep -i '^allowtcpforwarding'  # no again
```

Validate with `sshd -t` before reloading; reload, do not restart. Tell the user you changed it and restored it. If touching `sshd` is forbidden, install first and treat the through-the-node test as the only gate, and say so.

## Reading the result

- Normal answer: continue.
- `FAILED_PRECONDITION ... User location is not supported`: **stop**. Report the IP and ASN and ask for another IP/provider. Do not install, generate keys or write a profile.
- Pre-signal only: `https://iplocate.io/api/lookup/<ip>` (ipinfo.io often answers 403 to automation). Hosting ASNs widely resold for VPN use (e.g. PEG TECH / Raksmart AS54600) are usually rejected even when the country reads US; mainstream ones (HostPapa/ColoCrossing AS36352) can pass. Only the real test decides.

After installation, repeat the cheapest agent request through the finished node. Port, SNI and Reality parameters cannot fix an IP-level rejection.
